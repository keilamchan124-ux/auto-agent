# -*- coding: utf-8 -*-
from __future__ import annotations
import time
import logging
from typing import List, Dict, Any

from openai import OpenAI
from google import genai
import requests
from core.config import Config

logger = logging.getLogger("LLM")
LAST_RESCUE_EVENTS: list[dict] = []


def _classify_error_code(text: str) -> str:
    t = (text or "").lower()
    if "401" in t or "403" in t or "auth" in t:
        return "auth_error"
    if "404" in t or "not found" in t:
        return "not_found"
    if "429" in t or "rate limit" in t or "resource_exhausted" in t:
        return "rate_limited"
    if "http" in t:
        return "http_error"
    return "backend_unavailable"

GEMINI_CLIENT = genai.Client(api_key=Config.GEMINI_API_KEY) if Config.GEMINI_API_KEY else None

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


def call_gemini_rescue(history: list, stuck_reason: str | None = None, retries: int = 2) -> str:
    """Rescue supervisor with fallback order: GLM-4.7 > Gemini 3.1 flash lite > Gemma 4."""
    rescue_prompt = "You are a rescue controller for an execution agent.\n"

    if stuck_reason:
        rescue_prompt += f"The agent is currently stuck because: {stuck_reason}\n"

        if "FORMAT" in stuck_reason or "JSON" in stuck_reason:
            rescue_prompt += (
                "\nCRITICAL INSTRUCTION: You MUST return exactly one fenced JSON block containing `action` and `kwargs`.\n"
                "Do NOT include any markdown, thoughts, or text outside the ```json ... ``` block.\n"
            )
        elif "TOOL PARAMETER" in stuck_reason:
            rescue_prompt += (
                "\nCRITICAL INSTRUCTION: The agent provided invalid parameters for the tool.\n"
                "If using the 'plan' tool, use EXACTLY:\n"
                '{"action":"plan","kwargs":{"steps":"your plan here"}}\n'
                "Do NOT use task, goal, plan, subtasks, or input as keys.\n"
                "If using other tools, provide only the required parameters.\n"
            )
        else:
            rescue_prompt += (
                "\nCRITICAL INSTRUCTION: Analyze the runtime or execution error.\n"
                "Choose a different strategy, try installing missing dependencies, or write a different command.\n"
            )

    rescue_prompt += (
        "\nReturn ONLY one fenced JSON block.\n"
        "No explanation. No markdown outside the JSON block. No thoughts.\n"
        "Choose the single best next action to debug errors or recover from loop/format failure.\n"
        "Available actions: web_search, download_file, run_cmd, write_file, read_file, run_python_script, get_skill, plan, mark_done.\n"
        "Note: Use run_cmd with 'pip install <pkg>' if you need third-party packages.\n\n"
        "Use this exact format:\n"
        "```json\n"
        "{\"action\":\"run_python_script\",\"kwargs\":{\"code\":\"print('Debugging...')\"}}\n"
        "```"
    )

    contents = []
    for m in _clean_history(history):
        role = "user" if m["role"] in ("user", "system") else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    contents.append({"role": "user", "parts": [{"text": rescue_prompt}]})

    # Priority chain: GLM-4.7 (NVIDIA NIM) > Gemini > Gemma 4 (MIMO/OpenAI-compatible)
    LAST_RESCUE_EVENTS.clear()
    nim_err = None
    try:
        t0 = time.time()
        out = _call_nim_rescue(contents, retries=retries)
        LAST_RESCUE_EVENTS.append({
            "backend": "nim_glm",
            "status": "success",
            "error_code": "none",
            "attempt": retries + 1,
            "latency_ms": int((time.time() - t0) * 1000),
            "detail": "success",
        })
        return out
    except Exception as e:
        nim_err = e
        LAST_RESCUE_EVENTS.append({
            "backend": "nim_glm",
            "status": "failed",
            "error_code": _classify_error_code(str(e)),
            "attempt": retries + 1,
            "latency_ms": 0,
            "detail": str(e),
        })
        logger.warning("GLM rescue unavailable, fallback to Gemini: %s", e)

    try:
        t0 = time.time()
        out = _call_gemini_rescue(contents, retries=retries)
        LAST_RESCUE_EVENTS.append({
            "backend": "gemini",
            "status": "success",
            "error_code": "none",
            "attempt": retries + 1,
            "latency_ms": int((time.time() - t0) * 1000),
            "detail": "success",
        })
        return out
    except Exception as e:
        LAST_RESCUE_EVENTS.append({
            "backend": "gemini",
            "status": "failed",
            "error_code": _classify_error_code(str(e)),
            "attempt": retries + 1,
            "latency_ms": 0,
            "detail": str(e),
        })
        logger.warning("Gemini rescue unavailable, fallback to Gemma 4: %s", e)
        if nim_err:
            logger.debug("Earlier GLM/NIM error: %s", nim_err)

    t0 = time.time()
    out = _call_mimo_rescue(contents, retries=retries)
    LAST_RESCUE_EVENTS.append({
        "backend": "mimo_gemma",
        "status": "fallback_used",
        "error_code": "none",
        "attempt": retries + 1,
        "latency_ms": int((time.time() - t0) * 1000),
        "detail": "fallback_used",
    })
    return out


