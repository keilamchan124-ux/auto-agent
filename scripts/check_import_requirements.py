#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "requirements.txt"

IMPORT_TO_PACKAGE = {
    "dotenv": "python-dotenv",
    "telebot": "pyTelegramBotAPI",
    "github": "PyGithub",
    "google": "google-genai",
}

IGNORE_LOCAL = {"core", "mcp", "tests"}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "", name).lower()


def parse_requirements(path: Path) -> set[str]:
    pkgs: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"([A-Za-z0-9_.-]+)", line)
        if m:
            pkgs.add(m.group(1))
    return pkgs


def collect_imports(root: Path) -> set[str]:
    mods: set[str] = set()
    for py in root.rglob("*.py"):
        if any(x in py.parts for x in (".git", ".venv", "venv", "__pycache__")):
            continue
        if py.name == Path(__file__).name:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                mods.add(n.module.split(".")[0])
    return mods


def main() -> int:
    if not REQ.exists():
        print("requirements.txt not found", file=sys.stderr)
        return 2

    reqs = parse_requirements(REQ)
    req_norm = {normalize(r) for r in reqs}

    imports = collect_imports(ROOT)
    missing: list[tuple[str, str]] = []

    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    for mod in sorted(imports):
        if mod in stdlib or mod.startswith("_") or mod in IGNORE_LOCAL:
            continue
        pkg = IMPORT_TO_PACKAGE.get(mod, mod)
        if normalize(pkg) not in req_norm:
            missing.append((mod, pkg))

    if missing:
        print("Missing requirements for imported modules:")
        for mod, pkg in missing:
            print(f"- import '{mod}' -> add package '{pkg}'")
        return 1

    print("Import/requirements check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
