from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env")


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
    SKILLS_DIR = WORKSPACE_DIR / ".agents" / "skills"

    # ===== AGENT 控制 =====
    MAX_STEPS = int(os.getenv("MAX_STEPS", 40))   # 從 25 增加到 40
    MAX_HISTORY = int(os.getenv("MAX_HISTORY", 20))
    POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", 2))

    # ===== 防 Loop / 防爆 =====
    MAX_SEARCH_RETRY = int(os.getenv("MAX_SEARCH_RETRY", 3))
    MAX_REPEAT_ACTION = int(os.getenv("MAX_REPEAT_ACTION", 2))
    MAX_PARSE_FAIL = int(os.getenv("MAX_PARSE_FAIL", 2))

    # ===== 安全 =====
    ALLOWED_BINARIES = set(
        os.getenv("ALLOWED_BINARIES", "python,python3,ls,cat,echo").split(",")
    )
    ALLOWED_DOMAINS = [d.strip() for d in os.getenv("ALLOWED_DOMAINS", "*").split(",") if d.strip()]

    # ===== ANTIGRAVITY =====
    IS_ANTIGRAVITY = os.getenv("ANTIGRAVITY_MODE") == "1" or (WORKSPACE_DIR / ".antigravity").exists()

    # ===== SYSTEM PROMPT =====
    _BASE_PROMPT = (
        "You are an intelligent Autonomous Agent.\n"
        "Return ONLY ONE fenced JSON block: ```json\n{\"action\":\"...\", \"kwargs\":{...}}\n```\n"
        "No extra text, no markdown outside JSON.\n\n"
        
        "=== MANDATORY WORKFLOW ===\n"
        "1. THINK: Analyze task domain.\n"
        "2. DISCOVER & LOAD: Check auto-loaded skills. Call `list_skills` or `get_skill` (up to 6 max) if needed.\n"
        "3. PLAN: Use `plan` tool to outline steps.\n"
        "4. EXECUTE & FINISH: Act, then `mark_done`.\n\n"
        
        "=== AVAILABLE ACTIONS ===\n"
        "| Action | Usage |\n"
        "|---|---|\n"
        "| list_skills, get_skill, load_preset | Discover/load domain skills |\n"
        "| plan | Outline execution steps (MUST use 'steps' parameter) |\n"
        "| web_search, browse_page | Find/read information |\n"
        "| download_file, run_cmd | Shell execution (guarded) & IO |\n"
        "| write_file, read_file | Local file management |\n"
        "| run_python_script | Execute python code natively |\n"
        "| git_commit, mark_done | Version control & finish task |\n\n"
        
        "=== RULES ===\n"
        "1. NEVER repeat the same action >2 times.\n"
        "2. If a skill is already AUTO-LOADED, do not load it again.\n"
        "3. After any error or rescue, you MUST summarize what mistake you made.\n\n"
        
        "=== CRITICAL: TOOL PARAMETER EXAMPLES (MUST FOLLOW) ===\n"
        "You MUST use the EXACT parameter names:\n\n"
        
        "【plan 工具 - 正確範例】\n"
        "✅ 正確：{\"action\":\"plan\",\"kwargs\":{\"steps\":\"1. First step\\n2. Second step\"}}\n"
        "❌ 錯誤：使用 task、goal、tasks、input 作為 key\n\n"
        
        "【get_skill 工具 - 正確範例】\n"
        "✅ 正確：{\"action\":\"get_skill\",\"kwargs\":{\"skill_name\":\"frontend-ui-engineering\"}}\n"
        "❌ 錯誤：使用 name 作為 key\n\n"
        
        "【其他工具正確參數】\n"
        "- web_search → {\"q\": \"search term\"}\n"
        "- browse_page → {\"url\": \"https://...\"}\n"
        "- write_file → {\"path\": \"file.py\", \"content\": \"...\"}\n"
        "- run_cmd → {\"cmd\": \"ls -la\"}   (注意是 cmd，不是 command)\n\n"
        
        "如果工具回傳錯誤包含 'missing ... argument'，請立即使用正確參數名稱重試。\n"
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