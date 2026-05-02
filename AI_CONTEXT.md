# Agent V7.2 — Architecture Context (2026)

This document is the operational architecture guide for maintainers and automation agents.

## 1) System model

Agent V7.2 is a loop-based executor:

1. Read task
2. Ask model for next action JSON
3. Execute tool
4. Persist trace/progress
5. Recover or continue until done

Primary model: Mimo. Rescue model: Gemini.

## 2) Core modules and boundaries

- `core/agent.py`
  - Owns orchestration, retry/recovery, step budgets, continuation task queuing.
  - Writes runtime progress and task/global traces.
- `core/tools.py`
  - Executes all runtime tools with a stable JSON result schema.
  - Enforces workspace path safety and command allowlist constraints.
- `core/config.py`
  - Loads environment config and prompt rules.
  - Defines step limits, binary allowlist, domain policies, and skill metadata.
- `core/llm.py`
  - Encapsulates model calls and retry/backoff behavior.
- `core/__init__.py`
  - Kept side-effect free (no eager module initialization).

## 3) Reliability and continuation mechanics

- Structured action parsing with repair fallback.
- Loop guards for repeat/search/error/parse-fail pressure.
- Step-budget split for long tasks:
  - execution window
  - planning window
- Automatic continuation task queue when unfinished.
- Quality gate before completion (`validate_mobile_quality`).

## 4) Observability architecture

Artifacts are designed for low-overhead monitoring and postmortem replay:

- `workspace/state.json`
- `workspace/execution_trace.jsonl` (global)
- `workspace/artifacts/traces/<task_id>.jsonl` (task scoped)
- `workspace/artifacts/task_summaries/<task_id>.summary.json`
- `workspace/artifacts/runtime_progress.json`
- `workspace/artifacts/dashboard.html`

Global trace rotation prevents unbounded growth; task-scoped traces keep continuation context clean.

## 5) Stitch/Flutter mode

For design-reference development, follow `STITCH_MODE.md`:

- Design metadata scaffold generation
- Build web + start local server + screenshot capture loop
- Metadata/checklist comparison
- Mandatory quality gate before `mark_done`

## 6) Current architectural optimizations applied

1. Reduced import-time side effects in `core` package initialization.
2. Standardized docs around current runtime topology.
3. Stabilized regression tests against current module boundaries.
4. Added dedicated tools for web visual loop (`start_web_server`, `capture_web_screenshot`).

## 7) Recommended next refactors

- Move artifact writing into a dedicated `core/telemetry.py` module.
- Split `core/agent.py` into `loop`, `recovery`, and `continuation` components.
- Add typed tool result models to reduce schema drift.
- Add CI checks for doc/tool registry consistency.