def get_last_rescue_events() -> list[dict]:
    return list(LAST_RESCUE_EVENTS)


def _call_nim_rescue(contents: list, retries: int = 2) -> str:
    if not Config.NIM_API_KEY:
        raise RuntimeError("NIM rescue is not configured. Set NIM_API_KEY.")

    nim_messages = []
    for c in contents:
        role = "assistant" if c.get("role") == "model" else "user"
        text = ""
        parts = c.get("parts") or []
        if parts and isinstance(parts[0], dict):
            text = _normalize_text(parts[0].get("text", ""))
        nim_messages.append({"role": role, "content": text})

    payload = {
        "model": getattr(Config, "NIM_RESCUE_MODEL", "z-ai/glm4.7"),
        "messages": nim_messages,
        "temperature": 0.0,
        "top_p": 1,
        "max_tokens": 16384,
        "stream": False,
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {Config.NIM_API_KEY}",
    }

    url = f"{Config.NIM_BASE_URL}/chat/completions"
    last_err = None
    last_status = None
    for attempt in range(retries + 1):
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=120)
            last_status = res.status_code
            if res.status_code >= 400:
                detail = ""
                try:
                    detail = res.text[:500]
                except Exception:
                    detail = ""
                if res.status_code in (401, 403):
                    raise RuntimeError(f"NIM auth error ({res.status_code}): check NIM_API_KEY/permissions. {detail}")
                if res.status_code == 404:
                    raise RuntimeError(f"NIM endpoint/model not found (404): check NIM_BASE_URL/NIM_RESCUE_MODEL. {detail}")
                if res.status_code == 429:
                    raise RuntimeError(f"NIM rate limited (429): quota/concurrency exceeded. {detail}")
                raise RuntimeError(f"NIM HTTP error ({res.status_code}). {detail}")
            data = res.json()
            return _normalize_text(data["choices"][0]["message"]["content"]).strip()
        except Exception as e:
            last_err = e
            logger.warning("GLM rescue failed (attempt %s/%s): %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                _sleep_backoff(attempt)

    if last_status is not None:
        raise RuntimeError(f"GLM rescue failed after retries (status={last_status}): {last_err}")
    raise RuntimeError(f"GLM rescue failed after retries: {last_err}")

def _call_gemini_rescue(contents: list, retries: int = 2) -> str:
    if GEMINI_CLIENT is None:
        raise RuntimeError("GEMINI_API_KEY is not set for gemini rescue backend.")
    last_err = None
    for attempt in range(retries + 1):
        try:
            response = GEMINI_CLIENT.models.generate_content(
                model=getattr(Config, "GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
                contents=contents
            )
            return getattr(response, "text", "") or ""
        except Exception as e:
            last_err = e
            logger.warning("Gemini rescue failed (attempt %s/%s): %s", attempt + 1, retries + 1, e)
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                raise e
            if attempt < retries:
                _sleep_backoff(attempt)
    logger.error("call_gemini_rescue failed: %s", last_err)
    return "```json\n{\"action\":\"error\",\"kwargs\":{}}\n```"


def _call_mimo_rescue(contents: list, retries: int = 2) -> str:
    last_err = None
    rescue_messages = []
    for c in contents:
        role = "assistant" if c.get("role") == "model" else "user"
        text = ""
        parts = c.get("parts") or []
        if parts and isinstance(parts[0], dict):
            text = _normalize_text(parts[0].get("text", ""))
        rescue_messages.append({"role": role, "content": text})

    for attempt in range(retries + 1):
        try:
            res = MIMO_CLIENT.chat.completions.create(
                model=(getattr(Config, "RESCUE_MODEL", "") or getattr(Config, "MIMO_MODEL", "mimo-v2.5-pro")),
                messages=rescue_messages,
                temperature=0.0,
            )
            return (res.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            logger.warning("MIMO rescue failed (attempt %s/%s): %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                _sleep_backoff(attempt)
    logger.error("call_mimo_rescue failed: %s", last_err)
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
