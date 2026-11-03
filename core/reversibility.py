"""Whether a command class can be undone, and the reason a human must read."""

from __future__ import annotations

from core.types import Reversibility

_REASONS: dict[str, Reversibility] = {
    "magnetorquer": Reversibility(
        reversible=True,
        tag="REVERSIBLE",
        reason=(
            "Magnetorquer torque can be removed. No propellant is spent and "
            "the previous wheel state stays reachable."
        ),
    ),
    "safe_mode": Reversibility(
        reversible=True,
        tag="REVERSIBLE",
        reason=(
            "Safe mode is a mode change. A later command can restore payload "
            "operations without having spent propellant."
        ),
    ),
    "rcs": Reversibility(
        reversible=False,
        tag="IRREVERSIBLE",
        reason=(
            "A reaction-control burn expends propellant and changes orbital "
            "velocity. Neither can be undone."
        ),
    ),
}


def classify(kind: str) -> Reversibility:
    try:
        return _REASONS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown command kind {kind}") from exc
