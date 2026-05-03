# -*- coding: utf-8 -*-
from __future__ import annotations
import functools
import inspect
import json
import logging
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import requests
from ddgs import DDGS
from markitdown import MarkItDown

from core.config import Config
from core.command_normalizer import CommandNormalizer

logger = logging.getLogger("Tools")
_POLICY_ERROR_STREAK = {"type": None, "count": 0}


def _build_policy_repair_action(policy_type: str, detail: str) -> Dict[str, Any]:
    """Return an actionable next tool call suggestion for policy failures."""
    d = str(detail or "")
    if policy_type == "path":
        if "workspace/" in d:
            return {
                "action": "plan",
                "kwargs": {
                    "steps": (
                        "Convert target paths to cwd-relative form. "
                        "Remove leading workspace/ prefix and retry the same tool."
                    )
                },
                "reason": "Path policy typically fails due to workspace-prefixed or unsafe absolute paths.",
            }
        return {
            "action": "read_file",
            "kwargs": {"path": "README.md"},
            "reason": "Read project docs first, then retry with a workspace-safe relative path.",
        }
    if policy_type == "command":
        if "windows" in d.lower():
            steps = "Switch to Windows-safe command equivalents (dir/type) and rerun run_cmd."
        elif "unix" in d.lower():
            steps = "Switch to Unix-safe command equivalents (ls/cat) and rerun run_cmd."
        else:
            steps = "Rewrite command using allowlisted binaries and retry run_cmd."
        return {
            "action": "plan",
            "kwargs": {"steps": steps},
            "reason": "Command policy failures are usually solved by command normalization.",
        }
    return {
        "action": "plan",
        "kwargs": {"steps": "Summarize policy error root cause and perform one concrete safe retry."},
        "reason": "General policy remediation fallback.",
    }


def _policy_repair_template(policy_type: str, detail: str) -> str:
    repair_action = _build_policy_repair_action(policy_type, detail)
    return format_result(
        False,
        f"POLICY REPAIR REQUIRED ({policy_type}): {detail}",
        error_type="policy_error",
        data={
            "repair_template": {
                "mode": "forced",
                "options": [
                    "A: path fix",
                    "B: command fix",
                    "C: environment verify",
                ],
            }
            ,
            "suggested_repair_action": repair_action,
        },
    )


def _track_policy_error(policy_type: str, detail: str) -> str:
    if _POLICY_ERROR_STREAK["type"] == policy_type:
        _POLICY_ERROR_STREAK["count"] += 1
    else:
        _POLICY_ERROR_STREAK["type"] = policy_type
        _POLICY_ERROR_STREAK["count"] = 1
    if _POLICY_ERROR_STREAK["count"] >= 2:
        return _policy_repair_template(policy_type, detail)
    return format_result(False, detail, error_type="policy_error")


def _reset_policy_error_streak() -> None:
    _POLICY_ERROR_STREAK["type"] = None
    _POLICY_ERROR_STREAK["count"] = 0


def format_result(ok: bool, message: str, data: Dict[str, Any] = None, error_type: str = None) -> str:
    """Unified structured JSON-string response."""
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
    """Restrict all file operations to workspace."""
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


def _canonicalize_workspace_path(path: str) -> str:
    """
    Normalize duplicated workspace prefixes:
    - workspace/workspace/foo -> workspace/foo
    - workspace\\workspace\\foo -> workspace/foo
    """
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("workspace/workspace/"):
        normalized = normalized[len("workspace/"):]
    return normalized


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]


def _extract_key_lines(text: str, max_lines: int = 12) -> list[str]:
    lines = text.splitlines()
    key = []
    markers = ("#", "##", "###", "def ", "class ", "function", "return", "error", "warning")
    for ln in lines:
        s = ln.strip()
        if s and any(m in s.lower() for m in markers):
            key.append(s)
        if len(key) >= max_lines:
            break
    return key


def _smart_file_summary(text: str, head: int = 60, tail: int = 20) -> dict:
    lines = text.splitlines()
    total = len(lines)
    head_block = lines[:head]
    tail_block = lines[-tail:] if total > head else []
    funcs = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("def ") or s.startswith("class "):
            funcs.append(s[:120])
        if len(funcs) >= 20:
            break
    return {
        "summary": "\n".join(head_block + (["..."] if tail_block else []) + tail_block),
        "total_lines": total,
        "important_symbols": funcs,
    }


def browse_page(url: str, full_output: bool = True) -> str:
    """Fetch a page and convert it to clean Markdown (HTML/PDF/etc)."""
    try:
        url = str(url).strip()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        ctype = resp.headers.get("Content-Type", "").lower()
        if "application/pdf" in ctype:
            ext = ".pdf"
        elif "text/html" in ctype:
            ext = ".html"
        else:
            ext = ".txt"

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        try:
            md = MarkItDown()
            result = md.convert(tmp_path)
            content = result.text_content
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        if full_output:
            return format_result(True, f"Successfully fetched {url}", data={"url": url, "content": _truncate(content, 30000), "mode": "full"})

        lead = _truncate(content, 3000)
        key = _extract_key_lines(content, max_lines=12)
        compact = lead + ("\n\n[Key excerpts]\n- " + "\n- ".join(key) if key else "")
        return format_result(True, f"Successfully fetched {url}", data={"url": url, "content": compact, "mode": "smart_summary"})
    except Exception as e:
        return format_result(False, f"Failed to fetch {url}: {e}", error_type="network_error")


