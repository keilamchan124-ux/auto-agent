# -*- coding: utf-8 -*-
import json
from pathlib import Path
from collections import Counter

def analyze():
    trace_path = Path("workspace/execution_trace.jsonl")
    if not trace_path.exists():
        print("❌ 找不到 execution_trace.jsonl")
        return

    traces = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                traces.append(json.loads(line))

    if not traces:
        print("📭 Trace 檔案為空")
        return

    # 如果有依照改進建議加入 task_id，我們就可以只抓最後一個任務
    latest_task_id = traces[-1].get("task_id", "unknown")
    current_task_traces = [t for t in traces if t.get("task_id", "unknown") == latest_task_id]
    
    # 相容未加 task_id 的舊格式 (抓最後 25 筆)
    if latest_task_id == "unknown":
        current_task_traces = traces[-25:]

    actions_counter = Counter(t["action"] for t in current_task_traces)
    failures = [t for t in current_task_traces if not t.get("result", {}).get("ok", False)]
    
    print("==== 🕵️ Trace 執行分析報告 ====")
    print(f"🔸 任務 ID: {latest_task_id}")
    print(f"🔸 總執行步數: {len(current_task_traces)}")
    print(f"🔸 動作統計: {dict(actions_counter)}")
    print(f"🔸 錯誤次數: {len(failures)} / {len(current_task_traces)}")
    
    if failures:
        print("\n⚠️ 錯誤細節 (Top 3):")
        for f in failures[-3:]:
            print(f"  [{f.get('step', '?')}] Action: {f['action']}")
            print(f"      Args: {f['kwargs']}")
            print(f"      Err : {f['result'].get('error_type')} - {f['result'].get('msg', f['result'].get('message'))[:150]}")

    print("\n📝 執行軌跡 (最後 5 步):")
    for t in current_task_traces[-5:]:
        status = "✅" if t.get("result", {}).get("ok") else "❌"
        print(f"  Step {t.get('step', '?')} {status} | {t['action']}")

if __name__ == "__main__":
    analyze()