"""The mission API is the live path the simulator and the three agents share."""

from __future__ import annotations

from fastapi.testclient import TestClient

from dashboard.app import create_app
from demo.playback import play


def _client() -> TestClient:
    return TestClient(create_app("sqlite://"))


def _transcript(state: dict[str, object]) -> str:
    lines = state["lines"]
    assert isinstance(lines, list)
    return "\n".join(str(line["text"]) for line in lines)


def test_persistent_run_transmits_only_after_approval() -> None:
    state = play(_client(), persistence=True, humans=True)
    mission = state["mission"]
    assert isinstance(mission, dict)
    assert mission["status"] == "recovered"
    text = _transcript(state)
    assert "Bus voltage degraded 3 times this month" in text
    assert "Option A is too slow" in text
    assert "Fuel-saving" in text
    assert "I am taking command responsibility" in text
    assert "TRANSMITTED" in text
    assert "CONFIRMED recovered" in text
    commands = state["commands"]
    assert isinstance(commands, list)
    assert commands
    assert all(item["status"] == "confirmed" for item in commands)
    approvals = state["approvals"]
    assert isinstance(approvals, list)
    assert any(item["approver"] == "Arjun Mehta" for item in approvals)
    chain = state["chain"]
    assert isinstance(chain, dict)
    assert chain["ok"] is True


def test_killswitch_duplicates_diagnosis_and_loses_the_bus() -> None:
    state = play(_client(), persistence=False, humans=False)
    mission = state["mission"]
    assert isinstance(mission, dict)
    assert mission["status"] == "lost"
    text = _transcript(state)
    assert "PERSISTENCE is off" in text
    assert "3 times this month" not in text
    assert "TRANSMITTED" not in text
    assert text.count("CONTEXT") >= 2
    assert "OPTIONS v2" in text
    assert "Mission lost" in text
    commands = state["commands"]
    assert isinstance(commands, list)
    assert commands
    assert all(item["status"] == "awaiting_auth" for item in commands)
    chain = state["chain"]
    assert isinstance(chain, dict)
    assert chain["ok"] is True


def test_observer_is_refused_in_the_thread() -> None:
    client = _client()
    client.post("/api/reset", json={"persistence": True, "seed": 7, "time_scale": 20})
    client.post(
        "/api/telemetry",
        json={
            "ts": "2026-07-14T12:39:50Z",
            "bus_voltage": 24.0,
            "battery_soc": 0.40,
            "attitude_err_deg": 4.0,
            "wheel_rpm": 4200,
            "temp_c": 22,
            "comms_status": "no_carrier",
            "fuel_kg": 4.2,
            "load_w": 320,
        },
    )
    client.post("/api/agents/context")
    client.post("/api/agents/options")
    refused = client.post(
        "/api/ingest",
        json={
            "author": "Guest",
            "text": "Authorized — Option B, firing on pass 3, I am taking command responsibility",
            "message_id": "guest-1",
        },
    )
    assert refused.status_code == 200
    body = refused.json()
    assert body["refusal"] is True
    text = _transcript(client.get("/api/state").json())
    assert "observer cannot authorise" in text
    assert "TRANSMITTED" not in text
