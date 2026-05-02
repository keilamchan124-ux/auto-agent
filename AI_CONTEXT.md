# Agent V7.2 — Architecture Context (Maintainer Edition)

## 1) Runtime model

The system is an autonomous execution loop:

1. Read task
2. Ask model for action JSON
3. Execute tool
4. Persist progress/trace
5. Recover or continue

Primary model is Mimo, rescue model is Gemini.

## 2) Module boundaries

- `main.py`: single-instance bootstrap and lifecycle entrypoint.
- `core/agent.py`: orchestration, guards, rescue flow, continuation queueing.
- `core/tools.py`: all executable tools with structured JSON output.
- `core/config.py`: env config, prompt rules, limits, allowlists.
- `core/llm.py`: model wrappers with retry/backoff.

## 3) Observability topology

- Global trace: `workspace/execution_trace.jsonl`
- Task trace: `workspace/artifacts/traces/<task_id>.jsonl`
- Task summary: `workspace/artifacts/task_summaries/<task_id>.summary.json`
- Live progress: `workspace/artifacts/runtime_progress.json`
- Dashboard: `workspace/artifacts/dashboard.html`

## 4) Stitch/Flutter workflow

Stitch mode uses explicit task schema:

- `[MODE]=STITCH_FLUTTER`

Typical loop:

1. Build web (`flutter build web`)
2. Start local server (`start_web_server`)
3. Capture screenshot (`capture_web_screenshot`)
4. Compare against metadata/checklist
5. Validate quality (`validate_mobile_quality`)
6. Stop local server (`stop_web_server`)

## 5) Current shortcomings and possible bugs

### A. Architecture density
`core/agent.py` still holds many responsibilities (loop, telemetry, continuation, policy, rescue). This raises regression risk when touching one area.

### B. Web-server lifecycle complexity
Even with start/stop/status tools, server lifecycle correctness still depends on metadata integrity and process ownership assumptions.

### C. Environment-sensitive validation
Flutter and browser-dependent checks can fail due to environment drift rather than product defects.

### D. Optional smoke CI
Smoke integration is intentionally optional. This reduces mandatory CI friction but leaves gaps unless teams enable it consistently.

## 6) Recommended improvements

1. Split `core/agent.py` into focused modules:
   - `core/loop.py`
   - `core/recovery.py`
   - `core/telemetry.py`
   - `core/policy.py`
2. Add metadata ownership fields and lock semantics for web-server artifacts.
3. Add policy-level mode contracts (`general`, `mobile`, `stitch_flutter`) with explicit gate requirements.
4. Add more real integration assertions in smoke tests (visual diff thresholds, stable startup retries, artifact sanity checks).

## 7) Quality principles for future changes

- Keep tool schemas stable (`ok`, `message`, `data`, `error_type`).
- Preserve deterministic fallback behavior.
- Keep prompts and tool registry synchronized.
- Keep all comments/messages in English for maintainability.
