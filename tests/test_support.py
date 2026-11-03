from __future__ import annotations

import httpx

from agents.common.adapters import fanout
from agents.common.llm import narrate
from agents.common.operators import resolve_operator
from agents.common.roles import Role
from agents.common.switch_client import message_from_event, parse_sse


def test_parse_sse_splits_events() -> None:
    events, rest = parse_sse('event: message\ndata: {"a": 1}\n\n: keep\ndata: partial')
    assert rest == ": keep\ndata: partial"
    assert events[0]["event"] == "message"
    assert events[0]["data"] == '{"a": 1}'


def test_message_from_event_reads_body() -> None:
    message = message_from_event(
        {
            "data": '{"event":"message","data":{"room_id":"r","payload":{"body":"hello","sender_name":"Priya"}}}'
        }
    )
    assert message is not None
    assert message.body == "hello"
    assert message.sender_name == "Priya"
    assert message_from_event({"data": "not-json"}) is None


def test_narrate_without_a_key_returns_the_deterministic_text(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert narrate("BUS 24.20 V", purpose="context") == "BUS 24.20 V"


def test_narrate_falls_back_when_the_provider_errors(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9")
    assert narrate("BUS 24.20 V", purpose="context") == "BUS 24.20 V"


def test_resolve_operator_strips_a_mention() -> None:
    assert resolve_operator("@Priya Raman") == ("Priya Raman", Role.FLIGHT_OPS_ENGINEER)
    assert resolve_operator("nobody") is None


def test_fanout_reports_a_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_ENABLED", "true")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    deliveries = fanout("context", "hello", httpx.Client())
    assert deliveries[0].ok is False
