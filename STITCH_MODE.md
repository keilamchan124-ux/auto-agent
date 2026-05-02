# Stitch Reference Development Mode

This mode is designed for long-running autonomous Flutter development using design references (for example, Stitch-generated screens).

## 1) Mission task template

Use this template as the input task (`todo.txt`) for each feature batch.

```text
[MODE] STITCH_FLUTTER
[GOAL] Build/extend mobile app screens from Stitch references.

[INPUTS]
- design_refs: (list of image links or local file paths)
- product_requirements: (bullet list)
- tech_constraints: (Flutter version, package limits, target Android/iOS)
- acceptance_checks: (must-pass checks)

[OUTPUTS REQUIRED]
1. design/component_metadata.json
2. implementation checklist file
3. code changes for target screens/components
4. test updates
5. quality gate result (analyze/test/build)
6. dashboard update

[RULES]
- Plan first, then execute incrementally.
- Keep each change small and testable.
- If execution budget is exhausted, generate continuation checklist and queue next task.
- Never call mark_done until quality gate passes.
```

## 2) Tool-call strategy

### Phase A: Intake and planning
1. `plan`
   - Create a step list with explicit milestones.
2. `design_to_component_metadata`
   - Convert design refs into component-tree metadata and checklists.
3. `write_file`
   - Save iteration checklist (`design/iteration_checklist.md`).

### Phase B: Implementation loop
Repeat until all checklist items are complete:
1. `read_file` / `github_read_file`
   - Inspect current code and metadata.
2. `write_file` / `run_cmd`
   - Implement one screen or one reusable component at a time.
3. `run_cmd`
   - Run focused checks (format/lint/local build command where applicable).
4. `append trace + progress`
   - Already handled by the agent runtime.

### Phase B.5: Web visual feedback loop (mandatory for web-first review)
1. `run_cmd`
   - Build web: `flutter build web`
2. `start_web_server`
   - Start local server from `build/web` and persist server metadata.
3. `capture_web_screenshot`
   - Capture reference screenshots from the running web app.
4. `design_to_component_metadata` / `read_file`
   - Compare screenshot outcomes with metadata and checklist gaps.
5. Stop server or reuse controlled session for next iteration.
   - Preferred: call `stop_web_server` when an iteration ends.

### Phase C: Validation gate (mandatory)
1. `validate_mobile_quality`
   - Must pass `flutter pub get`, `flutter analyze`, `flutter test`, `flutter build apk --debug`, `flutter build web`, and `flutter test --platform chrome`.
   - Web strictness can be configured via `strict_web` (`False` = treat web check failures as warning, `True` = hard fail).
2. If failed:
   - Return to implementation loop and fix failures.
3. If passed:
   - Continue to completion checks.

### Phase D: Completion and reporting
1. `render_progress_dashboard`
   - Refresh dashboard artifact.
2. `read_file` on checklist + metadata
   - Confirm all planned items are complete.
3. `mark_done`
   - Allowed only after gate pass and completion checks.

## 3) Definition of Done (DoD)

A task is complete only if all conditions are true:

1. **Design mapping complete**
   - `design/component_metadata.json` exists and includes all target screens.
2. **Checklist complete**
   - No unchecked implementation items remain.
3. **Code complete**
   - Screens/components compile and integrate with app navigation/state.
4. **Quality gate passed**
   - `validate_mobile_quality` returns `all_passed=true`.
5. **Observability updated**
   - `runtime_progress.json`, per-task trace, and dashboard are updated.
6. **Handoff-ready summary**
   - `mark_done` summary states what was built, tested, and any follow-up work.

## 4) Long-running continuation policy

- Use the first execution budget window for coding and integration.
- If unfinished, use planning window to produce the next checklist batch.
- Agent auto-queues continuation tasks with trace summary context.
- Always resume from task-scoped trace (`workspace/artifacts/traces/<task_id>.jsonl`).

## 5) Recommended companion skills

- `planning-and-task-breakdown`
- `incremental-implementation`
- `frontend-ui-engineering`
- `debugging-and-error-recovery`
- `test-driven-development`
- `code-review-and-quality`
