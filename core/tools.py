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
from pathlib import Path
from typing import Any, Dict

import requests
from ddgs import DDGS
from markitdown import MarkItDown

from core.config import Config

logger = logging.getLogger("Tools")


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


def run_cmd(cmd: str) -> str:
    """Execute shell command with binary allowlist."""
    try:
        cmd = str(cmd).strip()
        if not cmd:
            return format_result(False, "Empty command.", error_type="execution_error")

        is_windows = os.name == "nt"

        if is_windows:
            args = shlex.split(cmd, posix=False)
            if not args:
                return format_result(False, "Empty command.", error_type="execution_error")
            binary = args[0].strip("\"'")
        else:
            args = shlex.split(cmd)
            if not args:
                return format_result(False, "Empty command.", error_type="execution_error")
            binary = args[0]

        if binary == "cd":
            return format_result(False, "The 'cd' command is not supported. All commands run in the workspace root automatically. Please use relative or absolute paths directly.", error_type="execution_error")

        if binary not in Config.ALLOWED_BINARIES:
            return format_result(False, "Forbidden command.", error_type="security_error")

        if is_windows:
            r = subprocess.run(
                cmd,
                shell=True,
                cwd=Config.WORKSPACE_DIR,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
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


def read_file(path: str, full_output: bool = True) -> str:
    try:
        p = safe_path(path)
        if not p.exists():
            return format_result(False, "File not found.", error_type="io_error")
        if not p.is_file():
            return format_result(False, "Path is not a file.", error_type="io_error")

        text = p.read_text(encoding="utf-8", errors="replace")
        if full_output:
            return format_result(True, "Read file success.", data={"content": _truncate(text, 30000), "mode": "full"})
        summary = _smart_file_summary(text, head=80, tail=20)
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

        # Prefer python3 when allowed, otherwise fallback to python.
        cmd_exe = "python3" if "python3" in Config.ALLOWED_BINARIES else "python"
        
        r = subprocess.run(
            [cmd_exe, str(script_path)],
            cwd=Config.WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )

        out = (r.stdout + "\n" + r.stderr).strip() or "Success (No output)"
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
