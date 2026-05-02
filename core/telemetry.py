# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("AgentV7.2")


def update_runtime_progress(
    workspace_dir: Path,
    *,
    task_id: Optional[str],
    task: str,
    step: int,
    max_steps: int,
    phase: str,
    state_snapshot: Dict[str, Any],
    current_action: Optional[str] = None,
    last_result_ok: Optional[bool] = None,
    status: str = "running",
) -> None:
    progress_path = workspace_dir / "artifacts" / "runtime_progress.json"
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress = {
        "task_id": task_id,
        "task_preview": task[:200],
        "status": status,
        "phase": phase,
        "step": step,
        "max_steps": max_steps,
        "progress_pct": round((step / max_steps) * 100, 2) if max_steps > 0 else 0,
        "current_action": current_action,
        "last_result_ok": last_result_ok,
        "state": state_snapshot,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), "utf-8")


def rotate_global_trace_if_needed(workspace_dir: Path, trace_path: Path, max_bytes: int = 5_000_000) -> None:
    try:
        if not trace_path.exists():
            return
        if trace_path.stat().st_size <= max_bytes:
            return
        archive_dir = workspace_dir / "artifacts" / "trace_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_name = f"execution_trace_{int(time.time())}.jsonl"
        archived_path = archive_dir / archive_name
        trace_path.replace(archived_path)
        trace_path.write_text("", "utf-8")
        logger.info("📦 Rotated execution_trace.jsonl -> %s", archived_path)
    except Exception as e:
        logger.warning("Trace rotation failed: %s", e)
