from __future__ import annotations


class PolicyGate:
    def __init__(self, phase_window: int = 3):
        self.phase_window = phase_window

    def is_ui_verify_phase(self, step: int) -> bool:
        return (step % self.phase_window) == 0

    def enforce_mcp_phase_hard_gate(self, action: str, ui_verify_phase: bool) -> bool:
        verify_actions = {"capture_web_screenshot", "web_server_status", "validate_mobile_quality"}
        if ui_verify_phase:
            return action in verify_actions or action in {"run_cmd", "read_file", "plan"}
        return True

    def enforce_completion_lock(self, action: str, completion_lock_enabled: bool) -> bool:
        if not completion_lock_enabled:
            return True
        return action != "mark_done"
