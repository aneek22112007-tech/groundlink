"""Render the three options. Numbers come from core.build_options."""

from __future__ import annotations

from core.types import OptionSpec


def wants_fuel_saving(text: str) -> bool:
    folded = text.casefold()
    return "fuel-saving" in folded or "fuel saving" in folded


def rejects_slow_option(text: str) -> bool:
    folded = text.casefold()
    return "option a" in folded and any(word in folded for word in ("slow", "reject", "too slow"))


def render_options(options: list[OptionSpec]) -> str:
    if len(options) != 3:
        raise ValueError("the room is promised exactly three options")
    version = options[0].version
    lines = [
        f"OPTIONS v{version}",
        "Three options. The figures are from the simulator, not the model.",
    ]
    for item in options:
        tag = "REVERSIBLE" if item.reversible else "IRREVERSIBLE"
        lines.append(
            f"Option {item.key} — {item.name} [{tag}]. "
            f"P(success) {item.success_prob:.3f}. "
            f"Power {item.power_cost_wh:.1f} Wh. "
            f"Fuel {item.fuel_cost_kg:.3f} kg "
            f"(reserve {item.fuel_reserve_pct:.1f}%). "
            f"Service loss {item.service_loss_h:.2f} h. "
            f"{item.reversibility_reason} "
            f"{item.rationale}"
        )
    lines.append(
        "Option A is the slow reversible desaturation. "
        "Option B is the pass-3 burn. Option C sheds the payload."
    )
    return "\n".join(lines)
