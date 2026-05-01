# -*- coding: utf-8 -*-
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from config import Config
import llm
import tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgentV7.2")


class Agent:
    def __init__(self):
        self.reset_counters()

    def reset_counters(self):
        self.last_action: Optional[str] = None
        self.repeat_count = 0
        self.parse_fail_count = 0
        self.search_count = 0
        self.hard_reset_count = 0

    # ---------- Context / History ----------
    def trim_history(self, msgs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Keep history small and clean:
        - preserve system + user task
        - keep only recent messages
        - cap by message count and rough char budget
        """
        if len(msgs) <= 2:
            return msgs

        system_msg = msgs[0]
        task_msg = msgs[1]
        tail = msgs[2:]

        max_history = getattr(Config, "MAX_HISTORY", 8)
        max_chars = getattr(Config, "MAX_CONTEXT_CHARS", 8000)

        trimmed: List[Dict[str, str]] = []
        total_chars = len(system_msg.get("content", "")) + len(task_msg.get("content", ""))

        for m in reversed(tail):
            content = str(m.get("content", ""))
            if len(trimmed) >= max_history:
                break
            if total_chars + len(content) > max_chars:
                break
            trimmed.append(m)
            total_chars += len(content)

        trimmed.reverse()
        return [system_msg, task_msg] + trimmed

    # ---------- Parsing ----------
    def extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Prefer fenced JSON. Fallback to raw JSON object only.
        """
        if not text:
            return None

        # 1) strict fenced block
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if not match:
            # 2) fallback: first object-like block
            match = re.search(r"(\{.*\})", text, re.DOTALL)

        if not match:
            return None

        try:
            obj = json.loads(match.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None

        return None

    # ---------- Context append ----------
    def append_clean_assistant(self, msgs: List[Dict[str, str]], action: str, kwargs: Dict[str, Any]) -> None:
        """
        A: only store clean JSON, not raw thoughts.
        """
        msgs.append({
            "role": "assistant",
            "content": json.dumps(
                {"action": action, "kwargs": kwargs},
                ensure_ascii=False
            )
        })

    def append_clean_result(self, msgs: List[Dict[str, str]], result: Dict[str, Any]) -> None:
        """
        A + D: only store compact result.
        """
        compact = {
            "ok": bool(result.get("ok", False)),
            "msg": str(result.get("message", ""))[:120]
        }
        if not compact["ok"]:
            compact["err"] = str(result.get("error_type", "error"))

        msgs.append({
            "role": "user",
            "content": json.dumps({"result": compact}, ensure_ascii=False)
        })

    # ---------- Guards ----------
    def update_repeat_guard(self, action: str) -> None:
        if action == self.last_action:
            self.repeat_count += 1
        else:
            self.last_action = action
            self.repeat_count = 1

    def should_force_rescue(self) -> bool:
        """
        B + E:
        - too many parse failures
        - too many repeated actions
        - too many repeated searches
        """
        if self.parse_fail_count >= 2:
            return True
        if self.repeat_count >= 3:
            return True
        if self.search_count >= 4:
            return True
        return False

    def hard_reset_if_needed(self, msgs: List[Dict[str, str]]) -> bool:
        """
        E: hard reset when stuck too long.
        """
        if self.hard_reset_count >= 1:
            return False

        if self.parse_fail_count >= 4 or self.repeat_count >= 5 or self.search_count >= 6:
            self.hard_reset_count += 1
            self.reset_counters()
            msgs.append({
                "role": "user",
                "content": "HARD RESET: choose a new strategy. Do not repeat the same action."
            })
            return True

        return False

    # ---------- Tool execution ----------
    def execute_tool_safe(self, action: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        raw = tools.execute_tool(action, kwargs)
        try:
            res = json.loads(raw)
            if not isinstance(res, dict):
                return {"ok": False, "message": "Tool returned invalid JSON object", "error_type": "runtime_error"}
            return res
        except Exception:
            return {"ok": False, "message": str(raw)[:200], "error_type": "runtime_error"}

    # ---------- Main loop ----------
    def run_task(self, task: str):
        self.reset_counters()

        msgs: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "Robotic Executor.\n"
                    "ONLY JSON.\n"
                    "Output exactly one fenced JSON block.\n"
                    "No thoughts. No explanations.\n"
                    "Available actions: web_search, download_file, run_cmd, write_file, read_file, mark_done.\n"
                    "Schema: {\"action\":\"...\", \"kwargs\":{...}}"
                )
            },
            {"role": "user", "content": task}
        ]

        max_steps = getattr(Config, "MAX_STEPS", 20)

        for step in range(1, max_steps + 1):
            logger.info("🧠 Step %s/%s", step, max_steps)

            # E: if too stuck, hard reset once
            if self.hard_reset_if_needed(msgs):
                continue

            # Decide whether to call Gemini rescue or main model
            need_rescue = self.should_force_rescue()

            if need_rescue:
                logger.warning("🆘 Agent stuck. Calling Gemini for rescue...")
                rescue_text = llm.call_gemini_rescue(self.trim_history(msgs))
                parsed = self.extract_json(rescue_text)

                self.parse_fail_count = 0
                self.repeat_count = 0
                self.search_count = 0

                if not parsed:
                    msgs.append({
                        "role": "user",
                        "content": "RESCUE ERROR: return exactly one fenced JSON block."
                    })
                    continue
            else:
                resp = llm.call_mimo(self.trim_history(msgs))
                content = resp.get("content", "")
                parsed = self.extract_json(content)

            # B: format fail handling
            if not parsed:
                self.parse_fail_count += 1

                if self.parse_fail_count == 1:
                    msgs.append({
                        "role": "user",
                        "content": "FORMAT ERROR: return exactly one ```json block only."
                    })
                elif self.parse_fail_count == 2:
                    msgs.append({
                        "role": "user",
                        "content": "STRICT FORMAT ERROR: ONLY ONE JSON BLOCK. NO EXTRA TEXT."
                    })
                else:
                    logger.warning("🆘 Too many format failures, forcing rescue...")
                    rescue_text = llm.call_gemini_rescue(self.trim_history(msgs))
                    parsed = self.extract_json(rescue_text)
                    self.parse_fail_count = 0
                    self.repeat_count = 0

                    if not parsed:
                        msgs.append({
                            "role": "user",
                            "content": "RESCUE ERROR: return exactly one JSON block."
                        })
                        continue

                continue

            action = parsed.get("action")
            kwargs = parsed.get("kwargs", {})
            if not isinstance(kwargs, dict):
                kwargs = {}

            # repeat guard
            self.update_repeat_guard(action)

            # C + A: store only clean assistant JSON, not raw thoughts
            self.append_clean_assistant(msgs, action, kwargs)

            if self.repeat_count >= 3:
                msgs.append({
                    "role": "user",
                    "content": f"STOP REPEATING {action}. Change your plan."
                })
                continue

            # D: count search repetition
            if action == "web_search":
                self.search_count += 1

            # finish
            if action == "mark_done":
                logger.info("✅ DONE: %s", kwargs.get("summary", ""))
                break

            # execute
            try:
                res_data = self.execute_tool_safe(action, kwargs)
            except Exception as e:
                res_data = {
                    "ok": False,
                    "message": str(e),
                    "error_type": "execution_error"
                }

            # D: compact result back to context
            self.append_clean_result(msgs, res_data)

            logger.info("🛠️ %s executed. ok=%s", action, res_data.get("ok", False))

        else:
            logger.warning("Max steps reached.")

    def start(self):
        logger.info("🤖 Agent V7.2 Active.")

        while True:
            try:
                if Config.TODO_FILE.exists():
                    try:
                        task = Config.TODO_FILE.read_text("utf-8").strip()
                    except UnicodeDecodeError:
                        task = Config.TODO_FILE.read_text("utf-16").strip()
                    if task:
                        Config.TODO_FILE.write_text("", "utf-8")
                        self.run_task(task)
            except Exception as e:
                logger.exception("Fail: %s", e)

            time.sleep(Config.POLL_INTERVAL)


if __name__ == "__main__":
    Agent().start()