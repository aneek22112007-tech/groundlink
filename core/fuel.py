"""Propellant from the rocket equation. Mass is the wet mass at the burn."""

from __future__ import annotations

import math

from core.constants import G0_M_S2, RCS_ISP_S


def exhaust_velocity_m_s(isp_s: float = RCS_ISP_S) -> float:
    return isp_s * G0_M_S2


def fuel_for_delta_v(delta_v_m_s: float, wet_mass_kg: float, isp_s: float = RCS_ISP_S) -> float:
    if delta_v_m_s < 0:
        raise ValueError("delta_v_m_s must be non-negative")
    if wet_mass_kg <= 0:
        raise ValueError("wet_mass_kg must be positive")
    if delta_v_m_s == 0:
        return 0.0
    ve = exhaust_velocity_m_s(isp_s)
    spent = wet_mass_kg * (1.0 - math.exp(-delta_v_m_s / ve))
    return min(wet_mass_kg, spent)


def reserve_pct(remaining_kg: float, capacity_kg: float) -> float:
    if capacity_kg <= 0:
        raise ValueError("capacity_kg must be positive")
    return 100.0 * max(0.0, remaining_kg) / capacity_kg


def delta_v_for_recovery(err_deg: float, variant: str | None) -> float:
    """Metres per second to null the rate implied by the current error.

    The mapping is linear and documented so a reviewer can recompute it.
    A fuel-saving variant commands half the delta-v and accepts a longer settle.
    """
    full = 2.4 + 0.45 * max(0.0, err_deg)
    if variant == "fuel-saving":
        return full * 0.45
    return full
