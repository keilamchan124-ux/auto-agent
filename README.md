# Agent V7.2

A loop-driven autonomous Python agent for task execution, recovery, and artifacted observability.

## What it does

- Reads tasks from `todo.txt`
- Plans and executes tool actions via LLM output
- Persists runtime state, traces, and summaries
- Auto-recovers from format/tool/runtime failures
- Supports long-running Stitch/Flutter workflows

## Quick start

1. Create and activate a Python environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `.env` (at minimum: `MIMO_API_KEY`, `GEMINI_API_KEY`).
4. Run:
   ```bash
   python main.py
   ```

## Project layout

- `main.py` — single-instance bootstrap and run loop entrypoint
- `core/agent.py` — orchestration, loop policy, recovery, progress/trace lifecycle
- `core/tools.py` — tool implementations, safety boundaries, mobile/design/web helpers
- `core/config.py` — environment-driven config and system prompt
- `telegram_bot.py` — remote task submission interface
- `analyze_trace.py` — trace summarization utility
- `STITCH_MODE.md` — design-reference Flutter execution mode

## Runtime artifacts

- `workspace/state.json` — loop counters and error pressure
- `workspace/execution_trace.jsonl` — global trace stream
- `workspace/artifacts/traces/<task_id>.jsonl` — task-scoped trace
- `workspace/artifacts/task_summaries/<task_id>.summary.json` — fast per-task index
- `workspace/artifacts/runtime_progress.json` — live progress snapshot
- `workspace/artifacts/dashboard.html` — rendered monitoring dashboard

## Architecture improvements in this revision

- Package import side effects reduced: `core/__init__.py` no longer eagerly imports all submodules.
- Documentation normalized around one source-of-truth workflow (`README.md` + `AI_CONTEXT.md` + `STITCH_MODE.md`).
- Test baseline aligned with current module topology (`tests/test_regression_stability.py`).

## Development guardrails

- Keep tool output schema stable (`ok/message/data/error_type`).
- Keep action parameter names consistent with `execute_tool` mapping.
- Prefer small iterative changes with explicit validation gates.
