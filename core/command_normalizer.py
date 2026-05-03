# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class NormalizeRule:
    pattern: str
    replacement: str
    target_binary: str


class CommandNormalizer:
    """Centralized Windows/Unix command normalization rules."""

    WINDOWS_RULES: List[NormalizeRule] = [
        NormalizeRule(r"^\s*cat\b", "type", "type"),
        NormalizeRule(r"^\s*pwd\s*$", "cd", "cd"),
        NormalizeRule(r"^\s*find\b.*$", "dir /s /b", "dir"),
        NormalizeRule(r"^\s*grep\b", "findstr", "findstr"),
    ]
    UNIX_RULES: List[NormalizeRule] = [
        NormalizeRule(r"^\s*dir\b", "ls", "ls"),
        NormalizeRule(r"^\s*type\b", "cat", "cat"),
        NormalizeRule(r"^\s*findstr\b", "grep", "grep"),
    ]

    @classmethod
    def normalize(cls, cmd: str, is_windows: bool) -> Tuple[str, str]:
        raw = str(cmd or "").strip()
        if not raw:
            return cmd, ""

        # Specialized ls handling to strip Unix flags on Windows.
        if is_windows and re.match(r"^\s*ls\b", raw, flags=re.IGNORECASE):
            tokens = shlex.split(raw, posix=False)
            non_flags = [t for t in tokens[1:] if not str(t).startswith("-")]
            target = non_flags[0] if non_flags else ""
            return f"dir {target}".strip(), "dir"

        rules = cls.WINDOWS_RULES if is_windows else cls.UNIX_RULES
        for rule in rules:
            if re.match(rule.pattern, raw, flags=re.IGNORECASE):
                next_cmd = re.sub(rule.pattern, rule.replacement, raw, count=1, flags=re.IGNORECASE)
                return next_cmd.strip(), rule.target_binary
        return cmd, ""
