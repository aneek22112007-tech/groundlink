"""Load the Kestrel-7 phase table. The simulator and the fast playback share it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from core.types import Sample
from demo.elements import epoch
from telemetry.plant import Plant


@dataclass(frozen=True)
class Phase:
    until_s: float
    name: str
    load_w: float
    drift_rate_deg_s: float
    comms_status: str


@dataclass(frozen=True)
class Scenario:
    seed: int
    heartbeat_s: float
    time_scale: float
    dropout_p: float
    initial: Sample
    phases: tuple[Phase, ...]


def scenario_path() -> Path:
    return Path(__file__).resolve().parent / "scenarios" / "kestrel7.yaml"


def load_scenario(path: Path | None = None) -> Scenario:
    raw = yaml.safe_load((path or scenario_path()).read_text(encoding="utf-8"))
    start = epoch()
    initial_raw = raw["initial"]
    initial = Sample(
        ts=start,
        bus_voltage=float(initial_raw["bus_voltage"]),
        battery_soc=float(initial_raw["battery_soc"]),
        attitude_err_deg=float(initial_raw["attitude_err_deg"]),
        wheel_rpm=float(initial_raw["wheel_rpm"]),
        temp_c=float(initial_raw["temp_c"]),
        comms_status=str(initial_raw["comms_status"]),
        fuel_kg=float(initial_raw["fuel_kg"]),
        in_eclipse=False,
        load_w=float(initial_raw["load_w"]),
    )
    phases = tuple(
        Phase(
            until_s=float(item["until_s"]),
            name=str(item["name"]),
            load_w=float(item["load_w"]),
            drift_rate_deg_s=float(item["drift_rate_deg_s"]),
            comms_status=str(item["comms_status"]),
        )
        for item in raw["phases"]
    )
    return Scenario(
        seed=int(raw["seed"]),
        heartbeat_s=float(raw["heartbeat_s"]),
        time_scale=float(raw["time_scale"]),
        dropout_p=float(raw["dropout_p"]),
        initial=initial,
        phases=phases,
    )


def phase_at(scenario: Scenario, elapsed_s: float) -> Phase:
    for phase in scenario.phases:
        if elapsed_s < phase.until_s:
            return phase
    return scenario.phases[-1]


def apply_phase(plant: Plant, scenario: Scenario, moment: datetime) -> None:
    if plant.lost or plant.recovering is not None:
        return
    elapsed = (moment - scenario.initial.ts).total_seconds()
    phase = phase_at(scenario, elapsed)
    plant.load_w = phase.load_w
    plant.drift_rate_deg_s = phase.drift_rate_deg_s
    plant.comms_status = phase.comms_status


def fresh_plant(scenario: Scenario) -> Plant:
    return Plant(
        sample=scenario.initial,
        drift_rate_deg_s=0.0,
        load_w=scenario.initial.load_w,
        comms_status=scenario.initial.comms_status,
    )
