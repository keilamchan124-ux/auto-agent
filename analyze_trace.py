# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def analyze() -> None:
    workspace = Path("workspace")
    progress_path = workspace / "artifacts" / "runtime_progress.json"
    global_trace_path = workspace / "execution_trace.jsonl"

    if not progress_path.exists() and not global_trace_path.exists():
        print("No trace artifacts found.")
        return

    task_id = "unknown"
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text("utf-8"))
            task_id = str(progress.get("task_id") or "unknown")
        except Exception:
            task_id = "unknown"

    task_trace_path = workspace / "artifacts" / "traces" / f"{task_id}.jsonl"
    traces = _load_jsonl(task_trace_path) if task_trace_path.exists() else _load_jsonl(global_trace_path)

    if not traces:
        print("Trace is empty.")
        return

    if task_id == "unknown":
        task_id = str(traces[-1].get("task_id", "unknown"))

    task_rows = [r for r in traces if str(r.get("task_id")) == task_id] if task_id != "unknown" else traces[-50:]
    actions = Counter(str(r.get("action", "unknown")) for r in task_rows)
    failures = [r for r in task_rows if not bool((r.get("result") or {}).get("ok", False))]

    print("==== Trace Analysis ====")
    print(f"Task ID: {task_id}")
    print(f"Steps: {len(task_rows)}")
    print(f"Failures: {len(failures)}")
    print(f"Actions: {dict(actions)}")

    if failures:
        print("\nRecent failures:")
        for row in failures[-5:]:
            result = row.get("result") or {}
            print(f"- step={row.get('step')} action={row.get('action')} error={result.get('error_type')} msg={str(result.get('message', ''))[:120]}")


if __name__ == "__main__":
    analyze()
