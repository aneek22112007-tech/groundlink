"""Heartbeat. Every wall tick posts one sample and follows a transmitted option."""

from __future__ import annotations

import os
import random
import time
from typing import Any

import httpx

from agents.common.timeutil import iso
from demo.playback import _absorb, sample_payload
from telemetry.plant import step
from telemetry.scenario import apply_phase, fresh_plant, load_scenario


def main() -> None:
    base = os.environ.get("MISSION_API_URL", "http://127.0.0.1:8090").rstrip("/")
    scenario = load_scenario()
    seed = int(os.environ.get("SEED", str(scenario.seed)))
    heartbeat = float(os.environ.get("HEARTBEAT_S", str(scenario.heartbeat_s)))
    scale = float(os.environ.get("TIME_SCALE", str(scenario.time_scale)))
    client = httpx.Client(timeout=30.0)
    plant = fresh_plant(scenario)
    rng = random.Random(seed)
    applied: set[str] = set()
    mission_id = ""
    posted_initial = False
    while True:
        try:
            state = client.get(f"{base}/api/state").json()
        except httpx.HTTPError:
            time.sleep(heartbeat)
            continue
        current = (state.get("mission") or {}).get("id") or ""
        if current and current != mission_id:
            mission_id = str(current)
            plant = fresh_plant(scenario)
            clock = state.get("clock") or {}
            rng = random.Random(int(clock.get("seed", seed)))
            applied = set()
            posted_initial = False
            scale = float(clock.get("time_scale", scale))
        if not current:
            time.sleep(heartbeat)
            continue
        if not posted_initial:
            client.post(f"{base}/api/telemetry", json=sample_payload(plant.sample))
            posted_initial = True
            time.sleep(heartbeat)
            continue
        _absorb(plant, state, applied)
        apply_phase(plant, scenario, plant.sample.ts)
        step(plant, heartbeat * scale, rng, scenario.dropout_p)
        client.post(f"{base}/api/telemetry", json=sample_payload(plant.sample))
        time.sleep(heartbeat)


def describe() -> dict[str, Any]:
    scenario = load_scenario()
    return {
        "seed": scenario.seed,
        "heartbeat_s": scenario.heartbeat_s,
        "epoch": iso(scenario.initial.ts),
        "phases": [phase.name for phase in scenario.phases],
    }


if __name__ == "__main__":
    main()
