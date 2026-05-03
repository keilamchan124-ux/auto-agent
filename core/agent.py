# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict, field
import json_repair
import os
import platform


from core.config import Config
from core import llm
from core import tools
from core import telemetry
from core import policy
from core import recovery
from core import rescue_orchestrator
from core import modes
from core.state_trace import StateTraceManager
from core.action_router import ActionRouter
from core.agent_loop import AgentLoop, LoopContext
from core.task_orchestrator import TaskOrchestrator
from core.error_handler_service import ErrorHandlerService
from core.mcp_policy_engine import McpPolicyEngine
from core.skill_router import SkillRouter
from core.agent_state_transition import AgentStateTransition
from core.agent_task_lifecycle import AgentTaskLifecycle
from core.agent_rescue_coordinator import AgentRescueCoordinator
from core.agent_step_executor import AgentStepExecutor

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
    last_error: Optional[str] = None
    plan_executed_count: int = 0
    quality_gate_passed: bool = False
    quality_gate_web_warning: bool = False
    quality_gate_web_warning_count: int = 0
    quality_gate_strict_web: bool = True
    task_mode: str = "general"
    shell_profile: str = "unknown"
    root_dir: str = ""
    path_aliases: Dict[str, str] = field(default_factory=dict)
    force_repair_mode: bool = False
    completion_lock_enabled: bool = True
    execution_mode: str = "skill_first"
    consecutive_policy_errors: int = 0
    last_action_signature: str = ""
    semantic_repeat_count: int = 0
    continuation_inventory_required: bool = False
    self_reflection_count: int = 0
    no_diff_write_streak: int = 0
    has_pending_file_op: bool = False
    blocked_reason: Optional[str] = None

