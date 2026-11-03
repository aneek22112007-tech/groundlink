from __future__ import annotations

import pytest

from core.attitude import drift_step, settle_rate_deg_s, wheel_rpm
from core.fuel import delta_v_for_recovery, fuel_for_delta_v, reserve_pct
from core.reversibility import classify
from core.thermal import temp_step


def test_negative_steps_are_rejected() -> None:
    with pytest.raises(ValueError):
        drift_step(1, 0, -1)
    with pytest.raises(ValueError):
        temp_step(10, False, 0, -1)
    with pytest.raises(ValueError):
        temp_step(10, False, 0, 1, tau_s=0)
    with pytest.raises(ValueError):
        fuel_for_delta_v(-1, 10)
    with pytest.raises(ValueError):
        fuel_for_delta_v(1, 0)
    with pytest.raises(ValueError):
        reserve_pct(1, 0)
    with pytest.raises(ValueError):
        classify("laser")
    with pytest.raises(ValueError):
        settle_rate_deg_s("laser", None)


def test_boundary_physics() -> None:
    assert drift_step(0.1, -1, 1) == 0.0
    assert wheel_rpm(1, -10000) == 0.0
    assert settle_rate_deg_s("safe_mode", None) == 0.0
    assert fuel_for_delta_v(0, 10) == 0.0
    assert reserve_pct(-1, 10) == 0.0
    assert delta_v_for_recovery(-3, None) == 2.4
    assert temp_step(10, True, -5, 10) < 10
