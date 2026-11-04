"""Fast Kestrel-7 playback against the mission API. The live simulator uses the same phases."""

from __future__ import annotations

import json
import random
from typing import Any

from agents.common.irreversibility import command_statement
from agents.common.timeutil import iso
from core.types import Sample
from telemetry.plant import apply_recovery, spend_fuel, step
from telemetry.scenario import apply_phase, fresh_plant, load_scenario

PRIYA_REJECT = "Option A is too slow. We cannot wait out a magnetorquer desat."
PRIYA_FUEL = "Request a fuel-saving variant of Option B."
PRIYA_CONFIRM = "Confirmed — Option B. Second operator confirmation."


def sample_payload(sample: Sample) -> dict[str, object]:
    return {
        "ts": iso(sample.ts),
        "bus_voltage": sample.bus_voltage,
        "battery_soc": sample.battery_soc,
        "attitude_err_deg": sample.attitude_err_deg,
        "wheel_rpm": sample.wheel_rpm,
        "temp_c": sample.temp_c,
        "comms_status": sample.comms_status,
        "fuel_kg": sample.fuel_kg,
        "in_eclipse": sample.in_eclipse,
        "load_w": sample.load_w,
    }


def _state(client: Any) -> dict[str, Any]:
    payload = client.get("/api/state").json()
    if not isinstance(payload, dict):
        raise RuntimeError("mission API returned a non-object state")
    return payload


def play(
    client: Any,
    *,
    persistence: bool,
    humans: bool,
    seed: int = 7,
    steps: int = 150,
) -> dict[str, Any]:
    scenario = load_scenario()
    created = client.post(
        "/api/reset",
        json={"persistence": persistence, "seed": seed, "time_scale": scenario.time_scale},
    )
    if created.status_code >= 300:
        raise RuntimeError(created.text)
    plant = fresh_plant(scenario)
    rng = random.Random(seed)
    applied: set[str] = set()
    asked = False
    authed = False
    client.post("/api/telemetry", json=sample_payload(plant.sample))
    last: dict[str, Any] = {}
    for _ in range(steps):
        client.post("/api/agents/context")
        client.post("/api/agents/options")
        state = _state(client)
        elapsed = _elapsed(state)
        transcript = _transcript(state)
        if humans and persistence and not asked and "OPTIONS v" in transcript and elapsed > 900:
            _ingest(client, "Priya Raman", PRIYA_REJECT, "priya-reject")
            _ingest(client, "Priya Raman", PRIYA_FUEL, "priya-fuel")
            asked = True
            client.post("/api/agents/options")
            state = _state(client)
            transcript = _transcript(state)
        if (
            humans
            and persistence
            and not authed
            and state.get("pass", {}).get("open")
            and "Fuel-saving" in transcript
        ):
            _ingest(client, "Arjun Mehta", command_statement("B", 3), "arjun-auth")
            _ingest(client, "Priya Raman", PRIYA_CONFIRM, "priya-confirm")
            authed = True
        client.post("/api/agents/action")
        state = _state(client)
        _absorb(plant, state, applied)
        status = (state.get("mission") or {}).get("status")
        if status in {"recovered", "lost"}:
            client.post("/api/agents/action")
            last = _state(client)
            return last
        apply_phase(plant, scenario, plant.sample.ts)
        step(plant, 30.0, rng, scenario.dropout_p)
        client.post("/api/telemetry", json=sample_payload(plant.sample))
        state = _state(client)
        status = (state.get("mission") or {}).get("status")
        if status in {"recovered", "lost"}:
            client.post("/api/agents/action")
            return _state(client)
        last = state
    client.post("/api/agents/action")
    return _state(client) or last


def _elapsed(state: dict[str, Any]) -> float:
    sample = state.get("sample") or {}
    ts = str(sample.get("ts", ""))
    if not ts:
        return 0.0
    from datetime import datetime

    moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    start = datetime.fromisoformat("2026-07-14T12:00:00+00:00")
    return (moment - start).total_seconds()


def _transcript(state: dict[str, Any]) -> str:
    return "\n".join(str(line.get("text", "")) for line in state.get("lines", []))


def _ingest(client: Any, author: str, text: str, message_id: str) -> None:
    response = client.post(
        "/api/ingest",
        json={"author": author, "text": text, "message_id": message_id},
    )
    if response.status_code >= 300:
        raise RuntimeError(response.text)


def _absorb(plant: Any, state: dict[str, Any], applied: set[str]) -> None:
    """Feed newly transmitted commands back into the plant.

    The recovery mode starts on the first transmitted step of an option. Propellant
    is spent once per transmitted step that carries a fuel cost, so a sequence sent
    one step per tick still burns exactly once.
    """
    for command in state.get("commands", []):
        if command.get("status") not in {"transmitted", "confirmed"}:
            continue
        option_id = str(command.get("option_id", ""))
        step_key = f"{option_id}#{command.get('seq')}"
        if step_key in applied:
            continue
        payload = json.loads(str(command.get("payload") or "{}"))
        kind = str(payload.get("kind", ""))
        if not kind:
            continue
        fuel = float(payload.get("fuel_cost_kg") or 0)
        variant = payload.get("variant") or None
        if option_id not in applied:
            apply_recovery(plant, kind, fuel, variant if isinstance(variant, str) else None)
            applied.add(option_id)
        elif fuel > 0:
            spend_fuel(plant, fuel)
        applied.add(step_key)
