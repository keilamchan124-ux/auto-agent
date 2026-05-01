from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env", override=True)


class Config:
    # ===== API KEYS =====
    MIMO_API_KEY = os.getenv("MIMO_API_KEY", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

    # ===== MODELS =====
    MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

    # ✅ 新增：Base URL（有 fallback）
    MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "").strip() or None

    # ===== WORKSPACE =====
    WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "workspace")).resolve()
    TODO_FILE = Path(os.getenv("TODO_FILE", "todo.txt"))
    SKILLS_DIR = Path(__file__).resolve().parent.parent / ".agents" / "skills"

    # ===== AGENT 控制 =====
    MAX_STEPS = int(os.getenv("MAX_STEPS", 50))
    MAX_HISTORY = int(os.getenv("MAX_HISTORY", 20))
    MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", 60000))  # 提升 Context 上限以容納多個 Skill
    POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", 2))

    # ===== 常用技能組合 (SKILL PRESETS) =====
    SKILL_PRESETS = {
        "frontend": ["frontend-ui-engineering", "browser-testing-with-devtools", "api-and-interface-design"],
        "backend": ["api-and-interface-design", "security-and-hardening", "test-driven-development"],
        "debug": ["debugging-and-error-recovery", "code-review-and-quality", "browser-testing-with-devtools"],
        "research": ["planning-and-task-breakdown", "documentation-and-adrs", "idea-refine"],
        "new_project": ["spec-driven-development", "planning-and-task-breakdown", "git-workflow-and-versioning"]
    }

    # ===== 安全 =====
    ALLOWED_BINARIES = set(
        os.getenv("ALLOWED_BINARIES", "python,python3,ls,cat,echo").split(",")
    )
    ALLOWED_DOMAINS = [d.strip() for d in os.getenv("ALLOWED_DOMAINS", "*").split(",") if d.strip()]

    # ===== ANTIGRAVITY =====
    IS_ANTIGRAVITY = os.getenv("ANTIGRAVITY_MODE") == "1" or (WORKSPACE_DIR / ".antigravity").exists()

    # ===== SYSTEM PROMPT =====
    _BASE_PROMPT = (
        "Robotic Executor.\n"
        "ONLY JSON.\n"
        "Output exactly one fenced JSON block.\n"
        "No thoughts. No explanations.\n"
        "Available actions: web_search, browse_page, download_file, run_cmd, write_file, read_file, run_python_script, get_skill, load_preset, plan, git_commit, mark_done.\n"
        "Schema: {\"action\":\"...\", \"kwargs\":{...}}\n"
        "Note: Use `get_skill` with `{\"skill_name\": \"<name>\"}` or `load_preset` with `{\"preset_name\": \"<name>\"}` to lazy-load engineering skills.\n"
        "Recommended skills: 'code-review-and-quality', 'test-driven-development', 'planning-and-task-breakdown', 'debugging-and-error-recovery'."
    )

    SYSTEM_PROMPT = _BASE_PROMPT
    if IS_ANTIGRAVITY:
        SYSTEM_PROMPT += (
            "\n[ANTIGRAVITY MODE ENABLED]\n"
            "- You must generate detailed artifacts for the user to review.\n"
            "- Consider terminal review policy (SafeToAutoRun vs manual approval).\n"
            "- Follow all best practices in SKILL.md rules if available."
        )


# ===== 初始化 =====
Config.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


# ===== 啟動檢查（關鍵）=====
def validate():
    if not Config.MIMO_API_KEY:
        print("⚠️ WARNING: MIMO_API_KEY is empty")

    if not Config.GEMINI_API_KEY:
        print("⚠️ WARNING: GEMINI_API_KEY is empty")

    # ✅ 呢行好重要：避免你再 debug 半日
    if Config.MIMO_BASE_URL is None:
        print("ℹ️ INFO: MIMO_BASE_URL not set, using OpenAI default endpoint")


validate()