class Agent:
    def __init__(self):
        self.state_file = Config.WORKSPACE_DIR / "state.json"
        self.current_task_id = None
        self.current_step = 0
        self.rescue_cooldown = 0
        self.current_task_text = ""
        self.state_trace = StateTraceManager(Config.WORKSPACE_DIR)
        self.action_router = ActionRouter(self.execute_tool_safe)
        self.agent_loop = AgentLoop(self, self.action_router)
        self.task_orchestrator = TaskOrchestrator()
        self.error_handler = ErrorHandlerService()
        self.mcp_policy_engine = McpPolicyEngine()
        self.skill_router = SkillRouter()
        self.load_state()

    def load_state(self):
        AgentStateTransition.load_state(self, AgentState)

    def _try_local_repair(self) -> bool:
        """Attempt local repair without calling Gemini."""
        last_action = self.state.last_action
        
        # Local fixes for common parameter mistakes
        if last_action == "plan":
            if "missing" in str(self.state.last_error).lower():
                logger.info("🔧 Detected plan parameter error, trying local fix.")
                return True
        
        if last_action == "get_skill":
            if "missing" in str(self.state.last_error).lower():
                logger.info("🔧 Detected get_skill parameter error, trying local fix.")
                return True
        
        return False

    def _simple_fallback_plan(self) -> str:
        """Simple fallback plan when Gemini is unavailable."""
        return """```json\n{"action":"plan","kwargs":{"steps":"1. Analyze the previous error\\n2. Retry with correct parameters\\n3. If still failing, switch strategy or skip this step"}}\n```"""

    def _is_done_gate_satisfied(self) -> tuple[bool, str]:
        checklist_done = not Config.TODO_FILE.exists() or not Config.TODO_FILE.read_text("utf-8", errors="replace").strip()
        if not checklist_done:
            return False, "Checklist/todo is not empty."
        if self.state.has_pending_file_op:
            return False, "Pending file operation exists."
        if self.state.no_diff_write_streak < 2:
            return False, "No-diff write streak is below threshold."
        return True, "All done-gate checks passed."

    def save_state(self):
        AgentStateTransition.save_state(self)

    def reset_counters(self):
        AgentStateTransition.reset_counters(self, AgentState)

    def _clean_workspace(self):
        """Clean workspace while preserving important files."""
        AgentStateTransition.clean_workspace()

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

    def _update_runtime_progress(
        self,
        task: str,
        step: int,
        max_steps: int,
        phase: str,
        current_action: Optional[str] = None,
        last_result_ok: Optional[bool] = None,
        status: str = "running",
    ) -> None:
        self.state_trace.update_runtime_progress(self, task, step, max_steps, phase, current_action, last_result_ok, status)

    def append_trace(self, action: str, kwargs: dict, result: dict):
        self.state_trace.append_trace(self, action, kwargs, result)
        self._write_task_summary_index({
            "task_id": self.current_task_id or "unknown",
            "step": self.current_step,
            "time": time.time(),
            "action": action,
            "result": result if isinstance(result, dict) else {},
        })

    def _rotate_global_trace_if_needed(self, trace_path, max_bytes: int = 5_000_000) -> None:
        try:
            if not trace_path.exists():
                return
            if trace_path.stat().st_size <= max_bytes:
                return
            archive_dir = Config.WORKSPACE_DIR / "artifacts" / "trace_archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_name = f"execution_trace_{int(time.time())}.jsonl"
            archived_path = archive_dir / archive_name
            trace_path.replace(archived_path)
            trace_path.write_text("", "utf-8")
            logger.info("📦 Rotated execution_trace.jsonl -> %s", archived_path)
        except Exception as e:
            logger.warning("Trace rotation failed: %s", e)

    def _write_task_summary_index(self, trace_entry: Dict[str, Any]) -> None:
        task_id = str(trace_entry.get("task_id") or "unknown")
        summary_dir = Config.WORKSPACE_DIR / "artifacts" / "task_summaries"
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_path = summary_dir / f"{task_id}.summary.json"

        current = {
            "task_id": task_id,
            "total_steps": 0,
            "failed_steps": 0,
            "last_step": 0,
            "last_action": None,
            "last_updated": None,
            "top_failed_actions": {},
        }
        if summary_path.exists():
            try:
                current = json.loads(summary_path.read_text("utf-8"))
            except Exception:
                pass

        current["total_steps"] = int(current.get("total_steps", 0)) + 1
        current["last_step"] = int(trace_entry.get("step", 0))
        current["last_action"] = trace_entry.get("action")
        current["last_updated"] = trace_entry.get("time")

        result = trace_entry.get("result") or {}
        if not bool(result.get("ok", False)):
            current["failed_steps"] = int(current.get("failed_steps", 0)) + 1
            failed_map = current.get("top_failed_actions", {}) or {}
            action = str(trace_entry.get("action", "unknown"))
            failed_map[action] = int(failed_map.get(action, 0)) + 1
            current["top_failed_actions"] = failed_map

        summary_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), "utf-8")

    def _analyze_current_task_trace(self) -> Dict[str, Any]:
        task_trace_path = Config.WORKSPACE_DIR / "artifacts" / "traces" / f"{self.current_task_id}.jsonl"
        trace_path = task_trace_path if task_trace_path.exists() else (Config.WORKSPACE_DIR / "execution_trace.jsonl")
        if not trace_path.exists():
            return {"total_steps": 0, "failed_steps": 0, "last_action": None, "top_failed_actions": []}

        total_steps = 0
        failed_steps = 0
        last_action: Optional[str] = None
        failed_action_counts: Dict[str, int] = {}

        with open(trace_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue

                if row.get("task_id") != self.current_task_id:
                    continue

                total_steps += 1
                last_action = row.get("action")
                ok = bool((row.get("result") or {}).get("ok", False))
                if not ok:
                    failed_steps += 1
                    action = str(row.get("action", "unknown"))
                    failed_action_counts[action] = failed_action_counts.get(action, 0) + 1

        top_failed_actions = sorted(failed_action_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "total_steps": total_steps,
            "failed_steps": failed_steps,
            "last_action": last_action,
            "top_failed_actions": top_failed_actions,
        }
            
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
            "status": "ok" if bool(result.get("ok", False)) else "error",
            "msg": str(result.get("message", ""))
        }
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        top_issues: List[str] = []
        next_actions: List[str] = []

        if isinstance(data.get("results"), list):
            failed = [r for r in data["results"] if isinstance(r, dict) and not r.get("ok", True)]
            top_issues.extend([str(r.get("step", "unknown")) for r in failed[:3]])
            next_actions.extend([f"Fix failing step: {str(r.get('step', 'unknown'))}" for r in failed[:2]])

        if not compact["ok"]:
            compact["err"] = str(result.get("error_type", "error"))
            if not top_issues:
                top_issues.append(compact["err"])
            if not next_actions:
                next_actions.append("Apply a targeted fix and rerun the failing tool.")

        compact["top_issues"] = top_issues[:3]
        compact["next_actions"] = next_actions[:3]

        msgs.append({
            "role": "user",
            "content": json.dumps({"result": compact}, ensure_ascii=False)
        })

    def _build_tool_first_repair_prompt(self, action: str, result: Dict[str, Any]) -> str:
        error_type = str(result.get("error_type", "runtime_error"))
        message = str(result.get("message", "")).strip()
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        failed_steps: List[str] = []
        if isinstance(data.get("results"), list):
            failed_steps = [
                str(r.get("step", "unknown"))
                for r in data.get("results", [])
                if isinstance(r, dict) and not r.get("ok", True)
            ][:3]
        return (
            "TOOL-FIRST REPAIR BRANCHING:\n"
            f"- failed_action: {action}\n"
            f"- error_type: {error_type}\n"
            f"- failed_steps: {failed_steps}\n"
            f"- top_error: {message[:240]}\n"
            "- choose one and execute next:\n"
            "A) patch code/config and rerun the same tool\n"
            "B) resolve one missing dependency/input and rerun the same tool\n"
            "C) if blocked, do minimal fallback and continue highest-impact step"
        )

    # ---------- Guards ----------
    def _build_action_signature(self, action: str, kwargs: Dict[str, Any]) -> str:
        if action == "plan":
            steps = str(kwargs.get("steps", "")).strip().lower()
            steps = re.sub(r"\s+", " ", steps)
            return f"plan:{steps[:160]}"
        if action in {"read_file", "write_file"}:
            path = tools._canonicalize_workspace_path(str(kwargs.get("path", "")))
            return f"{action}:{path}"
        if action == "run_cmd":
            cmd = str(kwargs.get("cmd", "")).strip().lower()
            cmd = re.sub(r"\s+", " ", cmd)
            return f"run_cmd:{cmd[:160]}"
        return action

    def update_repeat_guard(self, action: str, kwargs: Dict[str, Any]) -> None:
        if action == self.state.last_action:
            self.state.repeat_count += 1
        else:
            self.state.last_action = action
            self.state.repeat_count = 1
        signature = self._build_action_signature(action, kwargs)
        if signature == self.state.last_action_signature:
            self.state.semantic_repeat_count += 1
        else:
            self.state.last_action_signature = signature
            self.state.semantic_repeat_count = 1

    def should_force_rescue(self) -> bool:
        return recovery.should_force_rescue(
            error_count=self.state.error_count,
            repeat_count=self.state.repeat_count,
            parse_fail_count=self.state.parse_fail_count,
            hard_reset_count=self.state.hard_reset_count,
        ) or self.state.search_count >= 4

    def should_early_stop(self, msgs: List[Dict[str, str]], current_step: int) -> bool:
        """Early-stop heuristics disabled; never stop early."""
        return False

    def _is_ui_verify_phase(self, step: int) -> bool:
        todo_text = ""
        try:
            if Config.TODO_FILE.exists():
                todo_text = Config.TODO_FILE.read_text("utf-8", errors="replace")
        except Exception:
            todo_text = ""
        return modes.is_ui_verify_phase(self.state.task_mode, self.current_task_text or "", todo_text, step)

    def _enforce_mcp_phase_hard_gate(self, action: str, step: int) -> tuple[bool, str]:
        return self.mcp_policy_engine.enforce_mcp_phase_hard_gate(action, step, self._is_ui_verify_phase)

    def _enforce_completion_lock(self, action: str, kwargs: Dict[str, Any]) -> tuple[bool, str]:
        if action != "write_file" or not self.state.completion_lock_enabled:
            return True, ""
        path = str(kwargs.get("path", "")).replace("\\", "/")
        protected_names = {"calc.py", "test_calc.py", "math_ops.py", "check_math.py"}
        if not any(path.endswith(f"/{name}") or path == name for name in protected_names):
            return True, ""
        parent = "/".join(path.split("/")[:-1]) if "/" in path else "."
        report_path = f"{parent}/REPORT.md" if parent != "." else "REPORT.md"
        try:
            rp = tools.safe_path(report_path)
            if rp.exists():
                return False, (
                    "COMPLETION_LOCK: REPORT.md already exists for this task scope; "
                    "writes to calc.py/test_calc.py are locked. Only report updates or mark_done are allowed."
                )
        except Exception:
            pass
        return True, ""

    def _build_mcp_routing_directive(self, task: str, enabled_mcps: List[Dict[str, str]]) -> str:
        return self.mcp_policy_engine.build_mcp_routing_directive(task, enabled_mcps)

    def _enforce_mcp_usage_floor(self, action: str, step: int, task: str, enabled_mcps: List[Dict[str, str]]) -> tuple[bool, str]:
        return self.mcp_policy_engine.enforce_mcp_usage_floor(action, step, task, enabled_mcps)

    def _determine_execution_mode(self, step: int) -> str:
        """
        Unify Skills and MCP usage to avoid mixed noisy behavior.
        - skill_first: planning/implementation/debug
        - mcp_first: UI verification windows
        """
        return "mcp_first" if self._is_ui_verify_phase(step) else "skill_first"

    def _build_coordination_directive(self, mode: str) -> str:
        if mode == "mcp_first":
            return (
                "[COORDINATION MODE: MCP_FIRST]\n"
                "- Use MCP tools first for verification tasks.\n"
                "- Do NOT load or switch skills unless MCP evidence is insufficient.\n"
                "- Preferred MCP set: chrome-devtools, web-visual-feedback."
            )
        return (
            "[COORDINATION MODE: SKILL_FIRST]\n"
            "- Use loaded skills and local tools first for implementation.\n"
            "- Do NOT call browser/visual MCP tools in this mode.\n"
            "- Only switch to MCP_FIRST when entering explicit UI verify steps."
        )

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

    def _auto_fix_kwargs(self, action: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-rewrite kwargs once locally for known schema mistakes (One-shot repair)."""
        original_kwargs = kwargs.copy()
        fixed = False
        
        if action == "plan" and "steps" not in kwargs:
            for key in ["task", "plan", "goal", "input", "task_breakdown", "tasks"]:
                if key in kwargs:
                    val = kwargs.pop(key)
                    kwargs["steps"] = "\n".join([str(t) for t in val]) if isinstance(val, list) else str(val)
                    fixed = True
                    break
        elif action == "get_skill" and "skill_name" not in kwargs:
            for key in ["name", "skill"]:
                if key in kwargs:
                    kwargs["skill_name"] = str(kwargs.pop(key))
                    fixed = True
                    break
        elif action == "run_cmd" and "cmd" not in kwargs:
            if "command" in kwargs:
                kwargs["cmd"] = str(kwargs.pop("command"))
                fixed = True
        elif action == "run_python_script" and "code" not in kwargs:
            if "script" in kwargs:
                kwargs["code"] = str(kwargs.pop("script"))
                fixed = True
                
        if fixed:
            logger.info("🔧 Auto-fixed %s parameters (one-shot repair): %s -> %s", action, original_kwargs, kwargs)
            
        return kwargs

    def _summarize_skill(self, skill_name: str, full_content: str) -> str:
        """Summarize long skill content into a compact injection format."""
        max_chars = getattr(Config, "SKILL_SUMMARY_MAX_CHARS", 600)
        if len(full_content) <= max_chars:
            return full_content
            
        # Preserve key headings and important bullet points.
        lines = full_content.split('\n')
        summary = []
        current_length = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped: continue
            
            # Prefer headings and bullet-point rules.
            if stripped.startswith("#") or stripped.startswith("-") or stripped.startswith("*"):
                summary.append(line)
                current_length += len(line)
            elif current_length < max_chars // 2: # Preserve introductory context.
                summary.append(line)
                current_length += len(line)
                
            if current_length >= max_chars:
                summary.append("...(truncated to save context; follow the core rules above)")
                break
                
        if not summary:
            return full_content[:max_chars] + "...\n(truncated)"
            
        return "\n".join(summary)

    # ---------- Main loop ----------
    def _queue_followup_task(self, original_task: str, step: int, max_steps: int) -> None:
        AgentTaskLifecycle.queue_followup_task(self, original_task, step, max_steps)
        logger.info("📝 Queued continuation task in todo.txt for unfinished mission.")

    def run_task(self, task: str):
        self.reset_counters()
        self._clean_workspace()
        env_ctx = AgentTaskLifecycle.initialize_task(self, task)
        self.save_state()
        logger.info(
            "🔎 ENV LOCKED: os=%s platform=%s cwd=%s",
            env_ctx["os"],
            env_ctx["platform"],
            env_ctx["cwd"],
        )

        msgs: List[Dict[str, str]] = self.task_orchestrator.build_initial_messages(
            task=task,
            shell_profile=self.state.shell_profile,
            root_dir=self.state.root_dir,
        )

        enabled_mcps = self.mcp_policy_engine.get_enabled_registry()
        if enabled_mcps:
            mcp_lines = "\n".join([f"- {m['name']}: {m['role']}" for m in enabled_mcps])
            msgs[0]["content"] += (
                "\n\n[MCP REGISTRY]\n"
                "Registered MCP servers (use selectively based on task phase):\n"
                f"{mcp_lines}"
            )
            msgs[0]["content"] += (
                "\n\n[MCP PHASE POLICY - ENFORCED]\n"
                "1) Implementation phase (default): prioritize `context7` + `codegeneratormcp` (optional `github` as third core MCP).\n"
                "2) UI verify phase: use `chrome-devtools`/`web-visual-feedback` only when visual/runtime verification is required.\n"
                "3) Do NOT call browser MCP tools during pure implementation/debug steps unless task explicitly asks for UI verification.\n"
            )
            routing = self._build_mcp_routing_directive(task, enabled_mcps)
            if routing:
                msgs[0]["content"] += "\n\n" + routing

        # Layer 3: automatic skill routing
        selected_skills = self.skill_router.auto_select_skills(task)
        loaded_skills = self.skill_router.preload_skills(
            skill_names=selected_skills,
            msgs=msgs,
            loaded_skills_state=self.state.loaded_skills,
            summarize_skill=self._summarize_skill,
            execute_tool=tools.execute_tool,
        )
        if loaded_skills:
            self.save_state()
            logger.info("🎯 Auto-loaded %d skills: %s", len(loaded_skills), loaded_skills)
            # Inform agent which skills are preloaded to avoid duplicate loading.
            msgs[0]["content"] += (
                f"\n\n[AUTO-ROUTED] The following skills were pre-loaded based on task analysis: "
                f"{', '.join(loaded_skills)}. You may skip list_skills/get_skill for these."
            )
        else:
            logger.info("ℹ️ No skills auto-loaded. Agent will discover on its own.")

        max_steps = getattr(Config, "MAX_STEPS", 50)
        execution_budget = 40

        recent_actions: List[str] = []
        last_mode = None
        for step in range(1, max_steps + 1):
            self.current_step = step
            logger.info("🧠 Step %s/%s", step, max_steps)
            phase = "execution" if step <= execution_budget else "planning"
            self._update_runtime_progress(task, step, max_steps, phase=phase)
            mode = self._determine_execution_mode(step)
            if mode != last_mode:
                self.state.execution_mode = mode
                self.save_state()
                msgs.append({"role": "user", "content": self._build_coordination_directive(mode)})
                last_mode = mode

            # E: if too stuck, hard reset once
            if self.hard_reset_if_needed(msgs):
                continue

            parsed = AgentRescueCoordinator.request_next_action(self, msgs, step)
            if parsed is None:
                continue

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
                    rescue_text = rescue_orchestrator.run_rescue(
                        trim_history_fn=self.trim_history,
                        msgs=msgs,
                        stuck_reason="FORMAT ERROR: Agent failed to return valid JSON multiple times.",
                        simple_fallback_plan_fn=self._simple_fallback_plan,
                        workspace_dir=Config.WORKSPACE_DIR,
                        run_id=self.current_task_id or "",
                        task_id=self.current_task_id or "",
                        step=step,
                    )

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
            allowed, policy_msg = self._enforce_mcp_phase_hard_gate(str(action), step)
            if not allowed:
                self.state.error_count += 1
                msgs.append({"role": "user", "content": policy_msg})
                self.append_trace(str(action), kwargs, {"ok": False, "message": policy_msg, "error_type": "policy_error"})
                continue
            allowed, lock_msg = self._enforce_completion_lock(str(action), kwargs)
            if not allowed:
                self.state.error_count += 1
                msgs.append({"role": "user", "content": lock_msg})
                self.append_trace(str(action), kwargs, {"ok": False, "message": lock_msg, "error_type": "policy_error"})
                continue
            allowed, mcp_msg = self._enforce_mcp_usage_floor(str(action), step, task, enabled_mcps if enabled_mcps else [])
            if not allowed:
                self.state.error_count += 1
                msgs.append({"role": "user", "content": mcp_msg})
                self.append_trace(str(action), kwargs, {"ok": False, "message": mcp_msg, "error_type": "policy_error"})
                continue

            kwargs = self._auto_fix_kwargs(action, kwargs)
            if self.state.consecutive_policy_errors >= 2:
                required_cmd = "dir /b" if self.state.shell_profile == "windows" else "ls"
                if action != "run_cmd" or str(kwargs.get("cmd", "")).strip() != required_cmd:
                    msgs.append({
                        "role": "user",
                        "content": (
                            "REPAIR MODE ESCALATION: consecutive policy errors detected. "
                            f"Run environment probe exactly once with run_cmd(cmd='{required_cmd}') before any other action."
                        ),
                    })
                    continue
            if self.state.force_repair_mode and action == "plan":
                msgs.append({
                    "role": "user",
                    "content": (
                        "REPAIR MODE ACTIVE (policy_error). Plan is temporarily disabled. "
                        "Choose exactly one action now: "
                        "A) path fix, B) command fix, C) environment verify."
                    ),
                })
                continue
            if action == "plan":
                self.state.self_reflection_count += 1
                recent_plan_count = sum(1 for a in recent_actions[-9:] if a == "plan")
                if recent_plan_count >= 2:
                    msgs.append({
                        "role": "user",
                        "content": "PLAN THROTTLE: in any rolling 10 steps, max 2 plan actions. Execute concrete tool action now."
                    })
                    continue
                if self.state.self_reflection_count >= 3:
                    msgs.append({
                        "role": "user",
                        "content": (
                            "LOOP BUDGET REACHED: stop reflection/planning loops. "
                            "Run final verification now, then choose exactly one terminal step: "
                            "CALL mark_done with completion evidence OR BLOCKED: <single blocking reason>."
                        ),
                    })
                    if action == "plan":
                        continue

            if self.state.continuation_inventory_required:
                required_cmd = "dir /b" if self.state.shell_profile == "windows" else "ls"
                inventory_ok = action == "run_cmd" and str(kwargs.get("cmd", "")).strip().lower() in {required_cmd, "dir", "ls", "dir /s /b"}
                if not inventory_ok:
                    msgs.append({
                        "role": "user",
                        "content": (
                            "CONTINUATION INVENTORY GATE: first action must be a clean workspace inventory scan. "
                            f"Run run_cmd(cmd='{required_cmd}') now."
                        ),
                    })
                    continue
                self.state.continuation_inventory_required = False

            # repeat guard
            self.update_repeat_guard(action, kwargs)
            self.save_state()
            recent_actions.append(action)

            # C + A: store only clean assistant JSON, not raw thoughts
            self.append_clean_assistant(msgs, action, kwargs)

            if step > execution_budget and action not in {"plan", "read_file", "write_file", "mark_done"}:
                msgs.append({
                    "role": "user",
                    "content": (
                        "PLANNING PHASE ONLY: execution budget was the first 40 steps. "
                        "Use remaining steps to create or refine the next-task checklist in workspace files."
                    )
                })
                continue

            if self.state.repeat_count >= 3:
                msgs.append({
                    "role": "user",
                    "content": f"STOP REPEATING {action}. Change your plan."
                })
                continue
            if self.state.semantic_repeat_count >= 3:
                msgs.append({
                    "role": "user",
                    "content": (
                        f"SEMANTIC REPEAT GUARD: repeated near-identical action signature for `{action}`. "
                        "Switch strategy: list files, read missing artifact, then write/execute."
                    )
                })
                continue

            # D: count search repetition
            if action == "web_search":
                self.state.search_count += 1

            loop_ctx = LoopContext(task=task, step=step, max_steps=max_steps, execution_budget=execution_budget, phase=phase)
            # finish
            if action == "mark_done":
                ok_done, done_reason = self._is_done_gate_satisfied()
                if not ok_done:
                    msgs.append({
                        "role": "user",
                        "content": f"DONE CRITERIA GATE FAILED: {done_reason} Finish outstanding work before mark_done."
                    })
                    continue
                logger.info("✅ DONE: %s", kwargs.get("summary", ""))
                done_state = AgentStepExecutor.handle_mark_done(self, action, kwargs, loop_ctx, msgs)
                if done_state == "blocked":
                    continue
                if done_state == "done":
                    break

            # execute via ActionRouter
            dispatch_result = self.agent_loop.dispatch_action(action, kwargs)
            res_data = dispatch_result.result

            # Inject loaded skill content into system prompt to prevent history truncation loss.
            if action in ["get_skill", "load_preset"] and res_data.get("ok") and "data" in res_data:
                skill_content = res_data["data"].get("content", "")
                if skill_content:
                    target_name = res_data["data"].get("skill_name") or res_data["data"].get("preset") or action
                    max_skills = getattr(Config, "MAX_SKILLS_LOADED", 6)
                    
                    if len(self.state.loaded_skills) >= max_skills and target_name not in self.state.loaded_skills:
                        oldest_skill = self.state.loaded_skills.pop(0)
                        logger.info("🔄 Offloading oldest skill: %s", oldest_skill)

                    if target_name not in self.state.loaded_skills:
                        self.state.loaded_skills.append(target_name)
                        self.save_state()
                        
                    summarized = self._summarize_skill(target_name, skill_content)
                    msgs[0]["content"] += f"\n\n[LOADED: {target_name}]\n{summarized}"
                    # Avoid doubling context size by replacing heavy data payload.
                    res_data["data"] = {"status": "Successfully injected (summarized) into SYSTEM PROMPT."}
                    
            if action == "plan" and res_data.get("ok", False):
                self.state.plan_executed_count += 1
            if action == "write_file":
                message = str(res_data.get("message", "")).lower()
                if "already up to date" in message or "no changes" in message:
                    self.state.no_diff_write_streak += 1
                else:
                    self.state.no_diff_write_streak = 0
                self.state.has_pending_file_op = not bool(res_data.get("ok", False))
            elif res_data.get("ok", False):
                self.state.has_pending_file_op = False
            if action == "validate_mobile_quality":
                mobile_state = modes.extract_mobile_quality_state(res_data)
                self.state.quality_gate_passed = bool(mobile_state["quality_gate_passed"])
                self.state.quality_gate_strict_web = bool(mobile_state["quality_gate_strict_web"])
                self.state.quality_gate_web_warning = bool(mobile_state["quality_gate_web_warning"])
                self.state.quality_gate_web_warning_count = int(mobile_state["quality_gate_web_warning_count"])

            self.state, repair_msgs = self.error_handler.process_result(
                state=self.state,
                action=action,
                res_data=res_data,
                build_repair_prompt=self._build_tool_first_repair_prompt,
            )
            msgs.extend(repair_msgs)

            # D: compact result back to context
            self.append_clean_result(msgs, res_data)
            self.append_trace(action, kwargs, res_data)

            logger.info("🛠️ %s executed. ok=%s", action, res_data.get("ok", False))
            self._update_runtime_progress(
                task,
                step,
                max_steps,
                phase=phase,
                current_action=action,
                last_result_ok=bool(res_data.get("ok", False)),
                status="running",
            )

            if step == execution_budget:
                msgs.append({
                    "role": "user",
                    "content": (
                        "STEP 40 REACHED. If task is not complete, switch to planning mode for the next task. "
                        "Use `plan` and `write_file` to prepare a clear continuation checklist."
                    )
                })

            # === Success Heuristics + Early Stop ===
            if self.should_early_stop(msgs, step):
                self._write_antigravity_report(task, True, step)
                break

        else:
            logger.warning("Max steps reached.")
            self._write_antigravity_report(task, False, max_steps)
            self._queue_followup_task(task, max_steps, max_steps)
            self._update_runtime_progress(
                task, max_steps, max_steps, phase="planning", current_action=None, last_result_ok=None, status="needs_followup"
            )

    def _detect_task_mode(self, task: str) -> str:
        return policy.detect_task_mode(task)

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
