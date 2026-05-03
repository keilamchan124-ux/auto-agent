from __future__ import annotations
import time
import os
import platform
from typing import Dict

from core.config import Config


class AgentTaskLifecycle:
    @staticmethod
    def initialize_task(agent, task: str) -> Dict[str, str]:
        agent.current_task_id = f"task_{int(time.time())}"
        agent.current_task_text = task
        agent.state.task_mode = agent._detect_task_mode(task)
        agent.state.shell_profile = "windows" if os.name == "nt" else "unix"
        agent.state.root_dir = str(Config.WORKSPACE_DIR)
        agent.state.path_aliases = {"project_root": ".", "artifacts_root": "artifacts"}
        agent.state.continuation_inventory_required = "CONTINUATION TASK" in str(task).upper()
        return {"os": os.name, "platform": platform.system(), "cwd": str(Config.WORKSPACE_DIR)}

    @staticmethod
    def queue_followup_task(agent, original_task: str, step: int, max_steps: int) -> None:
        trace_summary = agent._analyze_current_task_trace()
        failed_lines = "\n".join(
            [f"- {action}: {count} failures" for action, count in trace_summary.get("top_failed_actions", [])]
        ) or "- No explicit failed action patterns found."

        followup = (
            "CONTINUATION TASK (auto-generated after step limit reached)\n"
            f"- Previous run stopped at step {step}/{max_steps}.\n"
            f"- Read workspace/artifacts/traces/{agent.current_task_id}.jsonl first, then workspace/state.json.\n"
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
