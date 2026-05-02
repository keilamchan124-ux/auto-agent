# -*- coding: utf-8 -*-
from __future__ import annotations

import re


def detect_task_mode(task: str) -> str:
    """Detect task mode from explicit schema header.

    Expected format: [MODE]=STITCH_FLUTTER (or GENERAL).
    """
    match = re.search(r"^\s*\[MODE\]\s*=\s*([A-Z0-9_]+)\s*$", task, re.MULTILINE)
    if not match:
        return "general"
    mode = match.group(1).strip().upper()
    if mode in {"STITCH_FLUTTER", "MOBILE"}:
        return "mobile"
    return "general"
