import json
from datetime import UTC, datetime

from core.types import Sample
from demo.playback import _absorb
from telemetry.plant import Plant


def _plant() -> Plant:
    sample = Sample(
        ts=datetime(2026, 7, 14, 12, 40, tzinfo=UTC),
        bus_voltage=25.7,
        battery_soc=60.0,
        attitude_err_deg=40.0,
        wheel_rpm=1100.0,
        temp_c=18.0,
        comms_status="no_carrier",
        fuel_kg=4.2,
        in_eclipse=False,
        load_w=80.0,
    )
    return Plant(sample=sample, drift_rate_deg_s=0.0, load_w=80.0, comms_status="no_carrier")


def _cmd(seq: int, status: str, **payload: str) -> dict[str, object]:
    body = {"kind": "rcs", "variant": "fuel-saving", **payload}
    return {"option_id": "m:2:B", "seq": seq, "status": status, "payload": json.dumps(body)}


def test_step_by_step_sequence_burns_exactly_once() -> None:
    plant, applied = _plant(), set()
    cmds = [_cmd(1, "transmitted"), _cmd(2, "awaiting_auth", fuel_cost_kg="0.196")]
    _absorb(plant, {"commands": cmds}, applied)
    assert plant.recovering == "rcs-save"
    assert plant.sample.fuel_kg == 4.2
    cmds[1]["status"] = "transmitted"
    _absorb(plant, {"commands": cmds}, applied)
    _absorb(plant, {"commands": cmds}, applied)
    assert plant.sample.fuel_kg == round(4.2 - 0.196, 4)
