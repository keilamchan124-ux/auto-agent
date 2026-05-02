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

    # Base URL (with fallback)
    MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "").strip() or None

    # ===== WORKSPACE =====
    WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "workspace")).resolve()
    TODO_FILE = Path(os.getenv("TODO_FILE", "todo.txt"))
    SKILLS_DIR = Path(__file__).resolve().parent.parent / ".agents" / "skills"

    # ===== AGENT CONTROL =====
    MAX_STEPS = int(os.getenv("MAX_STEPS", 50))
    MAX_HISTORY = int(os.getenv("MAX_HISTORY", 20))
    MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", 60000))  # higher context budget for multiple skills
    POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", 2))

    # ===== SKILL LIMITS (SKILL BUDGET) =====
    MAX_SKILLS_LOADED = int(os.getenv("MAX_SKILLS_LOADED", 6))
    SKILL_SUMMARY_MAX_CHARS = int(os.getenv("SKILL_SUMMARY_MAX_CHARS", 600))

    # ===== COMMON SKILL PRESETS =====
    SKILL_PRESETS = {
        "frontend": ["frontend-ui-engineering", "browser-testing-with-devtools", "api-and-interface-design"],
        "backend": ["api-and-interface-design", "security-and-hardening", "test-driven-development"],
        "debug": ["debugging-and-error-recovery", "code-review-and-quality", "browser-testing-with-devtools"],
        "research": ["planning-and-task-breakdown", "documentation-and-adrs", "idea-refine"],
        "new_project": ["spec-driven-development", "planning-and-task-breakdown", "git-workflow-and-versioning"]
    }

    # ===== SKILL TAGS (for auto-routing) =====
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
        "github-integration-lite": {
            "keywords": ["github", "clone", "pull request", "pr", "commit", "push", "repository"],
            "description": "Lightweight GitHub skill with clone/read/commit-push/create-pr tools"
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

    # ===== SECURITY =====
    ALLOWED_BINARIES = set(
        os.getenv(
            "ALLOWED_BINARIES",
            "python,python3,pip,pip3,ls,cat,echo,git,dir,find,pwd,cd,flutter,dart,npm,npx,node,pnpm,yarn,gradle,gradlew,java,javac,adb,sdkmanager,avdmanager,emulator,bundletool",
        ).split(",")
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
        "| design_to_component_metadata | Convert design references into metadata + checklist scaffold |\n"
        "| validate_mobile_quality | Run flutter build/test/lint quality gate |\n"
        "| render_progress_dashboard | Render runtime progress + task summary dashboard |\n"
        "| capture_web_screenshot | Capture web screenshots via Playwright for visual validation |\n"
        "| start_web_server | Start local static web server for screenshot/testing loop |\n"
        "| git_commit | Version control |\n"
        "| mark_done | Control action (handled by agent loop, not tool registry) |\n\n"
        
        "=== RULES ===\n"
        "1. NEVER repeat the same action >2 times.\n"
        "2. If a skill is already AUTO-LOADED, do not load it again.\n"
        "3. After any error or rescue, you MUST summarize what mistake you made.\n\n"
        
        "=== CRITICAL: TOOL PARAMETER EXAMPLES (MUST FOLLOW) ===\n"
        "You MUST use the EXACT parameter names:\n\n"
        
        "[plan tool - correct example]\n"
        "✅ Correct: {\"action\":\"plan\",\"kwargs\":{\"steps\":\"1. First step\\n2. Second step\"}}\n"
        "❌ Wrong: do not use task, goal, tasks, or input as key\n\n"
        
        "[get_skill tool - correct example]\n"
        "✅ Correct: {\"action\":\"get_skill\",\"kwargs\":{\"skill_name\":\"frontend-ui-engineering\"}}\n"
        "❌ Wrong: do not use name as key\n\n"
        
        "[other tool parameter examples]\n"
        "- web_search → {\"q\": \"search term\"}\n"
        "- browse_page → {\"url\": \"https://...\"}\n"
        "- write_file → {\"path\": \"file.py\", \"content\": \"...\"}\n"
        "- run_cmd → {\"cmd\": \"ls -la\"}   (use cmd, not command)\n\n"
        
        "If tool errors include 'missing ... argument', retry immediately with exact parameter names.\n"
    )

    SYSTEM_PROMPT = _BASE_PROMPT
    if IS_ANTIGRAVITY:
        SYSTEM_PROMPT += (
            "\n[ANTIGRAVITY MODE ENABLED]\n"
            "- You must generate detailed artifacts for the user to review.\n"
            "- Consider terminal review policy (SafeToAutoRun vs manual approval).\n"
            "- Follow all best practices in SKILL.md rules if available."
        )


# ===== INIT =====
Config.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


# ===== STARTUP CHECK =====
def validate():
    if not Config.MIMO_API_KEY:
        print("⚠️ WARNING: MIMO_API_KEY is empty")

    if not Config.GEMINI_API_KEY:
        print("⚠️ WARNING: GEMINI_API_KEY is empty")

    # Important: avoid debugging failures caused by unset base URL.
    if Config.MIMO_BASE_URL is None:
        print("ℹ️ INFO: MIMO_BASE_URL not set, using OpenAI default endpoint")


validate()
