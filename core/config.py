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
    MAX_STEPS = int(os.getenv("MAX_STEPS", 25))
    MAX_HISTORY = int(os.getenv("MAX_HISTORY", 20))
    MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", 60000))  # 提升 Context 上限以容納多個 Skill
    POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", 2))

    # ===== 技能限制 (SKILL BUDGET) =====
    MAX_SKILLS_LOADED = int(os.getenv("MAX_SKILLS_LOADED", 4))
    SKILL_SUMMARY_MAX_CHARS = int(os.getenv("SKILL_SUMMARY_MAX_CHARS", 600))

    # ===== 常用技能組合 (SKILL PRESETS) =====
    SKILL_PRESETS = {
        "frontend": ["frontend-ui-engineering", "browser-testing-with-devtools", "api-and-interface-design"],
        "backend": ["api-and-interface-design", "security-and-hardening", "test-driven-development"],
        "debug": ["debugging-and-error-recovery", "code-review-and-quality", "browser-testing-with-devtools"],
        "research": ["planning-and-task-breakdown", "documentation-and-adrs", "idea-refine"],
        "new_project": ["spec-driven-development", "planning-and-task-breakdown", "git-workflow-and-versioning"]
    }

    # ===== 技能標籤（用於自動路由） =====
    SKILL_TAGS = {
        "frontend-ui-engineering": {
            "keywords": ["frontend", "ui", "react", "html", "css", "vue", "svelte", "component", "layout", "responsive", "design", "tailwind", "animation", "interface", "webpage", "website"],
            "description": "Build production-quality UIs and components"
        },
        "browser-testing-with-devtools": {
            "keywords": ["browser", "devtools", "dom", "console", "network", "chrome", "selenium", "puppeteer", "visual", "screenshot", "render"],
            "description": "Test and debug in real browsers with DevTools"
        },
        "api-and-interface-design": {
            "keywords": ["api", "rest", "graphql", "endpoint", "interface", "contract", "schema", "backend", "fastapi", "express", "route", "module"],
            "description": "Design stable APIs and module boundaries"
        },
        "security-and-hardening": {
            "keywords": ["security", "auth", "authentication", "authorization", "xss", "csrf", "injection", "vulnerability", "password", "token", "encrypt", "ssl", "cors"],
            "description": "Harden code against vulnerabilities"
        },
        "test-driven-development": {
            "keywords": ["test", "tdd", "unittest", "pytest", "jest", "coverage", "mock", "assertion", "spec", "qa", "regression"],
            "description": "Drive development with tests first"
        },
        "debugging-and-error-recovery": {
            "keywords": ["debug", "error", "bug", "fix", "crash", "exception", "traceback", "stack", "breakpoint", "issue", "broken", "fail", "stuck"],
            "description": "Systematic root-cause debugging"
        },
        "code-review-and-quality": {
            "keywords": ["review", "quality", "refactor", "clean", "lint", "smell", "complexity", "maintainability", "readability", "standard"],
            "description": "Multi-axis code review"
        },
        "code-simplification": {
            "keywords": ["simplify", "simplification", "clarity", "readable", "reduce", "complexity", "cleaner", "redundant", "duplication"],
            "description": "Simplify code for clarity without changing behavior"
        },
        "planning-and-task-breakdown": {
            "keywords": ["plan", "task", "breakdown", "scope", "estimate", "requirement", "spec", "architecture", "design", "strategy", "roadmap"],
            "description": "Break work into ordered, implementable tasks"
        },
        "incremental-implementation": {
            "keywords": ["incremental", "step-by-step", "iterative", "phased", "multi-file", "large", "feature", "migration"],
            "description": "Deliver changes incrementally across multiple files"
        },
        "documentation-and-adrs": {
            "keywords": ["doc", "documentation", "adr", "readme", "changelog", "decision", "record", "explain", "comment"],
            "description": "Record decisions and documentation"
        },
        "git-workflow-and-versioning": {
            "keywords": ["git", "commit", "branch", "merge", "conflict", "version", "release", "tag", "pr", "pull request"],
            "description": "Structure git workflow and versioning practices"
        },
        "performance-optimization": {
            "keywords": ["performance", "optimize", "speed", "latency", "cache", "memory", "profile", "bottleneck", "web vitals", "load time", "slow"],
            "description": "Optimize application performance"
        },
        "ci-cd-and-automation": {
            "keywords": ["ci", "cd", "pipeline", "deploy", "github actions", "jenkins", "docker", "build", "automation", "workflow"],
            "description": "Automate CI/CD pipeline setup"
        },
        "spec-driven-development": {
            "keywords": ["spec", "specification", "requirement", "new project", "from scratch", "mvp", "prototype"],
            "description": "Create specs before coding"
        },
        "shipping-and-launch": {
            "keywords": ["ship", "launch", "deploy", "production", "rollout", "monitor", "checklist", "staging"],
            "description": "Prepare production launches"
        },
        "deprecation-and-migration": {
            "keywords": ["deprecate", "migrate", "sunset", "legacy", "upgrade", "replace", "backward", "compatibility"],
            "description": "Manage deprecation and migration"
        },
        "idea-refine": {
            "keywords": ["idea", "ideate", "brainstorm", "divergent", "convergent", "explore", "concept", "creative"],
            "description": "Refine ideas through structured thinking"
        },
        "source-driven-development": {
            "keywords": ["official docs", "documentation", "authoritative", "source", "framework", "library", "correct pattern"],
            "description": "Ground implementation in official documentation"
        },
        "context-engineering": {
            "keywords": ["context", "rules", "prompt", "agent", "session", "configure", "setup"],
            "description": "Optimize agent context setup"
        },
        "marimo-interactive-python": {
            "keywords": ["marimo", "notebook", "interactive", "dashboard", "visualize", "plot", "data analysis", "chart", "slider", "button"],
            "description": "Build reactive, interactive web apps and data tools with Python"
        },
    }

    # ===== 安全 =====
    ALLOWED_BINARIES = set(
        os.getenv("ALLOWED_BINARIES", "python,python3,pip,pip3,ls,cat,echo,git").split(",")
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
        "2. DISCOVER & LOAD: Check auto-loaded skills. Call `list_skills` or `get_skill` (up to 4 max) if needed.\n"
        "3. PLAN: Use `plan` tool to outline steps.\n"
        "4. EXECUTE & FINISH: Act, then `mark_done`.\n\n"
        
        "=== AVAILABLE ACTIONS ===\n"
        "| Action | Usage |\n"
        "|---|---|\n"
        "| list_skills, get_skill, load_preset | Discover/load domain skills (frontend/backend/debug/research/new_project) |\n"
        "| plan | Outline execution steps |\n"
        "| web_search, browse_page | Find/read information |\n"
        "| download_file, run_cmd | Shell execution (guarded) & IO |\n"
        "| write_file, read_file | Local file management |\n"
        "| run_python_script | Execute python code natively |\n"
        "| git_commit, mark_done | Version control & finish task |\n\n"
        
        "=== RULES ===\n"
        "1. NEVER repeat the same action >2 times.\n"
        "2. If a skill is already AUTO-LOADED, do not load it again.\n"
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