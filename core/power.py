"""Bus power. Open-circuit voltage is affine in state of charge; load sags it."""

from __future__ import annotations

from core.constants import BUS_CAPACITY_WH


def open_circuit_voltage(soc: float) -> float:
    clamped = min(1.0, max(0.0, soc))
    return 22.0 + 8.5 * clamped


def bus_voltage(soc: float, load_w: float) -> float:
    sag = max(0.0, load_w) * 0.008
    return open_circuit_voltage(soc) - sag


def soc_step(
    soc: float, load_w: float, eclipse: bool, dt_s: float, solar_w: float = 190.0
) -> float:
    if dt_s < 0:
        raise ValueError("dt_s must be non-negative")
    generated = 0.0 if eclipse else solar_w
    net_w = load_w - generated
    delta = -(net_w * dt_s / 3600.0) / BUS_CAPACITY_WH
    return min(1.0, max(0.0, soc + delta))


def energy_wh(load_w: float, dt_s: float) -> float:
    return max(0.0, load_w) * dt_s / 3600.0
