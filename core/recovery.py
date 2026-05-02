from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import time


def should_force_rescue(error_count: int, repeat_count: int, parse_fail_count: int, hard_reset_count: int) -> bool:
    """Centralized recovery policy for when to trigger rescue."""
    return (
        error_count >= 3
        or repeat_count >= 3
        or parse_fail_count >= 3
        or hard_reset_count >= 2
    )


@dataclass
class RescueEvent:
    ts: float
    run_id: str
    task_id: str
    step: int
    backend: str
    status: str
    error_code: str
    attempt: int
    latency_ms: int
    detail: str


def append_rescue_event(workspace_dir: Path, event: RescueEvent) -> None:
    """Append machine-readable rescue telemetry for dashboard/ops use."""
    p = workspace_dir / "artifacts" / "rescue_events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
