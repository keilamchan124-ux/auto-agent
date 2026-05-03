from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class ActionExecutionResult:
    action: str
    kwargs: Dict[str, Any]
    result: Dict[str, Any]


class ActionRouter:
    """Route actions to tool executors and normalize execution failures."""

    def __init__(self, execute_tool_safe: Callable[[str, Dict[str, Any]], Dict[str, Any]]):
        self._execute_tool_safe = execute_tool_safe

    def dispatch(self, action: str, kwargs: Dict[str, Any]) -> ActionExecutionResult:
        normalized_kwargs = kwargs if isinstance(kwargs, dict) else {}
        try:
            result = self._execute_tool_safe(action, normalized_kwargs)
        except Exception as exc:  # normalize unexpected execution failures
            result = {
                "ok": False,
                "message": str(exc),
                "error_type": "execution_error",
            }
        return ActionExecutionResult(action=action, kwargs=normalized_kwargs, result=result)
