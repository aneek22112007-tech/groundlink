from __future__ import annotations

from datetime import timedelta

from core.orbit import next_pass
from demo.elements import KESTREL_ELEMENTS, KESTREL_STATION, epoch
from demo.story import run_kestrel


def test_pass_opens_about_forty_minutes_after_epoch() -> None:
    window = next_pass(KESTREL_ELEMENTS, [KESTREL_STATION], epoch(), horizon_s=6 * 3600)
    assert window is not None
    delay = window.aos - epoch()
    assert timedelta(minutes=38) < delay < timedelta(minutes=42)
    assert window.duration_s > 8 * 60
    assert window.station_name == "Bengaluru"


def test_persistent_run_recovers_with_a_named_authorisation() -> None:
    result = run_kestrel(persistence=True, seed=7, humans=True)
    text = "\n".join(line.text for line in result.lines)
    assert result.transmitted is True
    assert result.outcome == "recovered"
    assert "Bus voltage degraded 3 times this month" in text
    assert "Option A is too slow" in text
    assert "Fuel-saving" in text
    assert "I am taking command responsibility" in text
    assert "Priya Raman" in text
    assert "Arjun Mehta" in text
    assert "TRANSMITTED" in text
    assert "CONFIRMED recovered" in text
    assert result.fuel_cost_kg > 0


def test_killswitch_loses_the_satellite_without_transmitting() -> None:
    lost = run_kestrel(persistence=False, seed=7, humans=False)
    text = "\n".join(line.text for line in lost.lines)
    assert lost.transmitted is False
    assert lost.outcome == "lost"
    assert "PERSISTENCE is off" in text
    assert "3 times this month" not in text
    assert "TRANSMITTED" not in text
    assert "Mission lost" in text
