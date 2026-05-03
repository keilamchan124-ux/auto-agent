from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.action_router import ActionExecutionResult, ActionRouter


@dataclass
class LoopContext:
    task: str
    step: int
    max_steps: int
    execution_budget: int
    phase: str


class AgentLoop:
    """Encapsulates loop-level execution behaviors to slim down Agent class."""

    def __init__(self, agent: Any, router: ActionRouter):
        self.agent = agent
        self.router = router

    def dispatch_action(self, action: str, kwargs: Dict[str, Any]) -> ActionExecutionResult:
        return self.router.dispatch(action, kwargs)

    def complete_if_mark_done(self, action: str, kwargs: Dict[str, Any], ctx: LoopContext) -> bool:
        if action != "mark_done":
            return False
        if self.agent.state.task_mode == "mobile" and not self.agent.state.quality_gate_passed:
            return False
        if self.agent.state.task_mode == "mobile" and self.agent.state.quality_gate_web_warning:
            return False
        self.agent._write_antigravity_report(ctx.task, True, ctx.step)
        self.agent._update_runtime_progress(
            ctx.task,
            ctx.step,
            ctx.max_steps,
            phase=ctx.phase,
            current_action=action,
            last_result_ok=True,
            status="completed",
        )
        return True
