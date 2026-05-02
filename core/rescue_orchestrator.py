from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List

from core import llm
from core import recovery


def run_rescue(
    trim_history_fn: Callable[[List[Dict[str, str]]], list],
    msgs: List[Dict[str, str]],
    stuck_reason: str,
    simple_fallback_plan_fn: Callable[[], str],
    workspace_dir: Path,
    run_id: str,
    task_id: str,
    step: int,
) -> str:
    """
    Execute rescue chain and persist machine-readable rescue events.
    """
    try:
        rescue_text = llm.call_gemini_rescue(trim_history_fn(msgs), stuck_reason=stuck_reason)
        for idx, evt in enumerate(llm.get_last_rescue_events(), start=1):
            recovery.append_rescue_event(
                workspace_dir,
                recovery.RescueEvent(
                    ts=time.time(),
                    run_id=run_id,
                    task_id=task_id,
                    step=step,
                    backend=evt.get("backend", "unknown"),
                    status=evt.get("status", "failed"),
                    error_code=evt.get("error_code", "unknown"),
                    attempt=int(evt.get("attempt", idx)),
                    latency_ms=int(evt.get("latency_ms", 0)),
                    detail=str(evt.get("detail", "")),
                ),
            )
        return rescue_text
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return simple_fallback_plan_fn()
        raise
