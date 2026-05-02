# Stitch Reference Development Mode

This playbook defines a reliable long-running Flutter workflow using Stitch design references.

## 1) Required task schema

Use this exact header in `todo.txt`:

```text
[MODE]=STITCH_FLUTTER
[GOAL] Build/extend mobile app screens from Stitch references.

[INPUTS]
- design_refs: list of image links or local file paths
- product_requirements: bullet list
- tech_constraints: Flutter version, package limits, target Android/iOS
- acceptance_checks: must-pass checks
```

If `[MODE]=STITCH_FLUTTER` is missing, mobile-specific gate behavior is not guaranteed.

## 2) Standard execution phases

### Phase A — Intake and planning
1. `plan`
2. `design_to_component_metadata`
3. `write_file` (iteration checklist)

### Phase B — Implementation loop
Repeat until checklist is complete:
1. `read_file` / `github_read_file`
2. `write_file` / `run_cmd`
3. `run_cmd` for focused checks
4. rely on runtime trace/progress artifacts

### Phase C — Web visual validation loop
1. `run_cmd` -> `flutter build web`
2. `start_web_server` with `task_id` and port
3. `capture_web_screenshot`
4. `web_server_status` for health + log-tail checks
5. compare results against metadata/checklist
6. `stop_web_server` using the exact metadata path

### Phase D — Quality gate (mandatory)
Call `validate_mobile_quality`.

Default policy in Stitch mode:
- `include_web=true`
- `strict_web=true`

Required checks:
- `flutter pub get`
- `flutter analyze`
- `flutter test`
- `flutter build apk --debug`
- `flutter build web`
- `flutter test --platform chrome`

### Phase E — Completion
Call `mark_done` only when all are true:
1. metadata and checklist complete
2. quality gate passed
3. web warning count is zero
4. dashboard and traces updated

## 3) Artifact contract

Expected artifacts:
- `design/component_metadata.json`
- `workspace/artifacts/runtime_progress.json`
- `workspace/artifacts/traces/<task_id>.jsonl`
- `workspace/artifacts/task_summaries/<task_id>.summary.json`
- `workspace/artifacts/dashboard.html`
- `workspace/artifacts/web_server_<task_id>_<port>.json`
- `workspace/artifacts/web_server_logs/stdout.log`
- `workspace/artifacts/web_server_logs/stderr.log`

## 4) Continuation policy for long runs

- Use execution window for coding.
- Use planning window for next-batch checklist.
- If unfinished, rely on auto-queued continuation task.
- Resume from task-scoped trace first, not global trace.

## 5) Recommended companion skills

- `planning-and-task-breakdown`
- `incremental-implementation`
- `frontend-ui-engineering`
- `debugging-and-error-recovery`
- `test-driven-development`
- `code-review-and-quality`


