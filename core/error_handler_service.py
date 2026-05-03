# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple


logger = logging.getLogger("ErrorHandlerService")


class ErrorHandlerService:
    """Handles post-dispatch success/error state transitions for Agent."""

    PARAM_HINTS = {
        "read_file": "Correct format: read_file(path='file_path')",
        "write_file": "Correct format: write_file(path='file_path', content='...')",
        "get_skill": "Correct format: get_skill(skill_name='skill_name')",
        "plan": "Correct format: plan(steps='step content')",
        "run_python_script": "Correct format: run_python_script(code='python code')",
    }

    def process_result(
        self,
        state: Any,
        action: str,
        res_data: Dict[str, Any],
        build_repair_prompt: Callable[[str, Dict[str, Any]], str],
    ) -> Tuple[Any, List[Dict[str, str]]]:
        msgs: List[Dict[str, str]] = []
        if not res_data.get("ok", False):
            state.last_error = str(res_data.get("message", ""))
            error_msg = res_data.get("message", "")
            error_type = res_data.get("error_type", "")

            if error_type == "tool_not_found" or "missing" in error_msg.lower() or "unexpected keyword" in error_msg.lower():
                logger.warning("🚨 Severe/tool parameter error detected, forcing rescue.")
                state.error_count = 3
                hint = self.PARAM_HINTS.get(action, "")
                if hint:
                    logger.warning("⚠️ Tool parameter hint: %s", hint)
                    res_data["message"] = f"{error_msg}\n{hint}"
            else:
                state.error_count += 1

            if error_type == "policy_error":
                state.force_repair_mode = True
                state.consecutive_policy_errors += 1
            else:
                state.consecutive_policy_errors = 0

            msgs.append({"role": "user", "content": build_repair_prompt(action, res_data)})
            return state, msgs

        state.error_count = 0
        state.last_error = None
        state.consecutive_policy_errors = 0
        if action != "plan":
            state.force_repair_mode = False
        return state, msgs
