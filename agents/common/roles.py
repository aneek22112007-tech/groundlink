"""Operator roles. The gate reads this module and nothing softer."""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    FLIGHT_OPS_ENGINEER = "flight_ops_engineer"
    MISSION_DIRECTOR = "mission_director"
    OBSERVER = "observer"


REVERSIBLE_ROLES = frozenset({Role.FLIGHT_OPS_ENGINEER, Role.MISSION_DIRECTOR})
IRREVERSIBLE_PRIMARY = frozenset({Role.MISSION_DIRECTOR})
SECOND_ROLES = frozenset({Role.FLIGHT_OPS_ENGINEER, Role.MISSION_DIRECTOR})


def parse_role(value: str) -> Role:
    try:
        return Role(value.strip().lower())
    except ValueError as exc:
        raise ValueError(f"unknown role {value}") from exc
