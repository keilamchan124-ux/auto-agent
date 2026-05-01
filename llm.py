# -*- coding: utf-8 -*-
import time
import logging
from typing import List, Dict, Any

from openai import OpenAI
from google import genai
from config import Config

logger = logging.getLogger("LLM")

GEMINI_CLIENT = genai.Client(api_key=Config.GEMINI_API_KEY)

MIMO_CLIENT = OpenAI(
    api_key=Config.MIMO_API_KEY,
    base_url=Config.MIMO_BASE_URL,
    timeout=120,
    default_headers={
        "User-Agent": "OpenClaw/1.3.5",
        "X-Mimo-Source": "CodingTool"
    }
)


def _sleep_backoff(attempt: int, base: float = 1.5, cap: float = 6.0) -> None:
    delay = min(cap, base * (2 ** attempt))
    time.sleep(delay)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _clean_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keep only role + text, and make sure content is a string.
    This helps avoid leaking weird metadata into the rescue model.
    """
    cleaned = []
    for m in history:
        role = m.get("role", "user")
        if role not in ("system", "user", "assistant", "model"):
            role = "user"

        content = _normalize_text(m.get("content", ""))
        cleaned.append({"role": role, "content": content})
    return cleaned


def call_gemini_rescue(history: list, retries: int = 2) -> str:
    """
    Gemini acts as a rescue supervisor.
    Output must be a single fenced JSON block.
    """
    rescue_prompt = (
        "You are a rescue controller for an execution agent.\n"
        "Return ONLY one fenced JSON block.\n"
        "No explanation. No markdown outside the JSON block. No thoughts.\n"
        "Choose the single best next action to debug errors or recover from loop/format failure.\n"
        "Available actions: web_search, download_file, run_cmd, write_file, read_file, run_python_script, mark_done.\n"
        "Use this exact format:\n"
        "```json\n"
        "{\"action\":\"run_python_script\",\"kwargs\":{\"code\":\"print('Debugging...')\"}}\n"
        "```"
    )

    contents = []
    for m in _clean_history(history):
        role = "user" if m["role"] in ("user", "system") else "model"
        contents.append({
            "role": role,
            "parts": [{"text": m["content"]}]
        })

    contents.append({
        "role": "user",
        "parts": [{"text": rescue_prompt}]
    })

    last_err = None
    for attempt in range(retries + 1):
        try:
            response = GEMINI_CLIENT.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=contents
            )
            text = getattr(response, "text", "") or ""
            return text
        except Exception as e:
            last_err = e
            logger.warning("Gemini rescue failed (attempt %s/%s): %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                _sleep_backoff(attempt)

    logger.error("call_gemini_rescue failed: %s", last_err)
    return "```json\n{\"action\":\"error\",\"kwargs\":{}}\n```"


def call_mimo(messages: list, retries: int = 2) -> dict:
    """
    Main model call.
    Returns a dict with:
      - role
      - content
      - thought
    """
    last_err = None

    # keep only fields we actually need, and normalize content to string
    clean_messages = []
    for m in messages:
        role = m.get("role", "user")
        content = _normalize_text(m.get("content", ""))
        clean_messages.append({"role": role, "content": content})

    for attempt in range(retries + 1):
        try:
            res = MIMO_CLIENT.chat.completions.create(
                model=Config.MIMO_MODEL,
                messages=clean_messages,
                temperature=0.0,
                extra_body={
                    "reasoning_effort": "high"
                }
            )

            msg = res.choices[0].message
            content = msg.content or ""
            thought = getattr(msg, "reasoning_content", "") or ""

            return {
                "role": "assistant",
                "content": content,
                "thought": thought
            }

        except Exception as e:
            last_err = e
            logger.warning("call_mimo failed (attempt %s/%s): %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                _sleep_backoff(attempt)

    logger.error("call_mimo failed: %s", last_err)
    return {
        "role": "assistant",
        "content": "```json\n{\"action\":\"error\",\"kwargs\":{}}\n```",
        "thought": ""
    }