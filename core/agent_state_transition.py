from __future__ import annotations
import json
import logging
import shutil
from dataclasses import asdict

from core.config import Config

logger = logging.getLogger("AgentV7.2")


class AgentStateTransition:
    @staticmethod
    def load_state(agent, state_cls) -> None:
        if agent.state_file.exists():
            try:
                data = json.loads(agent.state_file.read_text("utf-8"))
                agent.state = state_cls(**data)
                return
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
        agent.state = state_cls()

    @staticmethod
    def save_state(agent) -> None:
        agent.state_file.write_text(json.dumps(asdict(agent.state), ensure_ascii=False), "utf-8")

    @staticmethod
    def reset_counters(agent, state_cls) -> None:
        agent.state = state_cls()
        AgentStateTransition.save_state(agent)

    @staticmethod
    def clean_workspace() -> None:
        important_files = {"state.json", "execution_trace.jsonl", "todo.txt"}
        for item in Config.WORKSPACE_DIR.iterdir():
            if item.is_file() and item.name not in important_files:
                try:
                    item.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete {item.name}: {e}")
            elif item.is_dir() and item.name not in {"artifacts", ".agents", ".antigravity"}:
                try:
                    shutil.rmtree(item)
                except Exception as e:
                    logger.warning(f"Failed to delete dir {item.name}: {e}")
