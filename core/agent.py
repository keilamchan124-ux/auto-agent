# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import json_repair


from core.config import Config
from core import llm
from core import tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgentV7.2")



@dataclass
class AgentState:
    last_action: Optional[str] = None
    repeat_count: int = 0
    parse_fail_count: int = 0
    search_count: int = 0
    hard_reset_count: int = 0
    error_count: int = 0

class Agent:
    def __init__(self):
        self.state_file = Config.WORKSPACE_DIR / "state.json"
        self.load_state()

    def load_state(self):
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text("utf-8"))
                self.state = AgentState(**data)
                return
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
        self.state = AgentState()

    def save_state(self):
        self.state_file.write_text(json.dumps(asdict(self.state), ensure_ascii=False), "utf-8")

    def reset_counters(self):
        self.state = AgentState()
        self.save_state()

    def _write_antigravity_report(self, task: str, success: bool, steps: int):
        report_path = Config.WORKSPACE_DIR / "artifacts" / "agent_execution_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"""# Agent V7.2 Execution Report

**Task**: {task}
**Status**: {"✅ Success" if success else "⚠️ Needs Manual Intervention"}
**Steps**: {steps}
**Time**: {time.strftime("%Y-%m-%d %H:%M:%S")}

## Execution Summary
Task executed successfully.

## Actions Log
"""
        report_path.write_text(content, encoding="utf-8")

    def append_trace(self, action: str, kwargs: dict, result: dict):
        trace_path = Config.WORKSPACE_DIR / "execution_trace.jsonl"
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), "action": action, "kwargs": kwargs, "result": result}, ensure_ascii=False) + "\n")
            
    # ---------- Context / History ----------
    def smart_summarize_history(self, msgs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if len(msgs) <= 6:
            return self.trim_history(msgs)

        recent = msgs[-4:]
        old_history = msgs[2:-4]

        if not old_history:
            return msgs

        summary_prompt = (
            "請用 300 字以內摘要以下對話歷史，只保留關鍵事實、已完成的步驟、重要發現：\n" + 
            "\n".join([str(m.get("content", ""))[:300] for m in old_history])
        )

        try:
            summary_resp = llm.call_gemini_rescue([{"role": "user", "content": summary_prompt}])
            summary_obj = self.extract_json(summary_resp)
            summary_text = summary_obj.get("summary", summary_resp[:500]) if summary_obj else summary_resp[:500]
        except Exception as e:
            logger.warning(f"History summary failed: {e}")
            summary_text = "歷史摘要失敗，保留原始最近訊息"

        summarized = [
            msgs[0],
            msgs[1],
            {"role": "user", "content": f"[歷史摘要] {summary_text}"},
        ] + recent

        return summarized

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
        if not text:
            return None

        # 1. strict fenced block
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                res = json_repair.loads(match.group(1))
                if isinstance(res, dict): return res
            except Exception:
                pass

        # 2. Try json-repair on whole text
        try:
            repaired = json_repair.repair_json(text, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass

        # 3. fallback
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            try:
                res = json.loads(match.group(1))
                if isinstance(res, dict): return res
            except Exception:
                pass

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
        if action == self.state.last_action:
            self.state.repeat_count += 1
        else:
            self.state.last_action = action
            self.state.repeat_count = 1

    def should_force_rescue(self) -> bool:
        """
        B + E:
        - too many parse failures
        - too many repeated actions
        - too many repeated searches
        """
        if self.state.parse_fail_count >= 2:
            return True
        if self.state.repeat_count >= 3:
            return True
        if self.state.search_count >= 4:
            return True
        if self.state.error_count >= 2:
            return True
        return False

    def hard_reset_if_needed(self, msgs: List[Dict[str, str]]) -> bool:
        """
        E: hard reset when stuck too long.
        """
        if self.state.hard_reset_count >= 1:
            return False

        if self.state.parse_fail_count >= 4 or self.state.repeat_count >= 5 or self.state.search_count >= 6 or self.state.error_count >= 3:
            self.state.hard_reset_count += 1
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
                "content": Config.SYSTEM_PROMPT
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
                rescue_text = llm.call_gemini_rescue(self.smart_summarize_history(msgs), stuck_reason=f'Repeating {self.state.last_action} {self.state.repeat_count} times.')
                parsed = self.extract_json(rescue_text)

                self.state.parse_fail_count = 0
                self.state.repeat_count = 0
                self.state.search_count = 0
                self.state.error_count = 0

                if not parsed:
                    msgs.append({
                        "role": "user",
                        "content": "RESCUE ERROR: return exactly one fenced JSON block."
                    })
                    continue
            else:
                resp = llm.call_mimo(self.smart_summarize_history(msgs))
                content = resp.get("content", "")
                parsed = self.extract_json(content)

            # B: format fail handling
            if not parsed:
                self.state.parse_fail_count += 1

                if self.state.parse_fail_count == 1:
                    msgs.append({
                        "role": "user",
                        "content": "FORMAT ERROR: return exactly one ```json block only."
                    })
                elif self.state.parse_fail_count == 2:
                    msgs.append({
                        "role": "user",
                        "content": "STRICT FORMAT ERROR: ONLY ONE JSON BLOCK. NO EXTRA TEXT."
                    })
                else:
                    logger.warning("🆘 Too many format failures, forcing rescue...")
                    rescue_text = llm.call_gemini_rescue(self.smart_summarize_history(msgs), stuck_reason=f'Repeating {self.state.last_action} {self.state.repeat_count} times.')
                    parsed = self.extract_json(rescue_text)
                    self.state.parse_fail_count = 0
                    self.state.repeat_count = 0

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
            self.save_state()

            # C + A: store only clean assistant JSON, not raw thoughts
            self.append_clean_assistant(msgs, action, kwargs)

            if self.state.repeat_count >= 3:
                msgs.append({
                    "role": "user",
                    "content": f"STOP REPEATING {action}. Change your plan."
                })
                continue

            # D: count search repetition
            if action == "web_search":
                self.state.search_count += 1

            # finish
            if action == "mark_done":
                logger.info("✅ DONE: %s", kwargs.get("summary", ""))
                self._write_antigravity_report(task, True, step)
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

            if not res_data.get("ok", False):
                self.state.error_count += 1
            else:
                self.state.error_count = 0

            # D: compact result back to context
            self.append_clean_result(msgs, res_data)
            self.append_trace(action, kwargs, res_data)

            logger.info("🛠️ %s executed. ok=%s", action, res_data.get("ok", False))

        else:
            logger.warning("Max steps reached.")
            self._write_antigravity_report(task, False, max_steps)

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