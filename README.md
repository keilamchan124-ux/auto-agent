# Agent V7.2

Autonomous loop-based Python agent for long-running execution, recovery, and artifacted observability.

## Quick start

1. Create and activate Python environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `.env` (at least `MIMO_API_KEY`, `GEMINI_API_KEY`).
4. Run:
   ```bash
   python main.py
   ```

## Core architecture

- `core/agent.py`: orchestration loop, recovery, continuation, state gating.
- `core/tools.py`: runtime tools + safety boundaries + web/mobile utilities.
- `core/config.py`: environment-driven limits, prompt, allowlist, skill metadata.
- `core/llm.py`: model client wrappers and retry logic.
- `core/__init__.py`: side-effect-safe package entry.

## Runtime artifacts

- `workspace/state.json`
- `workspace/execution_trace.jsonl`
- `workspace/artifacts/traces/<task_id>.jsonl`
- `workspace/artifacts/task_summaries/<task_id>.summary.json`
- `workspace/artifacts/runtime_progress.json`
- `workspace/artifacts/dashboard.html`

## Current known gaps (high value fixes)

1. Some logic still lives in one large `core/agent.py`; splitting into `loop`, `telemetry`, and `recovery` modules would improve maintainability.
2. Web-server metadata is file-based and single-node oriented; distributed runner scenarios need stronger ownership/locking.
3. Smoke integration is optional/env-gated; full CI confidence still depends on environment quality.

## Suggested optimization roadmap

- Extract telemetry writer into `core/telemetry.py`.
- Extract gate policy into `core/policy.py`.
- Add stronger integration tests for real Playwright + Flutter environments.
- Add consistency check ensuring prompt action list stays in sync with tool registry.