@functools.lru_cache(maxsize=16)
def web_search(q: str, full_output: bool = True) -> str:
    """Web search with compact structured output to reduce context size."""
    try:
        q = str(q).strip()
        if not q:
            return format_result(False, "Empty query.", error_type="search_error")

        with DDGS() as d:
            results = list(d.text(q, max_results=10))

        data = []
        selected = results if full_output else results[:5]
        for r in selected:
            data.append({
                "title": _truncate(str(r.get("title", "")), 160),
                "body": _truncate(str(r.get("body", "")), 160),
                "href": _truncate(str(r.get("href", "")), 300),
            })

        message = "Search completed." if data else "No result found."
        return format_result(True, message, data={"results": data, "count": len(data), "mode": "full" if full_output else "lean_top5"})
    except Exception as e:
        return format_result(False, str(e), error_type="search_error")


def download_file(url: str, path: str) -> str:
    """Download a file and block accidental HTML-page downloads."""
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


def _friendly_exec_error(err: Exception, cmd: str) -> str:
    text = str(err)
    lowered = text.lower()

    if "winerror 2" in lowered or "no such file or directory" in lowered:
        return (
            f"Command not found: {cmd}. "
            "Tip: on Windows, use built-ins like `dir` (cmd.exe) or executables available in PATH."
        )

    if "timed out" in lowered:
        return f"Command timed out: {cmd}. Tip: simplify the command or split it into smaller steps."

    return f"Failed to execute command: {cmd}. Details: {text}"


def _normalize_cross_platform_cmd(cmd: str, is_windows: bool) -> tuple[str, str]:
    """Translate common cross-platform shell commands into safe local equivalents."""
    raw = cmd.strip()
    if is_windows:
        if re.match(r"^\s*ls\b", raw, flags=re.IGNORECASE):
            tokens = shlex.split(raw, posix=False)
            non_flags = [t for t in tokens[1:] if not str(t).startswith("-")]
            target = non_flags[0] if non_flags else ""
            return f"dir {target}".strip(), "dir"
        if re.match(r"^\s*cat\b", raw, flags=re.IGNORECASE):
            return re.sub(r"^\s*cat\b", "type", raw, flags=re.IGNORECASE), "type"
        if re.match(r"^\s*pwd\s*$", raw, flags=re.IGNORECASE):
            return "cd", "cd"
        if re.match(r"^\s*find\b", raw, flags=re.IGNORECASE):
            return "dir /s /b", "dir"
        if re.match(r"^\s*grep\b", raw, flags=re.IGNORECASE):
            return re.sub(r"^\s*grep\b", "findstr", raw, flags=re.IGNORECASE), "findstr"
    else:
        if re.match(r"^\s*dir\b", raw, flags=re.IGNORECASE):
            return re.sub(r"^\s*dir\b", "ls", raw, flags=re.IGNORECASE), "ls"
        if re.match(r"^\s*type\b", raw, flags=re.IGNORECASE):
            return re.sub(r"^\s*type\b", "cat", raw, flags=re.IGNORECASE), "cat"
        if re.match(r"^\s*findstr\b", raw, flags=re.IGNORECASE):
            return re.sub(r"^\s*findstr\b", "grep", raw, flags=re.IGNORECASE), "grep"
    return cmd, ""


