from __future__ import annotations

from typing import Dict, List, Any, Optional
import logging

from core.config import Config
from core import llm, rescue_orchestrator


class AgentRescueCoordinator:
    @staticmethod
    def request_next_action(agent, msgs: List[Dict[str, str]], step: int) -> Optional[Dict[str, Any]]:
        logger = logging.getLogger("AgentV7.2")
        need_rescue = agent.should_force_rescue()

        if need_rescue:
            if agent.rescue_cooldown > 0:
                agent.rescue_cooldown -= 1
                need_rescue = False
            else:
                logger.warning("🆘 Agent stuck. Trying local repair first...")
                local_repair_success = agent._try_local_repair()
                if local_repair_success:
                    logger.info("✅ Local repair succeeded, skipping Gemini rescue.")
                    agent.state.error_count = 0
                    agent.state.repeat_count = 0
                    agent.rescue_cooldown = 1
                    return None

                logger.warning("⚠️ Local repair failed, invoking Gemini rescue...")
                stuck_reason = "Unknown stuck reason."
                if agent.state.error_count >= 3:
                    if agent.state.last_error and (
                        "missing" in str(agent.state.last_error).lower()
                        or "unexpected keyword" in str(agent.state.last_error).lower()
                        or "not found" in str(agent.state.last_error).lower()
                    ):
                        stuck_reason = f"TOOL PARAMETER ERROR: {agent.state.last_error}"
                    else:
                        stuck_reason = f"RUNTIME ERROR: {agent.state.last_error}"
                elif agent.state.repeat_count >= 2:
                    stuck_reason = f"REPEATING ACTION LOOP: Repeated {agent.state.last_action} {agent.state.repeat_count} times."
                elif agent.state.search_count >= 4:
                    stuck_reason = "SEARCH LOOP: Performed too many consecutive web searches."

                error_summary_prompt = (
                    "You made an incorrect action.\n"
                    f"Failure source: action `{agent.state.last_action}` failed.\n"
                    "Summarize the mistake in one sentence and state what to do next time.\n"
                    "Format: {\"action\":\"plan\",\"kwargs\":{\"steps\":\"My mistake was ...; next I will ...\"}}"
                )
                msgs.append({"role": "user", "content": error_summary_prompt})

                rescue_text = rescue_orchestrator.run_rescue(
                    trim_history_fn=agent.trim_history,
                    msgs=msgs,
                    stuck_reason=stuck_reason,
                    simple_fallback_plan_fn=agent._simple_fallback_plan,
                    workspace_dir=Config.WORKSPACE_DIR,
                    run_id=agent.current_task_id or "",
                    task_id=agent.current_task_id or "",
                    step=step,
                )
                agent.rescue_cooldown = 3
                parsed = agent.extract_json(rescue_text)
                agent.state.parse_fail_count = 0
                agent.state.repeat_count = 0
                agent.state.search_count = 0
                agent.state.error_count = 0
                if not parsed:
                    msgs.append({"role": "user", "content": "RESCUE ERROR: return exactly one fenced JSON block."})
                    return None
                return parsed

        try:
            resp = llm.call_mimo(agent.trim_history(msgs))
            content = resp.get("content", "")
            return agent.extract_json(content)
        except Exception as e:
            agent.state.error_count += 1
            agent.state.last_error = f"call_mimo_exception: {e}"
            agent.save_state()
            logger.warning("⚠️ call_mimo raised exception: %s", e)
            msgs.append({
                "role": "user",
                "content": (
                    "MODEL CALL ERROR: primary model call failed due to network/runtime error. "
                    "Switch to a minimal recovery action (plan with one concrete next step), then continue."
                ),
            })
            return None
