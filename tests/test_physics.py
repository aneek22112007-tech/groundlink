from __future__ import annotations

import math
from datetime import UTC, timedelta

from core.attitude import drift_step, settle_rate_deg_s, wheel_rpm
from core.constants import EARTH_RADIUS_KM, G0_M_S2, RCS_ISP_S
from core.diagnosis import diagnose
from core.fuel import delta_v_for_recovery, fuel_for_delta_v, reserve_pct
from core.orbit import elevation_deg, geodetic_to_ecef, orbital_period_s
from core.power import bus_voltage, energy_wh, soc_step
from core.reversibility import classify
from core.thermal import temp_step
from core.types import Sample
from tests.conftest import T0


def test_period_matches_two_body() -> None:
    altitude = 550.0
    radius = EARTH_RADIUS_KM + altitude
    mu = 398600.4418
    expected = 2.0 * math.pi * math.sqrt(radius**3 / mu)
    assert orbital_period_s(altitude) == pytest_approx(expected)


def pytest_approx(value: float) -> float:
    return value


def test_period_is_about_95_minutes() -> None:
    assert 90 * 60 < orbital_period_s(550.0) < 100 * 60


def test_overhead_elevation_is_high() -> None:
    station = geodetic_to_ecef(13.0, 77.5, 0.001)
    # A point further along the same ray is overhead.
    sat = tuple(component * (EARTH_RADIUS_KM + 550.0) / EARTH_RADIUS_KM for component in station)
    assert elevation_deg(sat, station) > 89.0


def test_soc_and_voltage_move_with_load() -> None:
    charged = soc_step(0.8, 40.0, eclipse=False, dt_s=60.0)
    drained = soc_step(0.8, 200.0, eclipse=True, dt_s=3600.0)
    assert charged > 0.8
    assert drained < 0.8
    assert bus_voltage(0.8, 40.0) > bus_voltage(0.3, 180.0)
    assert energy_wh(100.0, 3600.0) == 100.0


def test_attitude_and_wheels() -> None:
    assert drift_step(1.0, 0.1, 10.0) == pytest_approx(2.0)
    assert drift_step(0.2, -1.0, 10.0) == 0.0
    assert wheel_rpm(2.0, 1000.0) > wheel_rpm(0.2, 1000.0)
    assert settle_rate_deg_s("rcs", None) < settle_rate_deg_s("rcs", "fuel-saving") < 0
    assert settle_rate_deg_s("magnetorquer", None) < 0


def test_rocket_equation_known_point() -> None:
    isp = 300.0
    mass = 1000.0
    dv = 100.0
    ve = isp * G0_M_S2
    expected = mass * (1.0 - math.exp(-dv / ve))
    assert fuel_for_delta_v(dv, mass, isp) == pytest_approx(expected)
    assert fuel_for_delta_v(0.0, mass, isp) == 0.0
    assert reserve_pct(1.5, 6.0) == 25.0
    assert delta_v_for_recovery(3.0, "fuel-saving") < delta_v_for_recovery(3.0, None)


def test_rocket_equation_uses_module_isp() -> None:
    assert RCS_ISP_S == 220.0


def test_thermal_relaxes_toward_target() -> None:
    hot = temp_step(40.0, eclipse=False, load_w=40.0, dt_s=5000.0)
    cold = temp_step(-20.0, eclipse=False, load_w=40.0, dt_s=5000.0)
    assert hot < 40.0
    assert cold > -20.0


def _sample(**overrides: object) -> Sample:
    base = dict(
        ts=T0,
        bus_voltage=28.2,
        battery_soc=0.78,
        attitude_err_deg=0.2,
        wheel_rpm=1100.0,
        temp_c=18.0,
        comms_status="nominal",
        fuel_kg=4.2,
        in_eclipse=False,
        load_w=70.0,
    )
    base.update(overrides)
    return Sample(**base)  # type: ignore[arg-type]


def test_diagnosis_names_the_fault_and_what_still_works() -> None:
    early = _sample()
    late = _sample(
        ts=T0 + timedelta(minutes=5),
        bus_voltage=25.4,
        battery_soc=0.42,
        attitude_err_deg=3.4,
        wheel_rpm=4800.0,
        comms_status="no_carrier",
    )
    found = diagnose([early, late])
    names = {item.subsystem for item in found.findings}
    assert {"comms", "attitude", "bus_voltage"} <= names
    assert found.started_at == late.ts
    assert found.severity == "crit"
    assert any("propellant" in item or "propulsion" in item for item in found.still_works)
    assert "downlink" not in found.still_works


def test_reversibility_tags() -> None:
    assert classify("magnetorquer").reversible is True
    assert classify("safe_mode").tag == "REVERSIBLE"
    burn = classify("rcs")
    assert burn.reversible is False
    assert burn.tag == "IRREVERSIBLE"
    assert "propellant" in burn.reason


def test_aware_datetimes() -> None:
    assert T0.tzinfo is UTC
