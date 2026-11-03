"""One integration step of the bus. Noise is the only randomness, and it is seeded."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta

from core.attitude import drift_step, wheel_rpm
from core.constants import SURVIVAL_SOC, SURVIVAL_VOLTAGE
from core.power import bus_voltage, soc_step
from core.thermal import temp_step
from core.types import Sample


@dataclass
class Plant:
    sample: Sample
    drift_rate_deg_s: float = 0.0
    load_w: float = 80.0
    comms_status: str = "nominal"
    eclipse: bool = False
    base_wheel_rpm: float = 900.0
    recovering: str | None = None
    burned: bool = False
    lost: bool = False

    def snapshot(self) -> Sample:
        return self.sample


def step(plant: Plant, dt_s: float, rng: random.Random, dropout_p: float = 0.02) -> Sample:
    previous = plant.sample
    if plant.lost:
        plant.sample = Sample(
            ts=previous.ts,
            bus_voltage=min(previous.bus_voltage, SURVIVAL_VOLTAGE - 0.4),
            battery_soc=min(previous.battery_soc, SURVIVAL_SOC - 0.02),
            attitude_err_deg=previous.attitude_err_deg + 0.05 * dt_s,
            wheel_rpm=previous.wheel_rpm,
            temp_c=previous.temp_c,
            comms_status="no_carrier",
            fuel_kg=previous.fuel_kg,
            in_eclipse=plant.eclipse,
            load_w=plant.load_w,
        )
        return plant.sample

    rate = plant.drift_rate_deg_s
    if plant.recovering == "rcs":
        rate = -0.08 if plant.burned else plant.drift_rate_deg_s
    elif plant.recovering == "rcs-save":
        rate = -0.02
    elif plant.recovering == "magnetorquer":
        rate = -0.004
    elif plant.recovering == "safe_mode":
        rate = 0.0

    soc = soc_step(previous.battery_soc, plant.load_w, plant.eclipse, dt_s)
    err = (
        previous.attitude_err_deg
        if plant.recovering == "safe_mode"
        else drift_step(previous.attitude_err_deg, rate, dt_s)
    )
    if plant.recovering == "safe_mode":
        err = max(err, 6.0)
    temp = temp_step(previous.temp_c, plant.eclipse, plant.load_w, dt_s)
    volts = bus_voltage(soc, plant.load_w)
    volts += rng.uniform(-0.04, 0.04)
    err = max(0.0, err + rng.uniform(-0.01, 0.01))
    temp += rng.uniform(-0.05, 0.05)
    comms = plant.comms_status
    if plant.recovering in {"rcs", "rcs-save", "magnetorquer"} and err < 0.8:
        comms = "nominal"
    if comms == "nominal" and rng.random() < dropout_p:
        comms = "degraded"
    wheels = wheel_rpm(err, plant.base_wheel_rpm)
    if volts < SURVIVAL_VOLTAGE or soc < SURVIVAL_SOC:
        plant.lost = True
        comms = "no_carrier"

    plant.sample = Sample(
        ts=previous.ts + timedelta(seconds=dt_s),
        bus_voltage=round(volts, 3),
        battery_soc=round(soc, 4),
        attitude_err_deg=round(err, 3),
        wheel_rpm=round(wheels, 1),
        temp_c=round(temp, 2),
        comms_status=comms,
        fuel_kg=round(previous.fuel_kg, 4),
        in_eclipse=plant.eclipse,
        load_w=plant.load_w,
    )
    return plant.sample


def apply_recovery(plant: Plant, kind: str, fuel_cost_kg: float, variant: str | None) -> None:
    if kind == "rcs":
        plant.recovering = "rcs-save" if variant == "fuel-saving" else "rcs"
        plant.burned = True
        plant.load_w = 100.0
        plant.comms_status = "degraded"
    elif kind == "magnetorquer":
        plant.recovering = "magnetorquer"
        plant.load_w = 150.0
    elif kind == "safe_mode":
        plant.recovering = "safe_mode"
        plant.load_w = 42.0
        plant.comms_status = "degraded"
    else:
        raise ValueError(kind)
    previous = plant.sample
    plant.sample = Sample(
        ts=previous.ts,
        bus_voltage=previous.bus_voltage,
        battery_soc=previous.battery_soc,
        attitude_err_deg=previous.attitude_err_deg,
        wheel_rpm=previous.wheel_rpm,
        temp_c=previous.temp_c,
        comms_status=plant.comms_status,
        fuel_kg=round(max(0.0, previous.fuel_kg - fuel_cost_kg), 4),
        in_eclipse=previous.in_eclipse,
        load_w=plant.load_w,
    )
