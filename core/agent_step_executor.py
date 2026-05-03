from __future__ import annotations

from typing import Dict, List, Any

from core import modes
from core.agent_loop import LoopContext


class AgentStepExecutor:
    @staticmethod
    def handle_mark_done(agent, action: str, kwargs: Dict[str, Any], loop_ctx: LoopContext, msgs: List[Dict[str, str]]) -> str:
        if action != "mark_done":
            return "skip"
        mobile_block_reason = modes.should_block_mobile_mark_done(
            agent.state.task_mode,
            agent.state.quality_gate_passed,
            agent.state.quality_gate_web_warning,
        )
        if mobile_block_reason:
            msgs.append({"role": "user", "content": mobile_block_reason})
            return "blocked"
        return "done" if agent.agent_loop.complete_if_mark_done(action, kwargs, loop_ctx) else "skip"