def run_cmd(cmd: str) -> str:
    """Execute shell command with binary allowlist and cross-platform normalization."""
    try:
        cmd = str(cmd).strip()
        if not cmd:
            return format_result(False, "Empty command.", error_type="execution_error")

        is_windows = os.name == "nt"

        windows_allow = {"dir", "type", "findstr"}
        unix_allow = {"ls", "cat", "grep", "find", "head"}

        if is_windows:
            args = shlex.split(cmd, posix=False)
            if not args:
                return format_result(False, "Empty command.", error_type="execution_error")
            binary = args[0].strip("\"'").lower()
            if binary == "mkdir" and len(args) >= 3 and args[1] == "-p":
                target = _canonicalize_workspace_path(" ".join(args[2:]).strip("\"'"))
                py = f"import os; os.makedirs(r'''{target}''', exist_ok=True); print('ok')"
                cmd = f'python -c "{py}"'
                binary = "python"
            if binary == "ls":
                binary = "dir"
                cmd = "dir" if len(args) == 1 else f"dir {' '.join(args[1:])}"
            elif binary == "cat" and "<<" in cmd:
                return format_result(
                    False,
                    "Heredoc pattern is not supported on Windows run_cmd. Use write_file(path=..., content=...) instead.",
                    error_type="policy_error",
                )
            elif binary == "cat":
                binary = "type"
                cmd = "type" if len(args) == 1 else f"type {' '.join(args[1:])}"
            elif binary == "pwd":
                binary = "cd"
                cmd = "cd"
            elif binary == "find" and "|" in cmd and "head" in cmd:
                cmd = "dir /s /b"
                binary = "dir"
        else:
            args = shlex.split(cmd)
            if not args:
                return format_result(False, "Empty command.", error_type="execution_error")
            binary = args[0].lower()

        if binary in {"ls", "dir", "mkdir", "md", "cat", "type"}:
            # Allow standard listing commands directly; this reduces unproductive
            # policy loops and mirrors common shell usage.
            pass

        # Cross-platform command normalization to reduce repetitive policy failures.
        normalized_cmd, normalized_binary = CommandNormalizer.normalize(cmd, is_windows=is_windows)
        if normalized_binary:
            cmd = normalized_cmd
            binary = normalized_binary
            args = shlex.split(cmd, posix=False) if is_windows else shlex.split(cmd)

        # OS-specific safety gate: block cross-platform shell dialect mismatch.
        if is_windows and binary in unix_allow and binary != "ls":
            return _track_policy_error("command", f"Cross-platform command blocked on Windows: {binary}")
        if (not is_windows) and binary in windows_allow and binary != "dir":
            return _track_policy_error("command", f"Cross-platform command blocked on Unix: {binary}")

        if binary == "cd":
            # Support `cd <path>` and `cd <path> && <command...>` while keeping
            # command allowlist/sandbox checks for the actual executable.
            if is_windows:
                split_token = "&&" if "&&" in cmd else None
                parts = [p.strip() for p in cmd.split(split_token, 1)] if split_token else [cmd]
                if not parts or len(parts[0].split()) < 2:
                    return format_result(False, "Invalid cd usage. Example: `cd subdir && python -m pytest`.", error_type="execution_error")
                cd_target = parts[0][len("cd"):].strip().strip("\"'")
                next_cmd = parts[1].strip() if split_token and len(parts) > 1 else ""
            else:
                if "&&" in cmd:
                    lhs, rhs = cmd.split("&&", 1)
                    lhs, next_cmd = lhs.strip(), rhs.strip()
                else:
                    lhs, next_cmd = cmd, ""
                lhs_args = shlex.split(lhs)
                if len(lhs_args) < 2:
                    return format_result(False, "Invalid cd usage. Example: `cd subdir && python -m pytest`.", error_type="execution_error")
                cd_target = lhs_args[1]

            target_dir = (Config.WORKSPACE_DIR / cd_target).resolve()
            workspace_root = Config.WORKSPACE_DIR.resolve()
            try:
                target_dir.relative_to(workspace_root)
            except ValueError:
                return format_result(False, "cd target must stay inside workspace.", error_type="security_error")
            if not target_dir.exists() or not target_dir.is_dir():
                return format_result(False, f"Directory not found: {cd_target}", error_type="execution_error")

            if not next_cmd:
                rel = target_dir.relative_to(workspace_root)
                rel_display = "." if str(rel) == "." else str(rel)
                return format_result(True, f"Changed directory to {rel_display}")

            if is_windows:
                next_args = shlex.split(next_cmd, posix=False)
            else:
                next_args = shlex.split(next_cmd)
            if not next_args:
                return format_result(False, "Missing command after cd.", error_type="execution_error")
            binary = next_args[0].strip("\"'").lower()
            cmd = next_cmd
            args = next_args
            cwd_override = target_dir
        else:
            cwd_override = Config.WORKSPACE_DIR

        pytest_allowed = False
        if binary == "pytest":
            pytest_allowed = True
        elif binary in {"python", "python3"}:
            # Only allow explicit pytest module invocation, e.g.:
            # - python -m pytest
            # - python3 -m pytest tests/test_x.py
            normalized_args = [str(x).strip().lower() for x in (args[1:] if not is_windows else shlex.split(cmd, posix=False)[1:])]
            if len(normalized_args) >= 2 and normalized_args[0] == "-m" and normalized_args[1] == "pytest":
                pytest_allowed = True

        if pytest_allowed:
            pass
        elif binary not in Config.ALLOWED_BINARIES:
            return format_result(False, "Forbidden command.", error_type="security_error")

        if is_windows:
            r = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd_override,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            r = subprocess.run(
                args,
                cwd=cwd_override,
                capture_output=True,
                text=True,
                timeout=30
            )

        stderr_text = (r.stderr or "").strip()
        out = ((r.stdout or "") + stderr_text).strip()
        if not out:
            out = "Success"

        stderr_lower = stderr_text.lower()
        stderr_cmd_not_found = any(x in stderr_lower for x in [
            "not recognized as an internal or external command",
            "is not recognized",
            "command not found",
            "不是內部或外部命令",
        ])
        if stderr_cmd_not_found:
            return format_result(False, _truncate(out, 1200), error_type="execution_error")

        known_cli_error = any(x in out.lower() for x in [
            "not recognized as an internal or external command",
            "不是內部或外部命令",
            "invalid parameter",
            "參數格式不正確",
            "無效的參數",
            "系統找不到指定的路徑",
            "no such file or directory",
        ])
        if r.returncode != 0 or known_cli_error:
            return format_result(False, _truncate(out, 1200), error_type="execution_error")
        _reset_policy_error_streak()
        return format_result(True, _truncate(out, 1200))
    except subprocess.TimeoutExpired as e:
        return format_result(False, _friendly_exec_error(e, cmd), error_type="timeout_error")
    except Exception as e:
        return format_result(False, _friendly_exec_error(e, cmd), error_type="execution_error")


def write_file(path: str, content: str) -> str:
    try:
        path = _canonicalize_workspace_path(path)
        normalized = str(path).replace("\\", "/")
        cwd = str(Config.WORKSPACE_DIR).replace("\\", "/")
        if cwd.endswith("/workspace") and normalized.startswith("workspace/demo_counter_app"):
            return _track_policy_error("path", "Use cwd-relative create-project path (demo_counter_app/...), not workspace/demo_counter_app/...")
        p = safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8")
        return format_result(True, f"Wrote to {path}")
    except Exception as e:
        return format_result(False, str(e), error_type="io_error")


def read_file(path: str, full_output: bool = True) -> str:
    try:
        if not path:
            return format_result(False, "Empty path.", error_type="io_error")
        path = _canonicalize_workspace_path(path)
        normalized = str(path).replace("\\", "/")
        cwd = str(Config.WORKSPACE_DIR).replace("\\", "/")
        if cwd.endswith("/workspace") and normalized.startswith("workspace/"):
            stripped = normalized[len("workspace/"):]
            if not stripped:
                return _track_policy_error("path", "Path rule violation: empty path after workspace/ prefix.")
            normalized = stripped
            path = stripped
        p = safe_path(path)
        if not p.exists():
            return format_result(False, "File not found.", error_type="io_error")
        if not p.is_file():
            return format_result(False, "Path is not a file.", error_type="io_error")

        text = p.read_text(encoding="utf-8", errors="replace")
        if full_output:
            return format_result(True, "Read file success.", data={"content": _truncate(text, 30000), "mode": "full"})
        summary = _smart_file_summary(text, head=80, tail=20)
        _reset_policy_error_streak()
        return format_result(
            True,
            "Read file success.",
            data={
                "content": summary["summary"],
                "total_lines": summary["total_lines"],
                "important_symbols": summary["important_symbols"],
                "mode": "lean_regions",
            },
        )
    except Exception as e:
        return format_result(False, str(e), error_type="io_error")


