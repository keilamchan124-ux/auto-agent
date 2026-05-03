# Agent V7.2 — Architecture Context

> Last updated: 2026-05-03 (UTC) — service split + MCP policy unification

## Runtime loop

1. Read task
2. Request action JSON from model
3. Execute tool
4. Persist trace/progress
5. Continue or enter rescue

Primary LLM path is MIMO; rescue fallback order is fixed:

1. NIM/GLM
2. Gemini
3. Gemma (MIMO)

## Current module responsibilities

- `main.py`: process lock + startup lifecycle
- `core/agent.py`: orchestration entrypoint and high-level loop control
- `core/action_router.py`: action dispatch facade + execution-error normalization
- `core/agent_loop.py`: loop-level dispatch/completion helper
- `core/task_orchestrator.py`: mission prompt + environment lock message construction
- `core/skill_router.py`: skill auto-routing and preload/offload lifecycle
- `core/mcp_policy_engine.py`: MCP registry selection + phase gate + usage floor + routing directives
- `core/error_handler_service.py`: centralized result/error state transitions and repair prompting
- `core/command_normalizer.py`: centralized cross-platform command normalization
- `core/modes.py`: task-mode helpers for STITCH cadence and mobile quality gates
- `core/state_trace.py`: runtime progress and trace persistence
- `core/policy.py`: task mode detection
- `core/recovery.py`: rescue trigger policy
- `core/rescue_orchestrator.py`: rescue call coordination + event sink
- `core/telemetry.py`: artifact updates + trace rotation
- `core/llm.py`: model wrappers, error classification, rescue decision matrix
- `core/tools.py`: executable tool registry and command/file/network primitives

## Observability surface

- Global trace: `workspace/execution_trace.jsonl`
- Task trace: `workspace/artifacts/traces/<task_id>.jsonl`
- Task summary: `workspace/artifacts/task_summaries/<task_id>.summary.json`
- Progress: `workspace/artifacts/runtime_progress.json`
- Dashboard: `workspace/artifacts/dashboard.html`
- Rescue events: `workspace/artifacts/rescue_events.jsonl`
- Dashboard now renders rescue event summary + latest rescue event list from JSONL.

## Policy notes

- MCP usage is phase-aware (implementation vs UI verification).
- Completion lock disallows premature `mark_done` without completion signal.
- Rescue guidance now includes a deterministic decision matrix by error code.

## CI status

- Prompt/registry consistency gate is required.
- Minimal integration workflow is required and non-mock in CI setup.

## Remaining risks

1. `agent.py` still has a large surface area.
2. Browser/mobile integration behavior is sensitive to CI runner dependencies.
3. File-based server metadata may need stronger locking semantics.
4. Mode logic is extracted but can be split further into per-mode strategy objects when scope grows.
