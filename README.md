# MyProject

這是一個基於 Python 與 LLM 的智慧代理 (Agent) 專案。

## 目錄結構

- `core/` - 系統核心程式 (包含最新的 `agent.py`, `llm.py`, `config.py` 等)
- `workspace/` - Agent 的工作區，包含目前的執行狀態 (`state.json`) 以及執行軌跡 (`execution_trace.jsonl`)
- `docs/history/` - 存放過去的歷史任務記錄與相關檔案

## 執行方式

如果需要保持 Agent 24/7 不間斷運作，可以直接點擊或執行根目錄下的批次檔：

```bat
start_247_agent.bat
```

也可以直接透過命令列手動啟動：`python core/agent.py`