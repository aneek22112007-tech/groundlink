"""OpenAI-compatible wording. With no key, the deterministic text is used unchanged."""

from __future__ import annotations

import os
from typing import Any

import httpx


def llm_enabled() -> bool:
    return bool(os.environ.get("LLM_API_KEY", "").strip())


def narrate(deterministic: str, *, purpose: str) -> str:
    """Return wording for the room. Numbers inside `deterministic` are authoritative."""
    if not llm_enabled():
        return deterministic
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write for a satellite mission room. Rephrase the operator text "
                    "so a flight controller can read it aloud. Do not add, drop, or change "
                    "any number, proper name, option letter, REVERSIBLE/IRREVERSIBLE tag, "
                    "or timestamp. If you cannot, return the text unchanged."
                ),
            },
            {"role": "user", "content": f"Purpose: {purpose}\n\n{deterministic}"},
        ],
    }
    try:
        response = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return deterministic
    if not isinstance(content, str) or not content.strip():
        return deterministic
    return content.strip()
