# Stitch Reference Development Mode

> Last updated: 2026-05-03 (UTC) — continuation guard + lease-aware web verify + stage-2 loop split context

## Required task header

```text
[MODE]=STITCH_FLUTTER
[GOAL] Build/extend mobile app screens from Stitch references.
```

## Standard phase flow

### A) Intake + plan
1. `plan`
2. `design_to_component_metadata`
3. `write_file` for checklist

### B) Implementation loop
1. `read_file` / `github_read_file`
2. `write_file` / `run_cmd`
3. Focused checks (`run_cmd`)
4. Review task trace/progress artifacts
5. If this is a continuation task, run an inventory scan first (`run_cmd` with `ls` or `dir /b`) before edits.

### C) UI verify loop
1. `flutter build web`
2. `start_web_server`
3. `capture_web_screenshot`
4. `web_server_status`
   - This call refreshes lease heartbeat/expiry in metadata; use it periodically during long screenshot/debug loops.
5. metadata/checklist compare
6. `stop_web_server`

### D) Quality gate
Run `validate_mobile_quality` with:
- `include_web=true`
- `strict_web=true`

Expected checks include:
- `flutter pub get`
- `flutter analyze`
- `flutter test`
- `flutter build apk --debug`
- `flutter build web`
- `flutter test --platform chrome`

### E) Completion
Use `mark_done` only when:
1. checklist complete
2. quality gate passed
3. UI/web warnings resolved
4. trace/progress artifacts updated

## MCP profile for Stitch

- Implementation-first: `context7`, `github`, `codegeneratormcp`
- UI verify on-demand: `chrome-devtools`, `web-visual-feedback`
- Optional security lane: `semgrep`

## Artifact contract

- `design/component_metadata.json`
- `workspace/artifacts/runtime_progress.json`
- `workspace/artifacts/traces/<task_id>.jsonl`
- `workspace/artifacts/task_summaries/<task_id>.summary.json`
- `workspace/artifacts/dashboard.html`
- `workspace/artifacts/rescue_events.jsonl`
- `workspace/artifacts/web_server_<task_id>_<port>.json`
  - includes `lease_owner`, `lease_heartbeat_at`, `lease_expires_at`, `lease_seconds`, `meta_version`
- `workspace/artifacts/web_server_logs/stdout.log`
- `workspace/artifacts/web_server_logs/stderr.log`


## Mode helper mapping

- UI verify cadence and semantic trigger logic are centralized in `core/modes.py:is_ui_verify_phase`.
- Mobile completion guard logic is centralized in `core/modes.py:should_block_mobile_mark_done`.
- Mobile quality parsing is centralized in `core/modes.py:extract_mobile_quality_state`.
- Rescue branch coordination is centralized in `core/agent_rescue_coordinator.py`.
- Step-level `mark_done` handling is centralized in `core/agent_step_executor.py`.
