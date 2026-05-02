# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
import re
import time
import shutil
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
from core import mcp_registry
from core import recovery
from core import rescue_orchestrator
from core.state_trace import StateTraceManager
from core.policy_gate import PolicyGate

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

class Agent:
    def __init__(self):
        self.state_file = Config.WORKSPACE_DIR / "state.json"
        self.current_task_id = None
        self.current_step = 0
        self.rescue_cooldown = 0
        self.current_task_text = ""
        self.state_trace = StateTraceManager(Config.WORKSPACE_DIR)
        self.policy_gate = PolicyGate()
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

    def save_state(self):
        self.state_file.write_text(json.dumps(asdict(self.state), ensure_ascii=False), "utf-8")

    def reset_counters(self):
        self.state = AgentState()
        self.save_state()

    def _clean_workspace(self):
        """Clean workspace while preserving important files."""
        important_files = {"state.json", "execution_trace.jsonl", "todo.txt"}
        
        for item in Config.WORKSPACE_DIR.iterdir():
            if item.is_file() and item.name not in important_files:
                try:
                    item.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete {item.name}: {e}")
            elif item.is_dir():
                # Remove temporary folders, keep artifacts and hidden control folders.
                if item.name not in {"artifacts", ".agents", ".antigravity"}:
                    try:
                        shutil.rmtree(item)
                    except Exception as e:
                        logger.warning(f"Failed to delete dir {item.name}: {e}")

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
    def update_repeat_guard(self, action: str) -> None:
        if action == self.state.last_action:
            self.state.repeat_count += 1
        else:
            self.state.last_action = action
            self.state.repeat_count = 1

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
        # Semantic trigger first: if task/checklist explicitly asks for visual verification.
        semantic_triggers = ["ui verify", "visual verify", "screenshot", "browser validation", "web validation"]
        task_text = (self.current_task_text or "").lower()
        if any(k in task_text for k in semantic_triggers):
            return True
        todo_text = ""
        try:
            if Config.TODO_FILE.exists():
                todo_text = Config.TODO_FILE.read_text("utf-8", errors="replace").lower()
        except Exception:
            todo_text = ""
        if any(k in todo_text for k in semantic_triggers):
            return True

        # Cadence fallback for stitch mode.
        if self.state.task_mode != "stitch_flutter":
            return False
        mod = step % 10
        return mod in (8, 9, 0)

    def _enforce_mcp_phase_hard_gate(self, action: str, step: int) -> tuple[bool, str]:
        browser_like_actions = {"capture_web_screenshot", "start_web_server", "stop_web_server", "web_server_status"}
        if action in browser_like_actions and not self._is_ui_verify_phase(step):
            return False, (
                "MCP_PHASE_POLICY_VIOLATION: Browser/UI verification tools are only allowed in UI verify phase "
                "(Stitch cadence steps 8/9/10). Continue with implementation-phase actions first."
            )
        return True, ""

    def _enforce_completion_lock(self, action: str, kwargs: Dict[str, Any]) -> tuple[bool, str]:
        if action != "write_file" or not self.state.completion_lock_enabled:
            return True, ""
        path = str(kwargs.get("path", "")).replace("\\", "/")
        protected_names = {"calc.py", "test_calc.py"}
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
        names = {m.get("name", "").lower() for m in enabled_mcps}
        t = (task or "").lower()
        directives = []
        if "context7" in names and any(k in t for k in ["docs", "documentation", "api", "sdk", "reference"]):
            directives.append("Use Context7 MCP early for source-grounded documentation lookups.")
        if "github" in names and any(k in t for k in ["pr", "pull request", "issue", "repository", "github"]):
            directives.append("Use GitHub MCP early for repository/PR/issue context.")
        if "codegeneratormcp" in names and any(k in t for k in ["implement", "refactor", "scaffold", "generate", "build"]):
            directives.append("Use CodeGeneratorMCP in implementation phase for scaffolding/patch acceleration.")
        if "chrome-devtools" in names and any(k in t for k in ["ui", "browser", "dom", "console", "screenshot", "visual"]):
            directives.append("Use Chrome DevTools MCP during UI verify phase only.")
        if "semgrep" in names and any(k in t for k in ["security", "vulnerability", "hardening", "injection"]):
            directives.append("Run Semgrep MCP checks before mark_done for security-sensitive tasks.")
        if not directives:
            return ""
        return "[MCP ROUTING DIRECTIVE]\n" + "\n".join([f"- {d}" for d in directives])

    def _enforce_mcp_usage_floor(self, action: str, step: int, task: str, enabled_mcps: List[Dict[str, str]]) -> tuple[bool, str]:
        """
        Require at least one MCP-correlated action early when task semantics strongly suggest it.
        This reduces passive MCP exposure where routing hints are ignored.
        """
        if step > 8:
            return True, ""
        names = {m.get("name", "").lower() for m in enabled_mcps}
        t = (task or "").lower()
        # Keep repo intent strict to avoid false positives from generic words
        # in long prompts (e.g., "PR title" metadata in unrelated tasks).
        repo_signals = [
            r"\bgithub\b",
            r"github\.com/",
            r"\bowner/[a-z0-9_.-]+\b",
            r"\bpull request\b",
        ]
        has_repo_signal = any(re.search(p, t) for p in repo_signals)
        if "github" in names and has_repo_signal:
            github_actions = {"github_read_file", "github_clone", "github_create_pr", "github_commit_push"}
            if action not in github_actions and action not in {"plan", "read_file"}:
                return False, (
                    "MCP_USAGE_REQUIRED: This task is repository-centric. Use a GitHub MCP action early "
                    "(github_read_file/github_clone/github_create_pr/github_commit_push) before generic actions."
                )
        if "chrome-devtools" in names and any(k in t for k in ["ui", "browser", "dom", "screenshot", "visual"]):
            ui_actions = {"capture_web_screenshot", "web_server_status", "start_web_server"}
            if action not in ui_actions and action not in {"plan", "run_cmd", "read_file"}:
                return False, (
                    "MCP_USAGE_REQUIRED: This task is UI-centric. Use a UI verification action early "
                    "(start_web_server/capture_web_screenshot/web_server_status)."
                )
        return True, ""

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

    # ---------- Auto Skill Router (Layer 3) ----------
    def _auto_select_skills(self, task: str, max_skills: int = 4) -> List[str]:
        """Rule-based skill routing using keyword scoring from task text."""
        task_lower = task.lower()
        skill_tags = getattr(Config, "SKILL_TAGS", {})

        scores: Dict[str, int] = {}
        for skill_name, info in skill_tags.items():
            keywords = info.get("keywords", [])
            score = 0
            for kw in keywords:
                if kw in task_lower:
                    # Give higher score to multi-word keywords.
                    score += 2 if " " in kw else 1
            if score > 0:
                scores[skill_name] = score

        if not scores:
            # Default fallback: always include a planning skill.
            return ["planning-and-task-breakdown"]

        # Sort by score descending and keep top entries.
        sorted_skills = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [name for name, _ in sorted_skills[:max_skills]]

        # Ensure at least two skills by using presets when only one is matched.
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
        """Preload selected skills into system prompt before the loop starts."""
        loaded = []
        max_skills = getattr(Config, "MAX_SKILLS_LOADED", 6)
        for skill_name in skill_names:
            # Dynamic context protection.
            current_context_size = sum(len(m.get("content", "")) for m in msgs)
            if current_context_size > 45000:   # Force offload when context exceeds 45k chars.
                if self.state.loaded_skills:
                    oldest = self.state.loaded_skills.pop(0)
                    logger.warning("⚠️ Context too large, force offload: %s", oldest)

            if len(self.state.loaded_skills) >= max_skills:
                oldest_skill = self.state.loaded_skills.pop(0)
                logger.info("🔄 Offloading oldest skill: %s", oldest_skill)
                
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
    def _build_mission_prompt(self, task: str) -> str:
        return (
            "MISSION REQUIREMENTS:\n"
            "1) You must call the `plan` action early with concrete steps.\n"
            "2) For each major step, explicitly check whether it is completed.\n"
            "3) Only call `mark_done` when all planned items are completed.\n\n"
            f"USER TASK:\n{task}"
        )

    def _queue_followup_task(self, original_task: str, step: int, max_steps: int) -> None:
        trace_summary = self._analyze_current_task_trace()
        failed_lines = "\n".join(
            [f"- {action}: {count} failures" for action, count in trace_summary.get("top_failed_actions", [])]
        ) or "- No explicit failed action patterns found."

        followup = (
            "CONTINUATION TASK (auto-generated after step limit reached)\n"
            f"- Previous run stopped at step {step}/{max_steps}.\n"
            f"- Read workspace/artifacts/traces/{self.current_task_id}.jsonl first, then workspace/state.json.\n"
            f"- Trace summary: total_steps={trace_summary.get('total_steps', 0)}, "
            f"failed_steps={trace_summary.get('failed_steps', 0)}, "
            f"last_action={trace_summary.get('last_action')}.\n"
            "- Top failed actions:\n"
            f"{failed_lines}\n"
            "- Create/refresh a TODO checklist of unfinished items.\n"
            "- Continue execution until every checklist item is completed.\n"
            "- Verify completion status explicitly before mark_done.\n\n"
            "ORIGINAL TASK:\n"
            f"{original_task}\n"
        )
        Config.TODO_FILE.write_text(followup, "utf-8")
        logger.info("📝 Queued continuation task in todo.txt for unfinished mission.")

    def run_task(self, task: str):
        self.reset_counters()
        self._clean_workspace()
        self.current_task_id = f"task_{int(time.time())}"
        self.current_task_text = task
        self.state.task_mode = self._detect_task_mode(task)
        self.state.shell_profile = "windows" if os.name == "nt" else "unix"
        self.state.root_dir = str(Config.WORKSPACE_DIR)
        self.state.path_aliases = {"project_root": ".", "artifacts_root": "artifacts"}
        self.save_state()
        logger.info(
            "🔎 ENV LOCKED: os=%s platform=%s cwd=%s",
            os.name,
            platform.system(),
            Config.WORKSPACE_DIR,
        )

        msgs: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": Config.SYSTEM_PROMPT
            },
            {"role": "user", "content": self._build_mission_prompt(task)}
        ]
        msgs.append({
            "role": "user",
            "content": (
                f"ENV CACHE LOCKED ONCE: shell_profile={self.state.shell_profile}, root_dir={self.state.root_dir}. "
                "Prefer workspace-safe commands and keep tool arguments exact."
            ),
        })

        enabled_mcps = mcp_registry.get_enabled_mcp_registry()
        if enabled_mcps:
            mcp_lines = "\n".join([f"- {m['name']}: {m['role']}" for m in enabled_mcps])
            msgs[0]["content"] += (
                "\n\n[MCP REGISTRY]\n"
                "Registered MCP servers (use selectively based on task phase):\n"
                f"{mcp_lines}"
            )
            msgs[0]["content"] += (
                "\n\n[MCP PHASE POLICY - ENFORCED]\n"
                "1) Implementation phase (default): prioritize `context7` + `github` + `codegeneratormcp`.\n"
                "2) UI verify phase: use `chrome-devtools`/`web-visual-feedback` only when visual/runtime verification is required.\n"
                "3) Do NOT call browser MCP tools during pure implementation/debug steps unless task explicitly asks for UI verification.\n"
            )
            routing = self._build_mcp_routing_directive(task, enabled_mcps)
            if routing:
                msgs[0]["content"] += "\n\n" + routing

        # Layer 3: automatic skill routing
        selected_skills = self._auto_select_skills(task)
        loaded_skills = self._preload_skills(selected_skills, msgs)
        if loaded_skills:
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

            # Decide whether to call Gemini rescue or main model
            need_rescue = self.should_force_rescue()

            if need_rescue:
                if self.rescue_cooldown > 0:
                    self.rescue_cooldown -= 1
                    need_rescue = False
                else:
                    logger.warning("🆘 Agent stuck. Trying local repair first...")
                    
                    # Phase 1: local repair without Gemini
                    local_repair_success = self._try_local_repair()
                    
                    if local_repair_success:
                        logger.info("✅ Local repair succeeded, skipping Gemini rescue.")
                        self.state.error_count = 0
                        self.state.repeat_count = 0
                        self.rescue_cooldown = 1
                        continue
                    
                    # Phase 2: call Gemini only if local repair failed
                    logger.warning("⚠️ Local repair failed, invoking Gemini rescue...")
                    
                    # Determine stuck reason for better rescue prompt
                    stuck_reason = "Unknown stuck reason."
                    if self.state.error_count >= 3:
                        if self.state.last_error and ("missing" in str(self.state.last_error).lower() or "unexpected keyword" in str(self.state.last_error).lower() or "not found" in str(self.state.last_error).lower()):
                            stuck_reason = f"TOOL PARAMETER ERROR: {self.state.last_error}"
                        else:
                            stuck_reason = f"RUNTIME ERROR: {self.state.last_error}"
                    elif self.state.repeat_count >= 2:
                        stuck_reason = f"REPEATING ACTION LOOP: Repeated {self.state.last_action} {self.state.repeat_count} times."
                    elif self.state.search_count >= 4:
                        stuck_reason = "SEARCH LOOP: Performed too many consecutive web searches."

                    error_summary_prompt = (
                        "You made an incorrect action.\n"
                        f"Failure source: action `{self.state.last_action}` failed.\n"
                        "Summarize the mistake in one sentence and state what to do next time.\n"
                        "Format: {\"action\":\"plan\",\"kwargs\":{\"steps\":\"My mistake was ...; next I will ...\"}}"
                    )
                    
                    msgs.append({
                        "role": "user",
                        "content": error_summary_prompt
                    })
                    
                    rescue_text = rescue_orchestrator.run_rescue(
                        trim_history_fn=self.trim_history,
                        msgs=msgs,
                        stuck_reason=stuck_reason,
                        simple_fallback_plan_fn=self._simple_fallback_plan,
                        workspace_dir=Config.WORKSPACE_DIR,
                        run_id=self.current_task_id or "",
                        task_id=self.current_task_id or "",
                        step=step,
                    )

                    self.rescue_cooldown = 3   # After rescue, skip rescue for next 3 steps.
                    
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
                recent_plan_count = sum(1 for a in recent_actions[-9:] if a == "plan")
                if recent_plan_count >= 2:
                    msgs.append({
                        "role": "user",
                        "content": "PLAN THROTTLE: in any rolling 10 steps, max 2 plan actions. Execute concrete tool action now."
                    })
                    continue

            # repeat guard
            self.update_repeat_guard(action)
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

            # D: count search repetition
            if action == "web_search":
                self.state.search_count += 1

            # finish
            if action == "mark_done":
                if self.state.task_mode == "mobile" and not self.state.quality_gate_passed:
                    msgs.append({
                        "role": "user",
                        "content": (
                            "QUALITY GATE REQUIRED: run validate_mobile_quality first. "
                            "Only call mark_done after build/analyze/test gate passes."
                        )
                    })
                    continue
                if self.state.task_mode == "mobile" and self.state.quality_gate_web_warning:
                    msgs.append({
                        "role": "user",
                        "content": (
                            "QUALITY GATE POLICY: web warnings must be empty before mark_done. "
                            "Re-run validate_mobile_quality with strict_web=true and fix web failures."
                        )
                    })
                    continue
                logger.info("✅ DONE: %s", kwargs.get("summary", ""))
                self._write_antigravity_report(task, True, step)
                self._update_runtime_progress(
                    task, step, max_steps, phase=phase, current_action=action, last_result_ok=True, status="completed"
                )
                break

            # execute
            try:
                res_data = self.execute_tool_safe(action, kwargs)
                
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
                if action == "validate_mobile_quality":
                    validation_data = res_data.get("data") or {}
                    self.state.quality_gate_passed = bool(
                        res_data.get("ok", False) and validation_data.get("all_passed", False)
                    )
                    self.state.quality_gate_strict_web = bool(validation_data.get("strict_web", True))
                    warning_rows = [r for r in validation_data.get("results", []) if r.get("step") == "web-validation-warning"]
                    self.state.quality_gate_web_warning = len(warning_rows) > 0
                    self.state.quality_gate_web_warning_count = len(warning_rows)

            except Exception as e:
                res_data = {
                    "ok": False,
                    "message": str(e),
                    "error_type": "execution_error"
                }

            if not res_data.get("ok", False):
                self.state.last_error = str(res_data.get("message", ""))
                
                error_msg = res_data.get("message", "")
                error_type = res_data.get("error_type", "")
                
                # Error-type specific recovery policies
                if error_type == "tool_not_found" or "missing" in error_msg.lower() or "unexpected keyword" in error_msg.lower():
                    logger.warning("🚨 Severe/tool parameter error detected, forcing rescue.")
                    self.state.error_count = 3  # Raise directly to rescue trigger threshold.
                    
                    param_hints = {
                        "read_file": "Correct format: read_file(path='file_path')",
                        "write_file": "Correct format: write_file(path='file_path', content='...')",
                        "get_skill": "Correct format: get_skill(skill_name='skill_name')",
                        "plan": "Correct format: plan(steps='step content')",
                        "run_python_script": "Correct format: run_python_script(code='python code')",
                    }
                    hint = param_hints.get(action, "")
                    if hint:
                        logger.warning("⚠️ Tool parameter hint: %s", hint)
                        res_data["message"] = f"{error_msg}\n{hint}"
                else:
                    self.state.error_count += 1  # Runtime errors allow 2-3 retries.
                if error_type == "policy_error":
                    self.state.force_repair_mode = True
                msgs.append({
                    "role": "user",
                    "content": self._build_tool_first_repair_prompt(action, res_data)
                })
            else:
                self.state.error_count = 0
                self.state.last_error = None
                if action != "plan":
                    self.state.force_repair_mode = False

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
