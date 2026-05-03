# Agent V7.2

Autonomous loop-based Python agent for long-running execution, recovery, and artifacted observability.

> Last updated: 2026-05-03 (UTC) — modular services refresh

## Quick start

1. Create and activate a Python environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `.env` (copy from `.env.example`).
   - Required: `MIMO_API_KEY`
   - Recommended rescue chain config:
     - `NIM_API_KEY`
     - `NIM_BASE_URL=https://integrate.api.nvidia.com/v1`
     - `NIM_RESCUE_MODEL=z-ai/glm4.7`
     - `GEMINI_API_KEY`
     - `GEMINI_MODEL=gemini-3.1-flash-lite-preview`
     - `RESCUE_MODEL=gemma-4-31b-it`
4. Run:
   ```bash
   python main.py
   ```

## Architecture

- `core/agent.py`: main orchestration loop and task lifecycle.
- `core/state_trace.py`: runtime progress + trace writing manager.
- `core/task_orchestrator.py`: mission prompt + env-lock message construction.
- `core/skill_router.py`: auto-select/preload skill routing and context offload.
- `core/mcp_policy_engine.py`: MCP registry + phase/usage policy enforcement.
- `core/error_handler_service.py`: post-action state transitions and repair prompts.
- `core/command_normalizer.py`: centralized Windows/Unix command normalization rules.
- `core/recovery.py`, `core/rescue_orchestrator.py`: rescue triggers and orchestration.
- `core/llm.py`: model clients + fixed rescue chain + decision matrix.
- `core/tools.py`: tool execution and safety boundaries.
- `core/action_router.py`: centralized action dispatch and execution error normalization.
- `core/agent_loop.py`: loop-level coordination helpers for dispatch/completion.
- `core/modes.py`: STITCH/mobile mode-specific heuristics and gating helpers.

## Fixed rescue chain

Fallback order is deterministic:

1. GLM via NVIDIA NIM
2. Gemini
3. Gemma via MIMO/OpenAI-compatible endpoint

`core/llm.py` now includes:
- `_classify_error_code(...)`
- `get_rescue_decision(...)` decision matrix
- `LAST_RESCUE_EVENTS` structured fallback telemetry

## CI workflows

- `prompt-tool-registry-consistency`: ensures prompt action list matches tool registry.
- `mandatory-minimal-integration`: always runs a minimal non-mock smoke path in CI.

## Runtime artifacts

- `workspace/state.json`
- `workspace/execution_trace.jsonl`
- `workspace/artifacts/traces/<task_id>.jsonl`
- `workspace/artifacts/task_summaries/<task_id>.summary.json`
- `workspace/artifacts/runtime_progress.json`
- `workspace/artifacts/dashboard.html`
- `workspace/artifacts/rescue_events.jsonl`

`render_progress_dashboard` now includes rescue event summary cards sourced from `rescue_events.jsonl`.

## Known gaps

1. `core/agent.py` still contains substantial orchestration complexity.
2. Web-server lifecycle is file-metadata-based and not distributed-runner safe.
3. Full mobile/browser integration confidence still depends on runner environment quality.


## Recent runtime-control updates

- Rescue prompt contract in `core/llm.py` was tightened for stricter JSON-only output and more actionable recovery instructions.
- Policy repair payloads in `core/tools.py` now include `suggested_repair_action` for auto-remediation guidance.
