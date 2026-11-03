"""Command steps for one option. Payloads are JSON the plant understands."""

from __future__ import annotations

import json

from core.types import OptionSpec


def build_sequence(option: OptionSpec) -> list[dict[str, str]]:
    variant = "fuel-saving" if "fuel-saving" in option.name.casefold() else ""
    common = {
        "kind": option.kind,
        "option": option.key,
        "version": str(option.version),
        "variant": variant,
    }
    if option.kind == "rcs":
        steps = [
            (
                "arm_rcs",
                {**common, "thruster": "RCS-A", "note": "arm is reversible until the pulse"},
            ),
            (
                "fire_pulse",
                {
                    **common,
                    "fuel_cost_kg": f"{option.fuel_cost_kg:.3f}",
                    "note": "propellant expenditure, irreversible",
                },
            ),
            ("verify_rate", {**common, "expect": "attitude error decreasing"}),
            ("restore_downlink", {**common, "note": "return the payload if the bus allows"}),
        ]
    elif option.kind == "magnetorquer":
        steps = [
            ("enable_magnetorquers", {**common, "duty": "0.4"}),
            ("dump_wheels", {**common, "target_rpm": "1500"}),
            ("verify_rate", {**common, "expect": "slow convergence"}),
        ]
    elif option.kind == "safe_mode":
        steps = [
            ("shed_payload", {**common, "load_w": "42"}),
            ("sun_point", {**common, "note": "mode change, reversible"}),
            ("confirm_survival", {**common, "expect": "voltage recovering"}),
        ]
    else:
        raise ValueError(option.kind)
    return [{"step": name, "payload": json.dumps(payload)} for name, payload in steps]


def checkpoint(step: str, attitude_err_deg: float, previous_err_deg: float | None) -> str:
    """continue, rollback, or confirm. Tied to the telemetry the step just saw."""
    if step == "verify_rate":
        if previous_err_deg is not None and attitude_err_deg > previous_err_deg + 0.05:
            return "rollback"
        if attitude_err_deg <= 0.8:
            return "confirm"
        return "continue"
    if step in {"confirm_survival", "restore_downlink"} and attitude_err_deg <= 1.0:
        return "confirm"
    if step == "confirm_survival":
        return "continue"
    return "continue"
