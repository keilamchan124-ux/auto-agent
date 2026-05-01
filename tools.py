# -*- coding: utf-8 -*-
import inspect
import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict

import requests
from ddgs import DDGS

from config import Config

logger = logging.getLogger("Tools")


def format_result(ok: bool, message: str, data: Dict[str, Any] = None, error_type: str = None) -> str:
    """
    統一結構化回傳，保持 JSON string。
    """
    res: Dict[str, Any] = {
        "ok": bool(ok),
        "message": str(message),
    }
    if data is not None:
        res["data"] = data
    if not ok:
        res["error_type"] = error_type or "unknown_error"
    return json.dumps(res, ensure_ascii=False)


def _workspace_root() -> Path:
    return Config.WORKSPACE_DIR.resolve()


def safe_path(p: str) -> Path:
    """
    限制所有檔案操作只可喺 workspace 入面。
    """
    root = _workspace_root()
    full = (root / p).resolve()

    try:
        if not full.is_relative_to(root):
            raise ValueError("Security Violation")
    except AttributeError:
        # Python < 3.9 fallback
        if root != full and root not in full.parents:
            raise ValueError("Security Violation")

    return full


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]


def web_search(q: str) -> str:
    """
    網頁搜尋：回傳少量、結構化摘要，避免 context 爆大。
    """
    try:
        q = str(q).strip()
        if not q:
            return format_result(False, "Empty query.", error_type="search_error")

        with DDGS() as d:
            results = list(d.text(q, max_results=3))

        data = []
        for r in results:
            data.append({
                "title": _truncate(str(r.get("title", "")), 160),
                "body": _truncate(str(r.get("body", "")), 260),
                "href": _truncate(str(r.get("href", "")), 300),
            })

        message = "Search completed." if data else "No result found."
        return format_result(True, message, data=data)
    except Exception as e:
        return format_result(False, str(e), error_type="search_error")


def download_file(url: str, path: str) -> str:
    """
    下載檔案，阻止 HTML 頁面被當成檔案寫入。
    """
    try:
        p = safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True, timeout=20) as r:
            r.raise_for_status()

            ctype = r.headers.get("Content-Type", "").lower()
            if "text/html" in ctype:
                return format_result(
                    False,
                    "Failed: URL is a webpage, not a direct file.",
                    error_type="invalid_mime"
                )

            with open(p, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        return format_result(True, f"Downloaded to {path}")
    except Exception as e:
        return format_result(False, str(e), error_type="download_error")


def run_cmd(cmd: str) -> str:
    """
    只允許白名單 binary。
    """
    try:
        cmd = str(cmd).strip()
        if not cmd:
            return format_result(False, "Empty command.", error_type="execution_error")

        args = shlex.split(cmd)
        if not args:
            return format_result(False, "Empty command.", error_type="execution_error")

        if args[0] not in Config.ALLOWED_BINARIES:
            return format_result(False, "Forbidden command.", error_type="security_error")

        r = subprocess.run(
            args,
            cwd=Config.WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )

        out = (r.stdout + r.stderr).strip()
        if not out:
            out = "Success"

        return format_result(True, _truncate(out, 1200))
    except subprocess.TimeoutExpired:
        return format_result(False, "Command timed out.", error_type="timeout_error")
    except Exception as e:
        return format_result(False, str(e), error_type="execution_error")


def write_file(path: str, content: str) -> str:
    try:
        p = safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8")
        return format_result(True, f"Wrote to {path}")
    except Exception as e:
        return format_result(False, str(e), error_type="io_error")


def read_file(path: str) -> str:
    try:
        p = safe_path(path)
        if not p.exists():
            return format_result(False, "File not found.", error_type="io_error")
        if not p.is_file():
            return format_result(False, "Path is not a file.", error_type="io_error")

        text = p.read_text(encoding="utf-8", errors="replace")
        return format_result(True, _truncate(text, 5000))
    except Exception as e:
        return format_result(False, str(e), error_type="io_error")


TOOLS_REGISTRY = {
    "web_search": web_search,
    "download_file": download_file,
    "run_cmd": run_cmd,
    "write_file": write_file,
    "read_file": read_file,
}


def execute_tool(action: str, kwargs: dict) -> str:
    """
    Schema 硬約束：
    - 忽略多餘參數
    - 支援少量 alias
    - 永遠回傳 JSON string
    """
    if action not in TOOLS_REGISTRY:
        return format_result(False, f"Tool {action} not found.", error_type="tool_not_found")

    func = TOOLS_REGISTRY[action]
    sig = inspect.signature(func)

    if not isinstance(kwargs, dict):
        kwargs = {}

    alias_map = {
        "query": "q",
        "search_term": "q",
        "filepath": "path",
    }

    normalized = {alias_map.get(k, k): v for k, v in kwargs.items()}
    valid_kwargs = {k: v for k, v in normalized.items() if k in sig.parameters}

    try:
        return func(**valid_kwargs)
    except Exception as e:
        return format_result(False, str(e), error_type="runtime_error")