def run_python_script(code: str, full_output: bool = True) -> str:
    """Run Python code with optional network guard."""
    try:
        if not code:
            return format_result(False, "Empty code.", error_type="execution_error")

        # If ALLOWED_DOMAINS is restricted, inject a network guard.
        if Config.ALLOWED_DOMAINS and "*" not in Config.ALLOWED_DOMAINS:
            guard_code = """
import socket
_orig_connect = socket.socket.connect
_ALLOWED_DOMAINS = """ + str(Config.ALLOWED_DOMAINS) + """
def _safe_connect(self, address):
    host = address[0]
    if isinstance(host, str):
        allowed = any(host == d or host.endswith('.' + d) for d in _ALLOWED_DOMAINS)
        if not allowed:
            raise PermissionError(f"Security Violation: Access to '{host}' is blocked by ALLOWED_DOMAINS policy.")
    return _orig_connect(self, address)
socket.socket.connect = _safe_connect
"""
            # Place guard code at the top of generated script.
            code = guard_code.strip() + "\n\n" + code

        script_path = safe_path(".temp_agent_script.py")
        script_path.write_text(code, encoding="utf-8")

        # Prefer platform-appropriate Python launcher.
        if os.name == "nt":
            if "py" in Config.ALLOWED_BINARIES:
                run_args = ["py", "-3", str(script_path)]
            elif "python" in Config.ALLOWED_BINARIES:
                run_args = ["python", str(script_path)]
            else:
                run_args = ["python3", str(script_path)]
        else:
            run_args = ["python3", str(script_path)] if "python3" in Config.ALLOWED_BINARIES else ["python", str(script_path)]

        r = subprocess.run(
            run_args,
            cwd=Config.WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )

        out = (r.stdout + "\n" + r.stderr).strip() or "Success (No output)"
        if r.returncode != 0:
            stderr_lines = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            last_stderr = stderr_lines[-1] if stderr_lines else ""
            detail = f"returncode={r.returncode}"
            if last_stderr:
                detail += f"; last_stderr={last_stderr}"
            return format_result(False, _truncate(f"{detail}\n{out}", 12000), error_type="execution_error")
        if full_output:
            return format_result(True, _truncate(out, 12000), data={"mode": "full"})
        top20 = "\n".join(out.splitlines()[:20])
        return format_result(True, _truncate(top20, 4000), data={"mode": "lean_top20_lines"})
    except Exception as e:
        return format_result(False, str(e), error_type="execution_error")


def load_preset(preset_name: str) -> str:
    """Load multiple skills from a preset."""
    try:
        preset_name = str(preset_name).strip()
        presets = getattr(Config, "SKILL_PRESETS", {})
        if preset_name not in presets:
            return format_result(False, f"Preset '{preset_name}' not found. Available: {list(presets.keys())}", error_type="not_found")
        
        md = MarkItDown()
        
        combined_content = []
        for skill_name in presets[preset_name]:
            skill_dir = Config.SKILLS_DIR / skill_name
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                matches = list(skill_dir.glob("SKILL.*"))
                if matches:
                    skill_file = matches[0]
                else:
                    continue
            
            result = md.convert(str(skill_file))
            combined_content.append(f"--- SKILL: {skill_name} ---\n{result.text_content}")
            
        final_text = "\n\n".join(combined_content)
        return format_result(True, f"Loaded preset '{preset_name}' ({len(presets[preset_name])} skills).", data={"preset": preset_name, "content": _truncate(final_text, 30000)})
    except Exception as e:
        return format_result(False, f"Failed to load preset: {e}", error_type="runtime_error")


def get_skill(skill_name: str) -> str:
    """
    Lazy load an Antigravity skill using markitdown for clean parsing.
    """
    try:
        md = MarkItDown()
        
        skill_name = str(skill_name).strip()
        skill_dir = Config.SKILLS_DIR / skill_name
        
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            matches = list(skill_dir.glob("SKILL.*"))
            if matches:
                skill_file = matches[0]
            else:
                return format_result(False, f"Skill '{skill_name}' not found at {skill_file}", error_type="not_found")
        
        result = md.convert(str(skill_file))
        content = result.text_content
        
        return format_result(True, f"Skill '{skill_name}' loaded successfully.", data={"skill_name": skill_name, "content": _truncate(content, 12000)})
    except Exception as e:
        return format_result(False, f"Failed to load skill: {e}", error_type="runtime_error")


def git_commit(message: str) -> str:
    """Run git add + git commit."""
    try:
        message = str(message).strip()
        if not message:
            return format_result(False, "Commit message is empty.", error_type="git_error")

        subprocess.run(["git", "add", "."], cwd=Config.WORKSPACE_DIR, capture_output=True, timeout=30)
        
        r = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=Config.WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if r.returncode != 0 and "nothing to commit" not in r.stdout.lower():
            return format_result(False, f"git commit failed: {r.stderr}", error_type="git_error")

        out = r.stdout.strip() if r.returncode == 0 else "Nothing to commit."
        return format_result(True, _truncate(out, 1200))
    except subprocess.TimeoutExpired:
        return format_result(False, "Git command timed out.", error_type="timeout_error")
    except Exception as e:
        return format_result(False, str(e), error_type="git_error")


