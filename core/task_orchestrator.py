# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, List

from core.config import Config


class TaskOrchestrator:
    """Builds task-scoped prompt/messages and keeps orchestration text centralized."""

    @staticmethod
    def build_mission_prompt(task: str) -> str:
        return (
            "MISSION REQUIREMENTS:\n"
            "1) You must call the `plan` action early with concrete steps.\n"
            "2) For each major step, explicitly check whether it is completed.\n"
            "3) Only call `mark_done` when all planned items are completed.\n\n"
            "4) Every plan must end in exactly one terminal step:\n"
            "   - CALL mark_done (with completion evidence), OR\n"
            "   - BLOCKED: <single blocking reason>.\n"
            "5) Do not produce plans without a terminal step.\n\n"
            f"USER TASK:\n{task}"
        )

    @staticmethod
    def build_env_lock_message(shell_profile: str, root_dir: str) -> str:
        return (
            f"ENV CACHE LOCKED ONCE: shell_profile={shell_profile}, root_dir={root_dir}. "
            "Prefer workspace-safe commands and keep tool arguments exact.\n"
            "CHEAT SHEET:\n"
            "- Windows shell: dir /b, dir /s /b, type <file>, findstr <pattern> <file>\n"
            "- Unix shell: ls, find . -maxdepth 3 -type f, cat <file>, head -n 50 <file>\n"
            "- Avoid cross-platform mixing (e.g., don't use dir on Unix or find/grep on Windows)."
        )

    def build_initial_messages(self, task: str, shell_profile: str, root_dir: str) -> List[Dict[str, str]]:
        msgs: List[Dict[str, str]] = [
            {"role": "system", "content": Config.SYSTEM_PROMPT},
            {"role": "user", "content": self.build_mission_prompt(task)},
            {"role": "user", "content": self.build_env_lock_message(shell_profile, root_dir)},
        ]
        return msgs
