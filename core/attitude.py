"""Attitude error and reaction-wheel speed. Rates are inputs, not estimated."""

from __future__ import annotations


def drift_step(err_deg: float, rate_deg_s: float, dt_s: float) -> float:
    if dt_s < 0:
        raise ValueError("dt_s must be non-negative")
    return max(0.0, err_deg + rate_deg_s * dt_s)


def wheel_rpm(err_deg: float, base_rpm: float, gain_rpm_per_deg: float = 900.0) -> float:
    """Wheel speed grows as the bus stores the momentum the drift represents."""
    return max(0.0, base_rpm + gain_rpm_per_deg * max(0.0, err_deg))


def settle_rate_deg_s(kind: str, variant: str | None) -> float:
    """How fast a chosen recovery drives the error down, in deg/s. Negative."""
    if kind == "magnetorquer":
        return -0.004
    if kind == "rcs":
        return -0.02 if variant == "fuel-saving" else -0.08
    if kind == "safe_mode":
        return 0.0
    raise ValueError(f"unknown recovery kind {kind}")