def github_clone(repo_url: str, target_dir: str = "") -> str:
    try:
        repo_url = str(repo_url).strip()
        if not repo_url:
            return format_result(False, "repo_url is required.", error_type="github_error")
        if not repo_url.startswith("https://github.com/"):
            return format_result(False, "Only https://github.com/... is supported.", error_type="github_error")

        repo_name = repo_url.rstrip("/").split("/")[-1]
        repo_name = repo_name[:-4] if repo_name.endswith(".git") else repo_name
        dest_rel = target_dir.strip() if str(target_dir).strip() else repo_name
        dest = safe_path(dest_rel)

        if dest.exists():
            return format_result(False, f"Target already exists: {dest_rel}", error_type="io_error")

        r = subprocess.run(["git", "clone", repo_url, str(dest)], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return format_result(False, f"git clone failed: {r.stderr.strip()}", error_type="git_error")
        return format_result(True, f"Cloned {repo_url} -> {dest_rel}")
    except Exception as e:
        return format_result(False, str(e), error_type="github_error")


def github_read_file(
    repo_dir: str,
    file_path: str,
    max_chars: int = 4000,
    lean_mode: bool = False,
    full_output: bool = True,
    start_line: int = 1,
    end_line: int = 0,
) -> str:
    try:
        repo_dir = str(repo_dir).strip()
        file_path = str(file_path).strip()
        if not repo_dir or not file_path:
            return format_result(False, "repo_dir and file_path are required.", error_type="io_error")

        repo_root = safe_path(repo_dir)
        target = (repo_root / file_path).resolve()
        if repo_root != target and repo_root not in target.parents:
            return format_result(False, "Security Violation", error_type="security_error")
        if not target.exists() or not target.is_file():
            return format_result(False, "File not found.", error_type="io_error")

        max_chars = max(500, min(int(max_chars), 12000))
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        # staged retrieval: only return a line range when requested
        if end_line and end_line >= start_line >= 1:
            selected = lines[start_line - 1:end_line]
            payload = "\n".join(selected)
            if lean_mode:
                payload = _truncate(payload, max_chars)
            return format_result(
                True,
                "Read file success.",
                data={
                    "content": payload,
                    "range": {"start_line": start_line, "end_line": end_line},
                    "total_lines": len(lines),
                },
            )

        if full_output:
            return format_result(True, "Read file success.", data={"content": text, "total_lines": len(lines), "mode": "full"})

        # lean mode default: return head+tail+symbols
        if lean_mode:
            summary = _smart_file_summary(text, head=60, tail=20)
            payload = _truncate(summary["summary"], max_chars)
            return format_result(
                True,
                "Read file success.",
                data={
                    "content": payload,
                    "total_lines": summary["total_lines"],
                    "important_symbols": summary["important_symbols"],
                    "mode": "lean_regions",
                },
            )

        return format_result(True, "Read file success.", data={"content": _truncate(text, max_chars), "total_lines": len(lines), "mode": "plain_truncate"})
    except Exception as e:
        return format_result(False, str(e), error_type="io_error")


def github_commit_push(repo_dir: str, message: str, branch: str = "", lean_mode: bool = False) -> str:
    try:
        repo_root = safe_path(repo_dir)
        message = str(message).strip()
        if not message:
            return format_result(False, "Commit message is required.", error_type="git_error")

        cmds = [["git", "add", "."]]
        if branch.strip():
            cmds.append(["git", "checkout", "-B", branch.strip()])
        cmds.append(["git", "commit", "-m", message])
        cmds.append(["git", "push", "-u", "origin", branch.strip() or "HEAD"])

        outputs = []
        for cmd in cmds:
            r = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=60)
            out = (r.stdout + "\n" + r.stderr).strip()
            if r.returncode != 0 and not ("nothing to commit" in out.lower() and cmd[:2] == ["git", "commit"]):
                return format_result(False, f"{' '.join(cmd)} failed: {out}", error_type="git_error")
            if lean_mode:
                outputs.append({"cmd": " ".join(cmd), "status": "ok"})
            else:
                outputs.append(f"$ {' '.join(cmd)}\n{_truncate(out or 'ok', 500)}")

        if lean_mode:
            return format_result(True, "Commit and push completed.", data={"steps": outputs})
        return format_result(True, "Commit and push completed.", data={"log": "\n\n".join(outputs)})
    except Exception as e:
        return format_result(False, str(e), error_type="git_error")


def github_create_pr(repo: str, title: str, body: str = "", base: str = "main", head: str = "") -> str:
    try:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            return format_result(False, "GITHUB_TOKEN is required.", error_type="github_error")
        repo = str(repo).strip()
        title = str(title).strip()
        base = str(base).strip() or "main"
        head = str(head).strip()
        if not repo or not title or not head:
            return format_result(False, "repo/title/head are required.", error_type="github_error")
        if not re.match(r"^[^/]+/[^/]+$", repo):
            return format_result(False, "repo must be in owner/name format.", error_type="github_error")

        url = f"https://api.github.com/repos/{repo}/pulls"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"title": title, "body": str(body), "base": base, "head": head}
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code >= 300:
            return format_result(False, f"GitHub API error {resp.status_code}: {resp.text[:300]}", error_type="github_error")
        data = resp.json()
        return format_result(True, "PR created successfully.", data={"url": data.get("html_url", ""), "number": data.get("number")})
    except Exception as e:
        return format_result(False, str(e), error_type="github_error")


def plan(steps: str | list | dict = None, **kwargs) -> str:
    """Record planning text. Accepts multiple input shapes and normalizes to string."""
    try:
        if isinstance(steps, (list, dict)):
            # Normalize list/dict to readable text.
            if isinstance(steps, list):
                content = "\n".join([str(s) for s in steps])
            else:
                content = str(steps)
        elif isinstance(steps, str):
            content = steps
        else:
            # Fallback extraction from common alias keys.
            content = str(kwargs.get("task") or kwargs.get("plan") or kwargs.get("goal") or "No plan content")
        
        return format_result(True, f"Plan recorded:\n{_truncate(content, 2000)}")
    except Exception as e:
        return format_result(False, str(e), error_type="plan_error")


