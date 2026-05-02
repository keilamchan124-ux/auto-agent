# Agent V7.2

Autonomous loop-based Python agent for long-running execution, recovery, and artifacted observability.

> Last updated: 2026-05-02 (UTC)

## Quick start

1. Create and activate Python environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `.env` (at least `MIMO_API_KEY`; optionally configure NIM + Gemini for rescue chain).
   - Quick start: copy `.env.example` to `.env` and fill your real keys.
   - Rescue fallback order is fixed: `GLM-4.7 > Gemini 3.1 flash lite > Gemma 4`.
   - Configure GLM via NVIDIA NIM:
     - `NIM_API_KEY=...`
     - `NIM_BASE_URL=https://integrate.api.nvidia.com/v1`
     - `NIM_RESCUE_MODEL=z-ai/glm4.7`
   - Configure Gemini fallback:
     - `GEMINI_API_KEY=...`
     - `GEMINI_MODEL=gemini-3.1-flash-lite-preview`
   - Configure Gemma fallback on MIMO/OpenAI-compatible endpoint:
     - `RESCUE_MODEL=gemma-4-31b-it`
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

## MCP integration (recommended)

The project works best when MCP servers are enabled selectively per task:

- `chrome-devtools`: browser runtime inspection (DOM/console/network/perf).
- `github`: pull requests/issues/file context.
- `web-visual-feedback`: screenshot-driven UI checks.
- `context7`: source-grounded documentation lookup.
- `codegeneratormcp`: implementation-oriented code generation/scaffolding.

Tip: keep `context7`/`github` always-on, and enable browser/visual MCP only for UI tasks to reduce tool-call overhead.
You can register a custom subset with `.env`:
`MCP_SERVERS=chrome-devtools,github,web-visual-feedback,context7,codegeneratormcp,semgrep`.

## Reliability updates (latest)

- `run_python_script` now treats non-zero script exit codes as errors (prevents false-positive "success").  
- `run_cmd` pytest allowance is narrowed to explicit forms only:
  - `pytest ...`
  - `python -m pytest ...`
  - `python3 -m pytest ...`
- NIM rescue now emits structured diagnostics for 401/403/404/429 to speed up debugging.

## Current known gaps (high value fixes)

1. Some logic still lives in one large `core/agent.py`; splitting into `loop`, `telemetry`, and `recovery` modules would improve maintainability.
2. Web-server metadata is file-based and single-node oriented; distributed runner scenarios need stronger ownership/locking.
3. Smoke integration is optional/env-gated; full CI confidence still depends on environment quality.

## Suggested optimization roadmap

- Add MCP-aware routing policy (choose 1–2 MCPs per task based on mode).
- Add stronger integration tests for real Playwright + Flutter environments.
- Add consistency check ensuring prompt action list stays in sync with tool registry.

## Delivery status (Done / In Progress / Planned)

- ✅ **Done**
  - Fixed rescue chain: NIM(GLM) → Gemini → Gemma.
  - Telemetry/policy/recovery/MCP registry modules extracted.
  - Prompt/tool registry CI gate added.
  - Safer `run_cmd` / `run_python_script` hardening landed.

- 🚧 **In Progress**
  - MCP phase-based routing hard policy (implementation vs UI verify) in runtime prompt guidance.
  - Rescue observability enrichment (backend/status/attempt/latency capture).

- 🗓️ **Planned**
  - Stronger integration suites (Playwright + Flutter real-environment assertions).
  - Additional decomposition of `core/agent.py` into finer loop/recovery orchestration units.

## Changelog highlights (recent)

- Added recovery module and rescue event sink (`workspace/artifacts/rescue_events.jsonl`).
- Added prompt/tool registry consistency CI workflow.
- Enforced MCP phase policy guidance in system context.
- Registered `codegeneratormcp` in MCP registry and implementation-phase policy.
- Added semantic UI-verify trigger support (task/todo keywords) with cadence fallback.
- Extended rescue event correlation fields: `run_id`, `task_id`, `step`.
- Optimized MCP registry parsing with alias support and deduped stable ordering.

## MCP quick profile (current)

- Implementation-first MCPs: `context7`, `github`, `codegeneratormcp`
- UI verification MCPs: `chrome-devtools`, `web-visual-feedback`
- Security/quality MCP: `semgrep`
