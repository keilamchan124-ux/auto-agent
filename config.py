# config.py
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

    # ===== AGENT 控制 =====
    MAX_STEPS = int(os.getenv("MAX_STEPS", 50))
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