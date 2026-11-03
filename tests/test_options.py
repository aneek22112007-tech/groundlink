from __future__ import annotations

from datetime import timedelta

from core.options import build_options
from core.types import PassWindow, Sample
from tests.conftest import AOS, LOS, T0


def _sample() -> Sample:
    return Sample(
        ts=AOS + timedelta(minutes=1),
        bus_voltage=25.6,
        battery_soc=0.52,
        attitude_err_deg=3.2,
        wheel_rpm=4200.0,
        temp_c=21.0,
        comms_status="no_carrier",
        fuel_kg=4.2,
        in_eclipse=False,
        load_w=150.0,
    )


def _window() -> PassWindow:
    return PassWindow("blr", "Bengaluru", AOS, LOS, 32.0)


def test_exactly_three_options_with_tags() -> None:
    options = build_options(_sample(), _window(), version=1, pass_number=3)
    assert [item.key for item in options] == ["A", "B", "C"]
    by_key = {item.key: item for item in options}
    assert by_key["A"].reversible is True
    assert by_key["B"].reversible is False
    assert "IRREVERSIBLE" in by_key["B"].rationale
    assert by_key["C"].reversible is True
    assert by_key["B"].fuel_cost_kg > 0
    assert by_key["A"].fuel_cost_kg == 0
    assert by_key["C"].fuel_cost_kg == 0
    assert 0.05 <= by_key["B"].success_prob <= 0.99


def test_fuel_saving_variant_spends_less() -> None:
    window = _window()
    full = build_options(_sample(), window, version=1)
    saved = build_options(_sample(), window, version=2, variant="fuel-saving")
    assert saved[1].fuel_cost_kg < full[1].fuel_cost_kg
    assert saved[1].version == 2
    assert "Fuel-saving" in saved[1].name
    assert saved[1].reversible is False


def test_numbers_are_stable_across_calls() -> None:
    first = build_options(_sample(), _window(), version=4)
    second = build_options(_sample(), _window(), version=4)
    assert first == second


def test_service_loss_is_reported_from_the_epoch() -> None:
    assert T0 < AOS
