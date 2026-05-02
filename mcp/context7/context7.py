# mcp/context7/context7.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class Context7MCP:
    """
    Context7 MCP - 負責長期記憶與多任務上下文管理
    """
    memory: Dict[str, Any] = field(default_factory=dict)
    task_contexts: Dict[str, dict] = field(default_factory=dict)
    max_memory_items: int = 50

    def save_memory(self, key: str, value: Any):
        self.memory[key] = value
        if len(self.memory) > self.max_memory_items:
            # 簡單的淘汰機制（可改進）
            oldest_key = next(iter(self.memory))
            del self.memory[oldest_key]

    def get_memory(self, key: str) -> Optional[Any]:
        return self.memory.get(key)

    def create_task_context(self, task_id: str, initial_data: dict = None):
        self.task_contexts[task_id] = initial_data or {}

    def update_task_context(self, task_id: str, key: str, value: Any):
        if task_id not in self.task_contexts:
            self.task_contexts[task_id] = {}
        self.task_contexts[task_id][key] = value

    def get_task_context(self, task_id: str) -> dict:
        return self.task_contexts.get(task_id, {})

    def clear_task_context(self, task_id: str):
        if task_id in self.task_contexts:
            del self.task_contexts[task_id]