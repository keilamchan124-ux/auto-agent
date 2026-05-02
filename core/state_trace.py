from __future__ import annotations
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from core import telemetry
from core.config import Config

logger = logging.getLogger("StateTraceManager")


class StateTraceManager:
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir

    def update_runtime_progress(self, agent: Any, task: str, step: int, max_steps: int, phase: str, current_action=None, last_result_ok=None, status: str = "running") -> None:
        telemetry.update_runtime_progress(
            self.workspace_dir,
            task_id=agent.current_task_id,
            task=task,
            step=step,
            max_steps=max_steps,
            phase=phase,
            current_action=current_action,
            last_result_ok=last_result_ok,
            status=status,
            state_snapshot={
                "repeat_count": agent.state.repeat_count,
                "parse_fail_count": agent.state.parse_fail_count,
                "search_count": agent.state.search_count,
                "error_count": agent.state.error_count,
                "plan_executed_count": agent.state.plan_executed_count,
                "task_mode": agent.state.task_mode,
                "last_action": agent.state.last_action,
                "last_error": agent.state.last_error,
                "quality_gate_web_warning_count": agent.state.quality_gate_web_warning_count,
            },
        )

    def append_trace(self, agent: Any, action: str, kwargs: dict, result: dict) -> None:
        trace_path = self.workspace_dir / "execution_trace.jsonl"
        task_trace_dir = self.workspace_dir / "artifacts" / "traces"
        task_trace_dir.mkdir(parents=True, exist_ok=True)
        trace_entry = {
            "task_id": agent.current_task_id or "unknown",
            "step": agent.current_step,
            "time": time.time(),
            "action": action,
            "kwargs": kwargs if isinstance(kwargs, dict) else {},
            "result": {
                "ok": bool((result or {}).get("ok", False)),
                "message": str((result or {}).get("message", ""))[:400],
                "error_type": (result or {}).get("error_type"),
            },
        }
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
        with open(task_trace_dir / f"{agent.current_task_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
        telemetry.rotate_global_trace_if_needed(Config.WORKSPACE_DIR, trace_path)
