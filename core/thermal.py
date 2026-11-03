"""First-order thermal lag toward a load- and eclipse-dependent target."""

from __future__ import annotations

import math


def target_c(eclipse: bool, load_w: float) -> float:
    base = -8.0 if eclipse else 16.0
    return base + max(0.0, load_w) * 0.03


def temp_step(
    temp_c: float, eclipse: bool, load_w: float, dt_s: float, tau_s: float = 1800.0
) -> float:
    if dt_s < 0:
        raise ValueError("dt_s must be non-negative")
    if tau_s <= 0:
        raise ValueError("tau_s must be positive")
    aim = target_c(eclipse, load_w)
    return temp_c + (aim - temp_c) * (1.0 - math.exp(-dt_s / tau_s))
