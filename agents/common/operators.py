"""Named operators for the Kestrel-7 room. Roles are not inferred from free text."""

from __future__ import annotations

from agents.common.roles import Role

_DIRECTORY: dict[str, tuple[str, Role]] = {
    "priya": ("Priya Raman", Role.FLIGHT_OPS_ENGINEER),
    "priya raman": ("Priya Raman", Role.FLIGHT_OPS_ENGINEER),
    "arjun": ("Arjun Mehta", Role.MISSION_DIRECTOR),
    "arjun mehta": ("Arjun Mehta", Role.MISSION_DIRECTOR),
    "guest": ("Guest", Role.OBSERVER),
    "observer": ("Guest", Role.OBSERVER),
}


def resolve_operator(name: str) -> tuple[str, Role] | None:
    key = " ".join(name.casefold().replace("@", "").split())
    if key in _DIRECTORY:
        return _DIRECTORY[key]
    first = key.split(" ")[0]
    return _DIRECTORY.get(first)
