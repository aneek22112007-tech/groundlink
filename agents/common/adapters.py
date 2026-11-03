"""Optional Discord and Telegram fan-out. Off unless the env flag and a token are set."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Delivery:
    channel: str
    ok: bool
    detail: str


def discord_enabled() -> bool:
    return os.environ.get("DISCORD_ENABLED", "false").lower() in {"1", "true", "yes"}


def telegram_enabled() -> bool:
    return os.environ.get("TELEGRAM_ENABLED", "false").lower() in {"1", "true", "yes"}


def format_outbound(agent: str, text: str) -> str:
    return f"[{agent}] {text}"


def fanout(agent: str, text: str, client: httpx.Client | None = None) -> list[Delivery]:
    """Post the same wording to side channels. Missing tokens are reported, not raised."""
    own = client or httpx.Client(timeout=10.0)
    close = client is None
    results: list[Delivery] = []
    body = format_outbound(agent, text)
    try:
        if discord_enabled():
            results.append(_discord(own, body))
        if telegram_enabled():
            results.append(_telegram(own, body))
    finally:
        if close:
            own.close()
    return results


def _discord(client: httpx.Client, body: str) -> Delivery:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return Delivery("discord", False, "DISCORD_ENABLED is set and DISCORD_WEBHOOK_URL is empty")
    response = client.post(url, json={"content": body[:1900]})
    return Delivery("discord", response.status_code < 300, f"http {response.status_code}")


def _telegram(client: httpx.Client, body: str) -> Delivery:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return Delivery("telegram", False, "telegram flag set without token or chat id")
    response = client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": body[:4000]},
    )
    return Delivery("telegram", response.status_code < 300, f"http {response.status_code}")
