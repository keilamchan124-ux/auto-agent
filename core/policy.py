# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Literal

TaskMode = Literal["general", "mobile", "stitch_flutter"]


def detect_task_mode(task: str) -> TaskMode:
    """Detect task mode from explicit schema header.

    Expected format: [MODE]=STITCH_FLUTTER (or MOBILE/GENERAL).
    """
    match = re.search(r"^\s*\[MODE\]\s*=\s*([A-Z0-9_]+)\s*$", task, re.MULTILINE)
    if not match:
        return "general"

    mode = match.group(1).strip().upper()
    if mode == "STITCH_FLUTTER":
        return "stitch_flutter"
    if mode == "MOBILE":
        return "mobile"
    if mode == "GENERAL":
        return "general"
    return "general"
