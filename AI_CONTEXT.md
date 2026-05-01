# 🤖 Agent V7.2 — Project Context & Architecture

> **To the AI reading this:** This document provides the complete context of the "Agent V7.2" project. Use this to quickly understand the structure, design patterns, and capabilities before suggesting changes or answering questions.

## 📌 Project Overview

**Agent V7.2** is a fully autonomous, loop-driven execution agent built in Python. It acts as an "Executor" — reads tasks from `todo.txt`, plans, searches the web, browses pages, runs terminal commands, executes Python scripts, and self-repairs errors. It supports dual-model architecture (Mimo + Gemini rescue), **proactive skill discovery with auto-routing**, lazy-loaded engineering skills with **Lean Injection (Skill Budget)**, Telegram bot remote control, and Antigravity ecosystem integration (including `marimo` reactive notebooks).

---

## 📂 Project Structure

```text
/ (Project Root)
├── main.py                  # Entry point. Calls `Agent().start()`.
├── start_agent.bat          # Keep-alive wrapper: auto-restarts on crash.
├── create_task.py           # CLI helper to write structured tasks to todo.txt.
├── telegram_bot.py          # Telegram bot interface for remote task submission.
├── todo.txt                 # Agent polls this file. Writing a prompt here triggers execution.
├── requirements.txt         # Dependencies (openai, google-genai, json-repair, markitdown, ddgs, etc.)
├── .env                     # Environment variables (API keys, Telegram token, model config)
├── .gitignore               # Excludes .env, workspace/, __pycache__/, *.log, etc.
├── workspace/               # Sandboxed directory for agent file I/O and tool execution.
│   ├── state.json           # Persistent counters (parse fails, repeat counts) survive restarts.
│   ├── execution_trace.jsonl# Append-only log of all actions taken and their results.
│   └── artifacts/           # Agent writes execution reports here.
├── .agents/skills/          # Addy Osmani's agent-skills collection (SKILL.md files). 22 skills.
└── core/                    # Core backend logic package
    ├── __init__.py
    ├── agent.py             # Main execution loop, auto skill router, history management, state.
    ├── config.py            # Config, System Prompt, SKILL_PRESETS, SKILL_TAGS for routing.
    ├── llm.py               # API wrappers (Mimo for execution, Gemini for rescue).
    └── tools.py             # Tool implementations and registry (13 tools incl. list_skills).
```

---

## 🧠 Core Architecture & Workflows

### 1. Dual-Model Architecture & Fallbacks (`core/llm.py`)
- **Primary Executor (Mimo)**: Uses `mimo-v2.5-pro` via OpenAI SDK. Outputs strict JSON blocks with `action` + `kwargs`. Supports `reasoning_effort: high`.
- **Rescue Supervisor (Gemini)**: Uses `gemini-3-flash-preview`. Activated when the primary model gets stuck.
- **Local Repair Pre-check**: For trivial format errors (e.g. missing `steps` in `plan`), the agent self-repairs locally, saving Gemini API calls.
- **429 Rate Limit Fallback**: If Gemini's quota is exhausted, the agent automatically falls back to a local robust plan rather than crashing.
- **Rescue Cooldown**: 3-step cooldown prevents API spam loops.

### 2. State & Persistence (`core/agent.py`)
- `AgentState` dataclass tracks: `repeat_count`, `parse_fail_count`, `error_count`, `search_count`, `hard_reset_count`, and `loaded_skills` (for skill budgeting).
- Saved to `workspace/state.json`. If crashed and restarted by `start_agent.bat`, the agent resumes with counters intact.

### 3. History Management (`trim_history`)
- Context is aggressively managed to fit within `MAX_CONTEXT_CHARS` (default 60,000).
- Keeps: System Prompt + initial task + most recent N messages (capped by `MAX_HISTORY`).

