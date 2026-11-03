"""When to publish a new option set. A fuel-saving request bumps the version."""

from __future__ import annotations

from agents.options_agent.propose import wants_fuel_saving


def _texts(lines: list[dict[str, object]]) -> list[str]:
    return [str(line.get("text", "")) for line in lines]


def proposal_request(
    lines: list[dict[str, object]],
    option_names: list[str],
    *,
    persistence: bool,
    current_version: int,
) -> tuple[int, str | None] | None:
    texts = _texts(lines)
    if not any(text.startswith("CONTEXT") for text in texts):
        return None
    posted = [text for text in texts if text.startswith("OPTIONS v")]
    fuel = any(wants_fuel_saving(text) for text in texts)
    names = " ".join(option_names)
    if not posted:
        variant = "fuel-saving" if fuel else None
        return (1, variant)
    if persistence and fuel and "fuel-saving" not in names.casefold():
        return (current_version + 1, "fuel-saving")
    if not persistence and len([text for text in texts if text.startswith("CONTEXT")]) >= 2:
        if len(posted) == 1:
            return (current_version + 1, None)
    return None
