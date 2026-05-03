from __future__ import annotations

from typing import Any, Dict, Optional


def is_ui_verify_phase(task_mode: str, task_text: str, todo_text: str, step: int) -> bool:
    semantic_triggers = ["ui verify", "visual verify", "screenshot", "browser validation", "web validation"]
    lowered_task = (task_text or "").lower()
    lowered_todo = (todo_text or "").lower()
    if any(k in lowered_task for k in semantic_triggers):
        return True
    if any(k in lowered_todo for k in semantic_triggers):
        return True

    if task_mode != "stitch_flutter":
        return False
    mod = step % 10
    return mod in (8, 9, 0)


def should_block_mobile_mark_done(task_mode: str, quality_gate_passed: bool, quality_gate_web_warning: bool) -> Optional[str]:
    if task_mode != "mobile":
        return None
    if not quality_gate_passed:
        return (
            "QUALITY GATE REQUIRED: run validate_mobile_quality first. "
            "Only call mark_done after build/analyze/test gate passes."
        )
    if quality_gate_web_warning:
        return (
            "QUALITY GATE POLICY: web warnings must be empty before mark_done. "
            "Re-run validate_mobile_quality with strict_web=true and fix web failures."
        )
    return None


def extract_mobile_quality_state(res_data: Dict[str, Any]) -> Dict[str, Any]:
    validation_data = res_data.get("data") or {}
    warning_rows = [r for r in validation_data.get("results", []) if r.get("step") == "web-validation-warning"]
    return {
        "quality_gate_passed": bool(res_data.get("ok", False) and validation_data.get("all_passed", False)),
        "quality_gate_strict_web": bool(validation_data.get("strict_web", True)),
        "quality_gate_web_warning": len(warning_rows) > 0,
        "quality_gate_web_warning_count": len(warning_rows),
    }