def list_skills(query: str = "") -> str:
    """List available skills with optional keyword filtering."""
    try:
        skills_dir = Config.SKILLS_DIR
        if not skills_dir.exists():
            return format_result(False, "Skills directory not found.", error_type="not_found")

        query_lower = str(query).strip().lower()
        skill_tags = getattr(Config, "SKILL_TAGS", {})
        skills = []

        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_name = skill_dir.name
            skill_file = skill_dir / "SKILL.md"

            # Read metadata from SKILL_TAGS.
            tag_info = skill_tags.get(skill_name, {})
            description = tag_info.get("description", "")
            keywords = tag_info.get("keywords", [])

            # Fallback: infer short description from SKILL.md.
            if not description and skill_file.exists():
                try:
                    raw = skill_file.read_text(encoding="utf-8", errors="replace")[:300]
                    # Use the first non-empty line as description.
                    for line in raw.split("\n"):
                        line = line.strip().strip("#").strip("-").strip()
                        if line and len(line) > 10:
                            description = line[:200]
                            break
                except Exception:
                    description = "(no description)"

            # Optional query filter.
            if query_lower:
                name_match = query_lower in skill_name.lower()
                desc_match = query_lower in description.lower()
                kw_match = any(query_lower in kw for kw in keywords)
                if not (name_match or desc_match or kw_match):
                    continue

            skills.append({
                "name": skill_name,
                "description": description,
                "keywords": keywords[:5],  # Return only first 5 keywords to save context.
                "has_skill_file": skill_file.exists(),
            })

        if not skills:
            return format_result(True, f"No skills found matching '{query}'.", data={"skills": [], "total": 0})

        return format_result(
            True,
            f"Found {len(skills)} skills" + (f" matching '{query}'" if query_lower else "") + ".",
            data={"skills": skills, "total": len(skills)}
        )
    except Exception as e:
        return format_result(False, f"Failed to list skills: {e}", error_type="runtime_error")


def design_to_component_metadata(
    design_name: str,
    screens: list | None = None,
    style_notes: str = "",
    output_path: str = "design/component_metadata.json",
) -> str:
    """Create design metadata and a checklist scaffold from reference images/notes."""
    try:
        design_name = str(design_name).strip() or "unnamed_design"
        screens = screens or []
        if not isinstance(screens, list):
            return format_result(False, "screens must be a list.", error_type="validation_error")

        payload = {
            "design_name": design_name,
            "style_notes": str(style_notes),
            "screens": [],
            "global_checklist": [
                "Define app navigation map",
                "Define reusable component library",
                "Map each screen to component tree",
                "Implement responsive layout rules",
                "Add loading/empty/error states",
                "Add accessibility labels and semantics",
                "Add unit/widget tests for critical screens",
            ],
        }

        for item in screens:
            if isinstance(item, dict):
                name = str(item.get("name", "unnamed_screen"))
                purpose = str(item.get("purpose", ""))
            else:
                name = str(item)
                purpose = ""
            payload["screens"].append({
                "name": name,
                "purpose": purpose,
                "component_tree": [
                    {"id": f"{name}_root", "type": "Scaffold", "children": []},
                ],
                "screen_checklist": [
                    "Extract repeated UI blocks into reusable widgets",
                    "Bind screen state and async data flow",
                    "Add form/input validation if needed",
                    "Add golden/snapshot tests",
                ],
            })

        p = safe_path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return format_result(True, f"Design metadata scaffold created at {output_path}", data={"path": output_path, "screens": len(payload["screens"])})
    except Exception as e:
        return format_result(False, str(e), error_type="io_error")


def validate_mobile_quality(
    project_dir: str = ".",
    framework: str = "flutter",
    include_web: bool = True,
    strict_web: bool = True,
) -> str:
    """Run build/test/lint quality gate and return pass/fail summary."""
    try:
        project_root = safe_path(project_dir)
        framework = str(framework).strip().lower()
        if framework != "flutter":
            return format_result(False, "Only flutter is supported currently.", error_type="validation_error")

        steps = [
            ("flutter pub get", ["flutter", "pub", "get"]),
            ("flutter analyze", ["flutter", "analyze"]),
            ("flutter test", ["flutter", "test"]),
            ("flutter build apk --debug", ["flutter", "build", "apk", "--debug"]),
        ]
        web_steps = []
        if include_web:
            web_steps = [
                ("flutter build web", ["flutter", "build", "web"]),
                ("flutter test --platform chrome", ["flutter", "test", "--platform", "chrome"]),
            ]
            steps.extend(web_steps)
        results = []
        all_passed = True
        for name, cmd in steps:
            r = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=600)
            out = (r.stdout + "\n" + r.stderr).strip()
            ok = r.returncode == 0
            all_passed = all_passed and ok
            results.append({"step": name, "ok": ok, "output": _truncate(out, 1200)})

        core_passed = all_passed
        web_warning = False
        if include_web and not strict_web:
            web_step_names = {name for name, _ in web_steps}
            core_results = [r for r in results if r["step"] not in web_step_names]
            web_results = [r for r in results if r["step"] in web_step_names]
            core_passed = all(r["ok"] for r in core_results) if core_results else True
            web_passed = all(r["ok"] for r in web_results) if web_results else True
            all_passed = core_passed
            if not web_passed:
                web_warning = True
                results.append(
                    {
                        "step": "web-validation-warning",
                        "ok": True,
                        "output": "Web validation failed but strict_web=false, treating as warning.",
                    }
                )

        return format_result(
            all_passed,
            (
                f"Mobile quality gate passed. core_passed={core_passed}, web_warning={web_warning}."
                if all_passed
                else f"Mobile quality gate failed. core_passed={core_passed}, web_warning={web_warning}."
            ),
            data={
                "framework": framework,
                "all_passed": all_passed,
                "core_passed": core_passed,
                "web_warning": web_warning,
                "include_web": include_web,
                "strict_web": strict_web,
                "results": results,
            },
            error_type=None if all_passed else "quality_gate_failed",
        )
    except Exception as e:
        return format_result(False, str(e), error_type="validation_error")


