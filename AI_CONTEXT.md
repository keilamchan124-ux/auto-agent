# 🤖 Agent V7.2 Project Context & Architecture

> **To the Web AI reading this:** This document provides the complete context of the "Agent V7.2" project. Please use this to quickly understand the project structure, design patterns, and core capabilities before suggesting code modifications or answering user questions.

## 📌 Project Overview
**Agent V7.2** is a fully autonomous, loop-driven execution agent built in Python. It is designed to act as an "Executor" that reads tasks, plans, searches the web, executes terminal commands, runs Python scripts, and repairs its own errors autonomously. It integrates natively with the **Antigravity** ecosystem and supports lazy-loading of engineering skills.

---

## 📂 Project Structure

```text
/ (Project Root)
├── main.py                  # Entry point for the application. Simply calls `Agent().start()`.
├── start_agent.bat          # Batch script to run the agent in a continuous keep-alive loop.
├── todo.txt                 # The agent polls this file. Writing a prompt here triggers the agent.
├── requirements.txt         # Dependencies (openai, google-genai, json-repair, markitdown, ddgs, etc.)
├── .env                     # Environment variables (API Keys: MIMO_API_KEY, GEMINI_API_KEY)
├── workspace/               # Isolated directory for the agent to execute tools and save outputs.
│   ├── state.json           # Persistent counters (parse fails, repeat counts) to survive restarts.
│   ├── execution_trace.jsonl# Log of all actions taken and their results.
│   └── artifacts/           # Directory where the agent writes its execution reports.
├── .agents/skills/          # Directory containing Addy Osmani's agent-skills (SKILL.md files).
└── core/                    # Core backend logic module
    ├── __init__.py
    ├── agent.py             # Main execution loop, history management, state persistence.
    ├── config.py            # Centralized configurations, System Prompt, and Environment checks.
    ├── llm.py               # Wrappers for API calls (Mimo for execution, Gemini for rescue).
    └── tools.py             # Tool definitions (web_search, run_cmd, run_python_script, get_skill, etc.)
```

---

## 🧠 Core Architecture & Workflows

### 1. Dual-Model Architecture (`core/llm.py`)
- **Primary Executor (Mimo)**: Uses `mimo-v2.5-pro` (via OpenAI SDK). It is instructed to ONLY output strict JSON blocks containing an `action` and `kwargs`. It has no internal thoughts in its output text (to save context), though reasoning is supported via `reasoning_effort`.
- **Rescue Supervisor (Gemini)**: Uses `gemini-3-flash-preview`. If the primary executor gets stuck in a loop, fails to format JSON multiple times, or repeats the same error, `agent.py` truncates the history and calls Gemini to act as a "rescue controller" to break the loop.

### 2. State & Persistence (`core/agent.py`)
- Uses an `AgentState` dataclass to track `repeat_count`, `parse_fail_count`, `error_count`, etc.
- Saves state to `workspace/state.json` dynamically. If the agent crashes and is restarted by `start_agent.bat`, it resumes exactly where it left off with its counters intact.

### 3. Smart History Management
- Context windows are aggressively managed. 
- **`smart_summarize_history`**: When the conversation exceeds 6 steps, the agent extracts the oldest messages and uses Gemini to summarize them into a compact `[歷史摘要]` user message. It retains only the System Prompt, the initial Task, the Summary, and the 4 most recent turns.

### 4. Robust JSON Parsing
- The LLM output is parsed using `json_repair` (`extract_json`). It successfully extracts fenced code blocks (```json) and aggressively repairs broken JSON structures.

### 5. Tools Engine (`core/tools.py`)
The agent has strict schema constraints. Tools include:
- `web_search`: Uses DuckDuckGo (`ddgs`). Cached via `@functools.lru_cache(maxsize=16)`.
- `run_cmd`: Executes terminal commands. Strictly guarded by `ALLOWED_BINARIES` in `config.py` (e.g., `python`, `ls`).
- `run_python_script`: Writes Python code to a temp file and executes it. 
- `get_skill`: Lazy-loads engineering skills from `.agents/skills/<name>/SKILL.md` using Microsoft's `markitdown` for clean parsing.

### 6. Antigravity Ecosystem Integration
- If `IS_ANTIGRAVITY` is True (checked via env vars or `.antigravity` folder), the System Prompt strictly enforces artifact generation and careful terminal execution policies.
- Automatically writes an `agent_execution_report.md` artifact at the end of a task.

---

## 🛠️ How to Assist the User

When the user asks you (the Web AI) to add a feature or fix a bug, please ask for the relevant files based on this mapping:

1. **"I want to add a new tool for the agent to use"**
   👉 Ask the user to upload `core/tools.py` and `core/config.py` (to update the System Prompt).
2. **"The agent is stuck in an infinite loop"**
   👉 Ask the user to upload `core/agent.py` (loop logic) and `core/llm.py` (rescue prompt).
3. **"I want to change the agent's personality or instructions"**
   👉 Ask the user to upload `core/config.py` (`SYSTEM_PROMPT`).
4. **"The LLM API is failing or needs a new model provider"**
   👉 Ask the user to upload `core/llm.py`.

### Code Style Guidelines
- **Typing**: Use strict Python type hints (`from typing import List, Dict, Any`, etc.).
- **Future Imports**: All files must start with `from __future__ import annotations`.
- **Error Handling**: Tools must return a strict JSON string using `format_result(ok: bool, message: str, data: dict, error_type: str)`. Never raise raw exceptions to the LLM.
