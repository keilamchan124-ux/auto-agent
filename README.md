# Agent V7.2

Autonomous loop-based Python agent for long-running execution, recovery, and artifacted observability.

> Last updated: 2026-05-03 (UTC) — stage-2 agent split + MCP externalization + dependency gate + web-server lease hardening

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
- `core/agent_rescue_coordinator.py`: rescue-vs-primary-call coordination and fallback flow extraction.
- `core/agent_step_executor.py`: step-level mark_done execution handling extraction.

## Fixed rescue chain

Fallback order is deterministic:

1. GLM via NVIDIA NIM
2. Gemini
3. Gemma via Gemini API key

`core/llm.py` now includes:
- `_classify_error_code(...)`
- `get_rescue_decision(...)` decision matrix
- `LAST_RESCUE_EVENTS` structured fallback telemetry

## CI workflows

- `prompt-tool-registry-consistency`: ensures prompt action list matches tool registry.
- `mandatory-minimal-integration`: always runs a minimal non-mock smoke path in CI.
- `import-requirements-consistency`: checks that top-level Python imports are declared in `requirements.txt` (prevents runtime missing dependency regressions such as `ddgs`).

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
2. Web-server lifecycle now uses lease/heartbeat + atomic metadata writes, but still depends on local process semantics across heterogeneous runners.
3. Full mobile/browser integration confidence still depends on runner environment quality.


## Recent runtime-control updates

- Rescue prompt contract in `core/llm.py` was tightened for stricter JSON-only output and more actionable recovery instructions.
- Policy repair payloads in `core/tools.py` now include `suggested_repair_action` for auto-remediation guidance.
- Path canonicalization is now more aggressive (`./`, duplicate separators, repeated `workspace/` prefixes) to reduce continuation path drift.
- Repeat guarding now includes semantic signatures (not only raw action name) to reduce plan/retry loops with near-identical inputs.
- Continuation tasks now require an explicit first-step workspace inventory scan (`run_cmd` with `ls`/`dir`) before other actions.
- Windows command fallback now maps common directory-discovery commands (`find`/`where`/`tree`) to `dir /s /b` when blocked by allowlist.
- Web-server metadata now includes lease owner/expiry/heartbeat and is persisted atomically to reduce cross-runner race windows.
- Primary model-call exceptions are now captured in-loop with state persistence and recovery prompt injection.
### MCP registry customization

- Default registry is built in code (lightweight core MCP set).
- `MCP_SERVERS` (comma-separated) filters enabled servers from the built-in registry (supports aliases like `chrome`, `devtools`, `visual`, `codegen`).
- Recommended stable default for auto-agent: keep only `context7,codegeneratormcp` (optionally add `github` as a 3rd core MCP).