def render_progress_dashboard(output_path: str = "artifacts/dashboard.html") -> str:
    """Render a local dashboard from runtime progress, task summaries, and rescue events."""
    try:
        progress_path = Config.WORKSPACE_DIR / "artifacts" / "runtime_progress.json"
        summary_dir = Config.WORKSPACE_DIR / "artifacts" / "task_summaries"
        rescue_events_path = Config.WORKSPACE_DIR / "artifacts" / "rescue_events.jsonl"

        progress = {}
        if progress_path.exists():
            progress = json.loads(progress_path.read_text("utf-8"))

        summaries = []
        if summary_dir.exists():
            for fp in sorted(summary_dir.glob("*.summary.json"))[-30:]:
                try:
                    summaries.append(json.loads(fp.read_text("utf-8")))
                except Exception:
                    continue

        rescue_events = []
        rescue_status_counts = {"success": 0, "failed": 0, "other": 0}
        if rescue_events_path.exists():
            for line in rescue_events_path.read_text("utf-8", errors="replace").splitlines():
                raw = line.strip()
                if not raw:
                    continue
                try:
                    evt = json.loads(raw)
                except Exception:
                    continue
                status = str(evt.get("status", "")).lower()
                if status in rescue_status_counts:
                    rescue_status_counts[status] += 1
                else:
                    rescue_status_counts["other"] += 1
                rescue_events.append(evt)
        latest_rescue_events = rescue_events[-50:]

        html = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Agent Dashboard</title>
