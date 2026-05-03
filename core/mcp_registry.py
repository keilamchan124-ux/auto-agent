from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, List, Set


DEFAULT_MCP_REGISTRY: List[Dict[str, str]] = [
    {"name": "context7", "role": "Source-grounded documentation lookup."},
    {"name": "codegeneratormcp", "role": "Code generation and scaffold acceleration for implementation tasks."},
    {"name": "github", "role": "Repository, PR, and issue context/actions (optional third core)."},
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


def _load_registry_from_env_or_file() -> List[Dict[str, str]]:
    """
    Optional override sources (in precedence order):
    1) MCP_REGISTRY_JSON: JSON array string
    2) MCP_REGISTRY_FILE: path to json file (default: mcp_registry.json)
    Fallback: DEFAULT_MCP_REGISTRY
    """
    raw_json = os.getenv("MCP_REGISTRY_JSON", "").strip()
    if raw_json:
        try:
            data = json.loads(raw_json)
            if isinstance(data, list):
                rows = [r for r in data if isinstance(r, dict) and r.get("name")]
                if rows:
                    return [{"name": str(r["name"]), "role": str(r.get("role", ""))} for r in rows]
        except Exception:
            pass

    registry_file = os.getenv("MCP_REGISTRY_FILE", "mcp_registry.json").strip()
    if registry_file:
        p = Path(registry_file)
        if not p.is_absolute():
            p = Path.cwd() / p
        if p.exists():
            try:
                data = json.loads(p.read_text("utf-8"))
                if isinstance(data, list):
                    rows = [r for r in data if isinstance(r, dict) and r.get("name")]
                    if rows:
                        return [{"name": str(r["name"]), "role": str(r.get("role", ""))} for r in rows]
            except Exception:
                pass

    return list(DEFAULT_MCP_REGISTRY)


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
    registry = _load_registry_from_env_or_file()
    name_to_item: Dict[str, Dict[str, str]] = {m["name"].lower(): m for m in registry}

    raw = os.getenv("MCP_SERVERS", "").strip()
    if not raw:
        return list(registry)

    wanted = _normalize_requested_names(raw)
    # Preserve registry ordering while filtering + deduplicating.
    return [m for m in registry if m["name"].lower() in wanted and m["name"].lower() in name_to_item]
