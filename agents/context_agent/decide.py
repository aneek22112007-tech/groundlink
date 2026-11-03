"""When the context agent speaks. Persistence off forgets the card it already posted."""

from __future__ import annotations

from core.types import Sample


def should_post_context(lines: list[dict[str, object]], sample: Sample, persistence: bool) -> bool:
    anomalous = (
        sample.comms_status == "no_carrier"
        or sample.attitude_err_deg >= 1.5
        or sample.bus_voltage <= 26.5
    )
    if not anomalous:
        return False
    contexts = [line for line in lines if str(line.get("text", "")).startswith("CONTEXT")]
    if persistence:
        return not contexts
    if not contexts:
        return True
    return sample.attitude_err_deg >= 1.5 and len(contexts) == 1