### 4. Robust JSON Parsing
- Three-tier extraction: fenced ```json blocks → `json_repair` on full text → raw regex `{...}` fallback.
- Handles broken/malformed LLM outputs gracefully.

### 5. Tools Engine (`core/tools.py`)
13 registered tools with strict schema constraints:

| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo search. Cached via `@lru_cache(16)`. |
| `browse_page` | Fetches URL → converts HTML/PDF to Markdown via `markitdown`. |
| `download_file` | Downloads files. Blocks HTML pages from being saved as files. |
| `run_cmd` | Terminal commands. Guarded by `ALLOWED_BINARIES` whitelist. |
| `write_file` | Write to workspace (sandboxed). |
| `read_file` | Read from workspace (sandboxed). |
| `run_python_script` | Executes Python code. Optional domain-level network guard. |
| `list_skills` | **NEW** — Lists all available skills with descriptions + keyword filtering. |
| `get_skill` | Lazy-loads a single skill from `.agents/skills/<name>/SKILL.md`. |
| `load_preset` | Loads a preset skill combo (e.g. `frontend`, `backend`, `debug`). |
| `plan` | Records a plan for the agent's next steps. |
| `git_commit` | Runs `git add . && git commit -m <msg>`. |
| `mark_done` | Signals task completion. Writes execution report. |

### 6. Proactive Skill System (Three-Layer Architecture)

#### Layer 1: Thinking-First System Prompt
The System Prompt instructs the agent to follow a mandatory workflow:
1. **THINK** → Analyze task domain and complexity
2. **DISCOVER** → Call `list_skills` to explore available skills
3. **LOAD** → Use `get_skill` (2-4 times) to load relevant skills
4. **PLAN** → Outline execution steps
5. **EXECUTE** → Carry out the plan
6. **FINISH** → Call `mark_done`

#### Layer 2: `list_skills` Tool
- Scans `.agents/skills/` directory for all available skills
- Returns name, description, keywords, and file availability for each skill
- Supports keyword filtering via `query` parameter
- Uses `SKILL_TAGS` from config for rich metadata

#### Layer 3: Auto Skill Router (`agent.py`)
- `_auto_select_skills(task)`: Rule-based keyword scoring against `SKILL_TAGS`
  - Multi-word keywords score higher (2 points vs 1)
  - Selects top 2-4 skills by score
  - Falls back to `planning-and-task-breakdown` if no keywords match
  - Supplements from `SKILL_PRESETS` if only 1 skill matches
- `_preload_skills(skills, msgs)`: Loads selected skills into System Prompt before loop starts
- Notifies agent which skills are pre-loaded to avoid redundant discovery

### 7. Skill Injection & Budgeting
When `get_skill` or `load_preset` succeeds, the skill is processed via **Lean Injection** (`_summarize_skill`). Instead of injecting large files verbatim, it intelligently extracts headings and key bullet points, truncating at `SKILL_SUMMARY_MAX_CHARS` (default 600).
- **Skill Budget**: The agent tracks active skills (`self.state.loaded_skills`) and blocks loading if it exceeds `MAX_SKILLS_LOADED` (default 4) to prevent context window explosion.
- The summarized content is appended directly into the System Prompt (`msgs[0]`).

### 8. Telegram Bot (`telegram_bot.py`)
- Remote task submission via Telegram messages.
- Commands: `/start`, `/status`, `/report`.
- Auth: `TELEGRAM_ALLOWED_USER_ID` env var restricts access to a single user.
- Writes tasks to `todo.txt`, which the main agent loop picks up.

### 9. Antigravity Mode
- Detected via `ANTIGRAVITY_MODE=1` env var or `.antigravity` folder in workspace.
- Enables: mandatory artifact generation, terminal review policies, SKILL.md best practices.

---

## 🔧 Configuration (`core/config.py`)

All config is loaded from environment variables (`.env` file) with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMO_API_KEY` | — | Primary model API key |
| `GEMINI_API_KEY` | — | Rescue model API key |
| `MIMO_MODEL` | `mimo-v2.5-pro` | Primary model name |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Rescue model name |
| `MIMO_BASE_URL` | OpenAI default | Custom endpoint URL |
| `MAX_STEPS` | `40` | Max execution steps per task |
| `MAX_HISTORY` | `20` | Max messages kept in context |
| `MAX_CONTEXT_CHARS` | `60000` | Character budget for context window |
| `MAX_SKILLS_LOADED` | `6` | Limit for concurrent skills in context |
| `SKILL_SUMMARY_MAX_CHARS`| `600` | Truncation limit for skill injection |
| `POLL_INTERVAL` | `2` | Seconds between todo.txt polls |
| `ALLOWED_BINARIES` | `python,python3,pip,pip3,ls,cat,echo,git` | Whitelist for `run_cmd` |
| `ALLOWED_DOMAINS` | `*` | Network guard for `run_python_script` |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_ALLOWED_USER_ID` | — | Authorized Telegram user ID |

---

## 🛠️ How to Assist the User

| User Request | Relevant Files |
|---|---|
| "Add a new tool" | `core/tools.py` (implement + register), `core/config.py` (update `_BASE_PROMPT` actions list) |
| "Agent is stuck in a loop" | `core/agent.py` (guard logic), `core/llm.py` (rescue prompt) |
| "Change agent personality" | `core/config.py` (`SYSTEM_PROMPT`) |
| "LLM API failing / new provider" | `core/llm.py` |
| "Telegram bot issue" | `telegram_bot.py`, `.env` |
| "Task creation / presets" | `create_task.py`, `core/config.py` (`SKILL_PRESETS`) |

### Code Style Guidelines
- **Typing**: Strict Python type hints (`from typing import List, Dict, Any`, etc.)
- **Future imports**: All core files use `from __future__ import annotations`
- **Encoding**: `# -*- coding: utf-8 -*-` as the first line
- **Error handling**: Tools return structured JSON via `format_result(ok, message, data, error_type)`. Never raise raw exceptions to the LLM.
- **Security**: All file I/O sandboxed to `workspace/` via `safe_path()`. Commands restricted by `ALLOWED_BINARIES`. Network restricted by `ALLOWED_DOMAINS`.
