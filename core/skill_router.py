# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List

from core.config import Config

logger = logging.getLogger("SkillRouter")


class SkillRouter:
    """Auto-select and preload skills for a task."""

    @staticmethod
    def auto_select_skills(task: str, max_skills: int = 4) -> List[str]:
        task_lower = (task or "").lower()
        skill_tags = getattr(Config, "SKILL_TAGS", {})

        scores: Dict[str, int] = {}
        for skill_name, info in skill_tags.items():
            keywords = info.get("keywords", [])
            score = 0
            for kw in keywords:
                if kw in task_lower:
                    score += 2 if " " in kw else 1
            if score > 0:
                scores[skill_name] = score

        if not scores:
            return ["planning-and-task-breakdown"]

        sorted_skills = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [name for name, _ in sorted_skills[:max_skills]]

        if len(selected) == 1:
            presets = getattr(Config, "SKILL_PRESETS", {})
            for preset_skills in presets.values():
                if selected[0] in preset_skills:
                    for s in preset_skills:
                        if s not in selected:
                            selected.append(s)
                            break
                    break

        return selected[:max_skills]

    def preload_skills(
        self,
        skill_names: List[str],
        msgs: List[Dict[str, str]],
        loaded_skills_state: List[str],
        summarize_skill: Callable[[str, str], str],
        execute_tool: Callable[[str, Dict[str, Any]], str],
    ) -> List[str]:
        loaded: List[str] = []
        max_skills = getattr(Config, "MAX_SKILLS_LOADED", 6)
        for skill_name in skill_names:
            current_context_size = sum(len(m.get("content", "")) for m in msgs)
            if current_context_size > 45000 and loaded_skills_state:
                oldest = loaded_skills_state.pop(0)
                logger.warning("⚠️ Context too large, force offload: %s", oldest)

            if len(loaded_skills_state) >= max_skills:
                oldest_skill = loaded_skills_state.pop(0)
                logger.info("🔄 Offloading oldest skill: %s", oldest_skill)

            try:
                result_raw = execute_tool("get_skill", {"skill_name": skill_name})
                result = json.loads(result_raw)
                if result.get("ok") and "data" in result:
                    skill_content = result["data"].get("content", "")
                    if skill_content:
                        if skill_name not in loaded_skills_state:
                            loaded_skills_state.append(skill_name)
                        summarized = summarize_skill(skill_name, skill_content)
                        msgs[0]["content"] += f"\n\n[AUTO-LOADED SKILL: {skill_name}]\n{summarized}"
                        loaded.append(skill_name)
                        logger.info("📦 Auto-loaded skill: %s", skill_name)
            except Exception as e:
                logger.warning("⚠️ Failed to auto-load skill '%s': %s", skill_name, e)
        return loaded
