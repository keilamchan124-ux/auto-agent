import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="建立 Agent 任務清單 (todo.txt)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("task", type=str, help="任務的主要目標描述")
    parser.add_argument(
        "-p", "--preset", 
        type=str, 
        choices=["frontend", "backend", "debug", "research", "new_project"], 
        help="要掛載的技能組合 Preset:\n"
             "  frontend   : UI 工程 + 瀏覽器測試 + API 設計\n"
             "  backend    : API 設計 + 資訊安全 + TDD\n"
             "  debug      : 除錯 + Code Review + 瀏覽器測試\n"
             "  research   : 規劃 + 文件 + 想法收斂\n"
             "  new_project: 規格驅動 + 任務規劃 + Git"
    )
    parser.add_argument("-s", "--skills", type=str, nargs="+", help="其他想額外掛載的單獨技能 (以空白分隔)")
    parser.add_argument("-f", "--file", type=str, default="todo.txt", help="輸出檔案位置 (預設 todo.txt)")
    
    args = parser.parse_args()
    
    lines = []
    
    if args.preset:
        lines.append(f"請先使用 load_preset 工具載入 \"{args.preset}\" 技能組合。")
    
    if args.skills:
        for skill in args.skills:
            lines.append(f"請使用 get_skill 工具載入 \"{skill}\" 技能。")
            
    if lines:
        lines.append("") # blank line
        
    lines.append(f"任務目標：\n{args.task}")
    
    out_path = Path(args.file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    
    print(f"[SUCCESS] 任務已成功寫入 {out_path.absolute()}")
    print("Agent 正在待命中，很快就會接手處理！")

if __name__ == "__main__":
    main()
