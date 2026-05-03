# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Set, Tuple


class McpPolicyEngine:
    DEFAULT_MCP_REGISTRY: List[Dict[str, str]] = [
        {"name": "context7", "role": "Source-grounded documentation lookup."},
        {"name": "codegeneratormcp", "role": "Code generation and scaffold acceleration for implementation tasks."},
        {"name": "github", "role": "Repository, PR, and issue context/actions (optional third core)."},
    ]
    _ALIASES: Dict[str, str] = {
        "chrome": "chrome-devtools",
        "devtools": "chrome-devtools",
        "visual": "web-visual-feedback",
        "web-visual": "web-visual-feedback",
        "codegen": "codegeneratormcp",
        "code-generator": "codegeneratormcp",
    }

    @classmethod
    def _normalize_requested_names(cls, raw: str) -> Set[str]:
        names: Set[str] = set()
        for part in raw.split(","):
            p = part.strip().lower()
            if not p:
                continue
            names.add(cls._ALIASES.get(p, p))
        return names

    @classmethod
    def get_enabled_registry(cls) -> List[Dict[str, str]]:
        raw = os.getenv("MCP_SERVERS", "").strip()
        if not raw:
            return list(cls.DEFAULT_MCP_REGISTRY)
        wanted = cls._normalize_requested_names(raw)
        return [m for m in cls.DEFAULT_MCP_REGISTRY if m["name"].lower() in wanted]

    @staticmethod
    def enforce_mcp_phase_hard_gate(action: str, step: int, is_ui_verify_phase_fn: Callable[[int], bool]) -> Tuple[bool, str]:
        browser_like_actions = {"capture_web_screenshot", "start_web_server", "stop_web_server", "web_server_status"}
        if action in browser_like_actions and not is_ui_verify_phase_fn(step):
            return False, (
                "MCP_PHASE_POLICY_VIOLATION: Browser/UI verification tools are only allowed in UI verify phase "
                "(Stitch cadence steps 8/9/10). Continue with implementation-phase actions first."
            )
        return True, ""

    @staticmethod
    def build_mcp_routing_directive(task: str, enabled_mcps: List[Dict[str, str]]) -> str:
        names = {m.get("name", "").lower() for m in enabled_mcps}
        t = (task or "").lower()
        directives = []
        if "context7" in names and any(k in t for k in ["docs", "documentation", "api", "sdk", "reference"]):
            directives.append("Use Context7 MCP early for source-grounded documentation lookups.")
        if "github" in names and any(k in t for k in ["pr", "pull request", "issue", "repository", "github"]):
            directives.append("Use GitHub MCP early for repository/PR/issue context.")
        if "codegeneratormcp" in names and any(k in t for k in ["implement", "refactor", "scaffold", "generate", "build", "python", "pytest", "pydantic", "fastapi", "flask", ".py"]):
            directives.append("Use CodeGeneratorMCP first in implementation phase for code drafting/patch acceleration (especially Python tasks).")
        if "chrome-devtools" in names and any(k in t for k in ["ui", "browser", "dom", "console", "screenshot", "visual"]):
            directives.append("Use Chrome DevTools MCP during UI verify phase only.")
        if "semgrep" in names and any(k in t for k in ["security", "vulnerability", "hardening", "injection"]):
            directives.append("Run Semgrep MCP checks before mark_done for security-sensitive tasks.")
        if not directives:
            return ""
        return "[MCP ROUTING DIRECTIVE]\n" + "\n".join([f"- {d}" for d in directives])

    @staticmethod
    def enforce_mcp_usage_floor(action: str, step: int, task: str, enabled_mcps: List[Dict[str, str]]) -> Tuple[bool, str]:
        if step > 8:
            return True, ""
        names = {m.get("name", "").lower() for m in enabled_mcps}
        t = (task or "").lower()
        repo_signals = [r"\bgithub\b", r"github\.com/", r"\bowner/[a-z0-9_.-]+\b", r"\bpull request\b"]
        has_repo_signal = any(re.search(p, t) for p in repo_signals)
        if "github" in names and has_repo_signal:
            github_actions = {"github_read_file", "github_clone", "github_create_pr", "github_commit_push"}
            if action not in github_actions and action not in {"plan", "read_file"}:
                return False, (
                    "MCP_USAGE_REQUIRED: This task is repository-centric. Use a GitHub MCP action early "
                    "(github_read_file/github_clone/github_create_pr/github_commit_push) before generic actions."
                )
        if "codegeneratormcp" in names and any(k in t for k in ["python", ".py", "pytest", "fastapi", "flask", "refactor", "implement", "write code", "coding"]):
            codegen_like = action.startswith("codegenerator") or ("codegen" in action) or action in {"plan", "read_file"}
            if not codegen_like:
                return False, (
                    "MCP_USAGE_REQUIRED: This task is code-implementation heavy (especially Python). "
                    "Use a CodeGeneratorMCP action early before generic execution actions."
                )
        if "chrome-devtools" in names and any(k in t for k in ["ui", "browser", "dom", "screenshot", "visual"]):
            ui_actions = {"capture_web_screenshot", "web_server_status", "start_web_server"}
            if action not in ui_actions and action not in {"plan", "run_cmd", "read_file"}:
                return False, (
                    "MCP_USAGE_REQUIRED: This task is UI-centric. Use a UI verification action early "
                    "(start_web_server/capture_web_screenshot/web_server_status)."
                )
        return True, ""
