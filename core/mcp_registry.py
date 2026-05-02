from __future__ import annotations

import os
from typing import Dict, List, Set


DEFAULT_MCP_REGISTRY: List[Dict[str, str]] = [
    {"name": "chrome-devtools", "role": "Browser runtime inspection (DOM/console/network/perf)."},
    {"name": "github", "role": "Repository, PR, and issue context/actions."},
    {"name": "web-visual-feedback", "role": "Screenshot-based UI verification and feedback loops."},
    {"name": "context7", "role": "Source-grounded documentation lookup."},
    {"name": "codegeneratormcp", "role": "Code generation and scaffold acceleration for implementation tasks."},
    {"name": "semgrep", "role": "Security/static analysis checks before merge."},
]

_NAME_TO_ITEM: Dict[str, Dict[str, str]] = {m["name"].lower(): m for m in DEFAULT_MCP_REGISTRY}
_ALIASES: Dict[str, str] = {
    "chrome": "chrome-devtools",
    "devtools": "chrome-devtools",
    "visual": "web-visual-feedback",
    "web-visual": "web-visual-feedback",
    "codegen": "codegeneratormcp",
    "code-generator": "codegeneratormcp",
}


def _normalize_requested_names(raw: str) -> Set[str]:
    names: Set[str] = set()
    for part in raw.split(","):
        p = part.strip().lower()
        if not p:
            continue
        canonical = _ALIASES.get(p, p)
        names.add(canonical)
    return names


def get_enabled_mcp_registry() -> List[Dict[str, str]]:
    """
    Return enabled MCP server descriptors.
    - If MCP_SERVERS is provided (comma-separated), keep only those names.
    - Otherwise return the default recommended set.
    """
    raw = os.getenv("MCP_SERVERS", "").strip()
    if not raw:
        return list(DEFAULT_MCP_REGISTRY)

    wanted = _normalize_requested_names(raw)
    # Preserve default registry ordering while filtering + deduplicating.
    return [m for m in DEFAULT_MCP_REGISTRY if m["name"].lower() in wanted]