<style>body{{font-family:Arial;margin:24px}} .card{{border:1px solid #ddd;padding:12px;margin:8px 0;border-radius:8px}}</style>
</head><body>
<h1>Agent Runtime Dashboard</h1>
<div class='card'><h2>Current Progress</h2><pre>{json.dumps(progress, ensure_ascii=False, indent=2)}</pre></div>
<div class='card'><h2>Task Summaries (latest {len(summaries)})</h2><pre>{json.dumps(summaries, ensure_ascii=False, indent=2)}</pre></div>
<div class='card'><h2>Rescue Events Summary</h2><pre>{json.dumps({"total": len(rescue_events), "status_counts": rescue_status_counts}, ensure_ascii=False, indent=2)}</pre></div>
<div class='card'><h2>Rescue Events (latest {len(latest_rescue_events)})</h2><pre>{json.dumps(latest_rescue_events, ensure_ascii=False, indent=2)}</pre></div>
</body></html>"""

        p = safe_path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        return format_result(
            True,
            f"Dashboard rendered at {output_path}",
            data={
                "path": output_path,
                "summary_count": len(summaries),
                "rescue_event_count": len(rescue_events),
            },
        )
    except Exception as e:
        return format_result(False, str(e), error_type="io_error")


def capture_web_screenshot(
    url: str,
    output_path: str,
    full_page: bool = True,
    wait_ms: int = 1500,
    viewport_width: int = 1440,
    viewport_height: int = 900,
) -> str:
    """Capture a screenshot of a web page using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return format_result(
            False,
            "Playwright is not installed. Install with `pip install playwright` and run `playwright install chromium`.",
            error_type="dependency_error",
        )

    try:
        url = str(url).strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return format_result(False, "url must start with http:// or https://", error_type="validation_error")

        p = safe_path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": int(viewport_width), "height": int(viewport_height)})
            page.goto(url, wait_until="networkidle", timeout=60_000)
            if wait_ms > 0:
                page.wait_for_timeout(int(wait_ms))
            page.screenshot(path=str(p), full_page=bool(full_page))
            browser.close()

        return format_result(
            True,
            f"Screenshot captured: {output_path}",
            data={
                "url": url,
                "path": output_path,
                "full_page": bool(full_page),
                "wait_ms": int(wait_ms),
                "viewport": {"width": int(viewport_width), "height": int(viewport_height)},
            },
        )
    except Exception as e:
        return format_result(False, str(e), error_type="screenshot_error")


def start_web_server(
    project_dir: str = "build/web",
    host: str = "127.0.0.1",
    port: int = 8787,
    python_bin: str = "python",
    task_id: str = "default",
) -> str:
    """Start a local static web server and persist server metadata."""
    try:
        root = safe_path(project_dir)
        if not root.exists() or not root.is_dir():
            return format_result(False, f"Directory not found: {project_dir}", error_type="io_error")

        if python_bin not in Config.ALLOWED_BINARIES:
            return format_result(False, f"Forbidden python binary: {python_bin}", error_type="security_error")

        cmd = [python_bin, "-m", "http.server", str(int(port)), "--bind", str(host)]
        log_dir = safe_path("artifacts/web_server_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = log_dir / "stdout.log"
        stderr_path = log_dir / "stderr.log"
        stdout_f = open(stdout_path, "a", encoding="utf-8")
        stderr_f = open(stderr_path, "a", encoding="utf-8")
        proc = subprocess.Popen(  # nosec B603,B607 - controlled command and allowlist checked
            cmd,
            cwd=root,
            stdout=stdout_f,
            stderr=stderr_f,
            text=True,
        )
        stdout_f.close()
        stderr_f.close()
        time.sleep(0.3)
        if proc.poll() is not None:
            return format_result(False, "Web server process exited during startup.", error_type="execution_error")

        health_url = f"http://{host}:{int(port)}"
        healthy = False
        health_error = ""
        for _ in range(5):
            try:
                r = requests.get(health_url, timeout=3)
                healthy = r.status_code < 500
                if healthy:
                    break
                health_error = f"HTTP status {r.status_code}"
            except Exception as e:
                health_error = str(e)
            time.sleep(0.3)

        server_meta = {
            "pid": proc.pid,
            "host": host,
            "port": int(port),
            "project_dir": project_dir,
            "url": health_url,
            "cmd": cmd,
            "healthy": healthy,
            "stdout_log": str(stdout_path.relative_to(Config.WORKSPACE_DIR)),
            "stderr_log": str(stderr_path.relative_to(Config.WORKSPACE_DIR)),
        }
        safe_task = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(task_id).strip() or "default")
        meta_path = safe_path(f"artifacts/web_server_{safe_task}_{int(port)}.json")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(server_meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if not healthy:
            return format_result(False, f"Web server started but health check failed: {health_error}", data=server_meta, error_type="health_check_failed")
        return format_result(True, "Web server started and healthy.", data=server_meta)
    except Exception as e:
        return format_result(False, str(e), error_type="execution_error")


def stop_web_server(meta_path: str = "artifacts/web_server_default_8787.json") -> str:
    """Stop local web server using metadata file and remove metadata."""
    try:
        p = safe_path(meta_path)
        if not p.exists():
            return format_result(False, f"Metadata file not found: {meta_path}", error_type="io_error")

        meta = json.loads(p.read_text("utf-8"))
        pid = int(meta.get("pid", 0))
        if pid <= 0:
            return format_result(False, "Invalid PID in metadata file.", error_type="validation_error")

        stopped = False
        reason = ""
        try:
            if os.name == "nt":
                r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=15)
                stopped = r.returncode == 0
                reason = (r.stdout + r.stderr).strip()
            else:
                os.kill(pid, 15)
                for _ in range(5):
                    try:
                        os.kill(pid, 0)
                        time.sleep(0.2)
                    except ProcessLookupError:
                        stopped = True
                        break
                if not stopped:
                    os.kill(pid, 9)
                    stopped = True
        except ProcessLookupError:
            stopped = True
            reason = "Process not found; treated as already stopped."

        p.unlink(missing_ok=True)
        return format_result(True, "Web server stop flow completed.", data={"pid": pid, "meta_path": meta_path, "stopped": stopped, "reason": reason})
    except Exception as e:
        return format_result(False, str(e), error_type="execution_error")


def web_server_status(meta_path: str = "artifacts/web_server_default_8787.json", log_tail_lines: int = 40) -> str:
    """Get web server status, health, and recent log tails."""
    try:
        p = safe_path(meta_path)
        if not p.exists():
            return format_result(False, f"Metadata file not found: {meta_path}", error_type="io_error")
        meta = json.loads(p.read_text("utf-8"))
        pid = int(meta.get("pid", 0))
        running = False
        if pid > 0:
            try:
                os.kill(pid, 0)
                running = True
            except Exception:
                running = False

        url = str(meta.get("url", ""))
        healthy = False
        health_error = ""
        if url:
            try:
                r = requests.get(url, timeout=3)
                healthy = r.status_code < 500
                if not healthy:
                    health_error = f"HTTP status {r.status_code}"
            except Exception as e:
                health_error = str(e)

        def _tail(rel_path: str) -> str:
            try:
                fp = safe_path(rel_path)
                if not fp.exists():
                    return ""
                lines = fp.read_text("utf-8", errors="replace").splitlines()
                return "\n".join(lines[-max(1, int(log_tail_lines)):])
            except Exception:
                return ""

        stdout_tail = _tail(meta.get("stdout_log", ""))
        stderr_tail = _tail(meta.get("stderr_log", ""))
        return format_result(
            True,
            "Web server status collected.",
            data={
                "pid": pid,
                "running": running,
                "healthy": healthy,
                "health_error": health_error,
                "meta_path": meta_path,
                "url": url,
                "stdout_tail": _truncate(stdout_tail, 3000),
                "stderr_tail": _truncate(stderr_tail, 3000),
            },
        )
    except Exception as e:
        return format_result(False, str(e), error_type="execution_error")


TOOLS_REGISTRY = {
    "web_search": web_search,
    "download_file": download_file,
    "run_cmd": run_cmd,
    "write_file": write_file,
    "read_file": read_file,
    "run_python_script": run_python_script,
    "get_skill": get_skill,
    "load_preset": load_preset,
    "list_skills": list_skills,
    "plan": plan,
    "git_commit": git_commit,
    "github_clone": github_clone,
    "github_read_file": github_read_file,
    "github_commit_push": github_commit_push,
    "github_create_pr": github_create_pr,
    "browse_page": browse_page,
    "design_to_component_metadata": design_to_component_metadata,
    "validate_mobile_quality": validate_mobile_quality,
    "render_progress_dashboard": render_progress_dashboard,
    "capture_web_screenshot": capture_web_screenshot,
    "start_web_server": start_web_server,
    "stop_web_server": stop_web_server,
    "web_server_status": web_server_status,
}


def execute_tool(action: str, kwargs: dict) -> str:
    """
    Strict schema behavior:
    - ignore unknown params
    - support a small alias set
    - always return JSON string
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
        "command": "cmd",
        "plan": "steps",
        "task": "steps",
        "goal": "steps",
        "tasks": "steps",
        "input": "steps",
    }

    normalized = {alias_map.get(k, k): v for k, v in kwargs.items()}
    
    has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if has_varkw:
        valid_kwargs = normalized
    else:
        valid_kwargs = {k: v for k, v in normalized.items() if k in sig.parameters}

    try:
        return func(**valid_kwargs)
    except Exception as e:
        return format_result(False, str(e), error_type="runtime_error")
