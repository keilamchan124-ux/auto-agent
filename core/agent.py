# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict, field
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
    loaded_skills: List[str] = field(default_factory=list)

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
        A + D: store compact result but preserve data for tools like web_search/get_skill.
        """
        compact = {
            "ok": bool(result.get("ok", False)),
            "msg": str(result.get("message", ""))  # Do not hard-truncate to 120 chars
        }
        if "data" in result:
            compact["data"] = result["data"]

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

    def _summarize_skill(self, skill_name: str, full_content: str) -> str:
        """
        方案 A：精簡注入 (Skill Lean Injection)
        把原本動輒數千字的技能說明，濃縮到指定字數內，保留最重要規則。
        """
        max_chars = getattr(Config, "SKILL_SUMMARY_MAX_CHARS", 600)
        if len(full_content) <= max_chars:
            return full_content
            
        # 嘗試保留大綱和重點
        lines = full_content.split('\n')
        summary = []
        current_length = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped: continue
            
            # 優先保留標題 (##) 和重點列表 (-)
            if stripped.startswith("#") or stripped.startswith("-") or stripped.startswith("*"):
                summary.append(line)
                current_length += len(line)
            elif current_length < max_chars // 2: # 保留開頭的簡介段落
                summary.append(line)
                current_length += len(line)
                
            if current_length >= max_chars:
                summary.append("...(已截斷，詳情已省略以節省 Context，請遵循上述核心原則)")
                break
                
        if not summary:
            return full_content[:max_chars] + "...\n(已截斷)"
            
        return "\n".join(summary)

    # ---------- Auto Skill Router (Layer 3) ----------
    def _auto_select_skills(self, task: str, max_skills: int = 4) -> List[str]:
        """
        規則式技能路由：根據任務文本的關鍵字匹配，自動選擇最相關的 2~4 個技能。
        用簡單的 keyword scoring —— 零成本、零延遲、不需要額外 API call。
        """
        task_lower = task.lower()
        skill_tags = getattr(Config, "SKILL_TAGS", {})

        scores: Dict[str, int] = {}
        for skill_name, info in skill_tags.items():
            keywords = info.get("keywords", [])
            score = 0
            for kw in keywords:
                if kw in task_lower:
                    # 多字關鍵字給更高分
                    score += 2 if " " in kw else 1
            if score > 0:
                scores[skill_name] = score

        if not scores:
            # 預設：複雜任務至少給一個規劃技能
            return ["planning-and-task-breakdown"]

        # 按分數降序，取前 max_skills 個
        sorted_skills = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [name for name, _ in sorted_skills[:max_skills]]

        # 確保至少 2 個：如果只有 1 個，參考 SKILL_PRESETS 補充
        if len(selected) == 1:
            presets = getattr(Config, "SKILL_PRESETS", {})
            for preset_skills in presets.values():
                if selected[0] in preset_skills:
                    for s in preset_skills:
                        if s not in selected:
                            selected.append(s)
                            break
                    break

        return selected[:max_skills]

    def _preload_skills(self, skill_names: List[str], msgs: List[Dict[str, str]]) -> List[str]:
        """
        預載入選定的技能到 System Prompt 中，讓 Agent 從第一步就擁有相關知識。
        回傳成功載入的技能名稱。
        """
        loaded = []
        max_skills = getattr(Config, "MAX_SKILLS_LOADED", 4)
        for skill_name in skill_names:
            if len(self.state.loaded_skills) >= max_skills:
                logger.info("⚠️ Skill budget reached, skipping auto-load for %s", skill_name)
                break
                
            try:
                result_raw = tools.execute_tool("get_skill", {"skill_name": skill_name})
                result = json.loads(result_raw)
                if result.get("ok") and "data" in result:
                    skill_content = result["data"].get("content", "")
                    if skill_content:
                        if skill_name not in self.state.loaded_skills:
                            self.state.loaded_skills.append(skill_name)
                        summarized = self._summarize_skill(skill_name, skill_content)
                        msgs[0]["content"] += f"\n\n[AUTO-LOADED SKILL: {skill_name}]\n{summarized}"
                        loaded.append(skill_name)
                        logger.info("📦 Auto-loaded skill: %s", skill_name)
            except Exception as e:
                logger.warning("⚠️ Failed to auto-load skill '%s': %s", skill_name, e)

        if loaded:
            self.save_state()
        return loaded

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

        # === Layer 3: 自動技能路由 ===
        selected_skills = self._auto_select_skills(task)
        loaded_skills = self._preload_skills(selected_skills, msgs)
        if loaded_skills:
            logger.info("🎯 Auto-loaded %d skills: %s", len(loaded_skills), loaded_skills)
            # 告訴 Agent 哪些技能已經預載，避免重複載入
            msgs[0]["content"] += (
                f"\n\n[AUTO-ROUTED] The following skills were pre-loaded based on task analysis: "
                f"{', '.join(loaded_skills)}. You may skip list_skills/get_skill for these."
            )
        else:
            logger.info("ℹ️ No skills auto-loaded. Agent will discover on its own.")

        max_steps = getattr(Config, "MAX_STEPS", 25)

        for step in range(1, max_steps + 1):
            logger.info("🧠 Step %s/%s", step, max_steps)

            # E: if too stuck, hard reset once
            if self.hard_reset_if_needed(msgs):
                continue

            # Decide whether to call Gemini rescue or main model
            need_rescue = self.should_force_rescue()

            if need_rescue:
                logger.warning("🆘 Agent stuck. Calling Gemini for rescue...")
                rescue_text = llm.call_gemini_rescue(self.trim_history(msgs), stuck_reason=f'Repeating {self.state.last_action} {self.state.repeat_count} times.')
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
                resp = llm.call_mimo(self.trim_history(msgs))
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
                    rescue_text = llm.call_gemini_rescue(self.trim_history(msgs), stuck_reason=f'Repeating {self.state.last_action} {self.state.repeat_count} times.')
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
                
                # 攔截 Skill 載入，將內容直接注入 System Prompt，避免被 History Truncate / Summarize 丟棄
                if action in ["get_skill", "load_preset"] and res_data.get("ok") and "data" in res_data:
                    skill_content = res_data["data"].get("content", "")
                    if skill_content:
                        target_name = res_data["data"].get("skill_name") or res_data["data"].get("preset") or action
                        max_skills = getattr(Config, "MAX_SKILLS_LOADED", 4)
                        
                        if len(self.state.loaded_skills) >= max_skills and target_name not in self.state.loaded_skills:
                            res_data["data"] = {"status": f"Failed: Skill budget exceeded (max {max_skills}). Please plan without this skill or restart task."}
                        else:
                            if target_name not in self.state.loaded_skills:
                                self.state.loaded_skills.append(target_name)
                                self.save_state()
                                
                            summarized = self._summarize_skill(target_name, skill_content)
                            msgs[0]["content"] += f"\n\n[LOADED: {target_name}]\n{summarized}"
                            # 避免 context 雙重爆大，將 data 清空
                            res_data["data"] = {"status": "Successfully injected (summarized) into SYSTEM PROMPT."}
                        
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