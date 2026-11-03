"""Deterministic context summary. The model may only rephrase this text."""

from __future__ import annotations

from agents.common.timeutil import iso
from core.diagnosis import Diagnosis
from core.orbit import countdown_s
from core.types import PassWindow, Sample


def render_summary(
    sample: Sample,
    diagnosis: Diagnosis,
    *,
    sat_name: str,
    window: PassWindow | None,
    incidents: list[dict[str, str]],
    persistence: bool,
    dashboard_url: str,
) -> str:
    countdown = countdown_s(window, sample.ts)
    if window is None or countdown is None:
        pass_line = "No ground-station pass inside the planning horizon."
    elif countdown == 0.0:
        pass_line = (
            f"Pass is OPEN now over {window.station_name} until {iso(window.los)} "
            f"(max elevation {window.max_elevation_deg:.0f} deg)."
        )
    else:
        minutes = countdown / 60.0
        pass_line = (
            f"Next pass: {window.station_name} in {minutes:.0f} min "
            f"(AOS {iso(window.aos)}, LOS {iso(window.los)}, "
            f"max elevation {window.max_elevation_deg:.0f} deg)."
        )
    if persistence and incidents:
        links = ", ".join(
            f"{item['title']} ({dashboard_url}/incidents/{item['id']})" for item in incidents
        )
        history = f"Bus voltage degraded {len(incidents)} times this month. See {links}."
    elif persistence:
        history = "Room memory has no earlier bus-voltage incidents this month."
    else:
        history = (
            "PERSISTENCE is off. Room memory is empty, so this diagnosis "
            "does not cite earlier incidents or an earlier plan."
        )
    findings = "; ".join(f"{item.subsystem}: {item.detail}" for item in diagnosis.findings)
    if not findings:
        findings = "no threshold exceeded"
    works = ", ".join(diagnosis.still_works)
    return "\n".join(
        [
            f"CONTEXT {sat_name}",
            f"Severity: {diagnosis.severity}. Onset: {iso(diagnosis.started_at)}.",
            f"What is wrong: {findings}.",
            f"What still works: {works}.",
            (
                f"Latest: bus {sample.bus_voltage:.2f} V, SOC {sample.battery_soc:.0%}, "
                f"attitude error {sample.attitude_err_deg:.2f} deg, "
                f"wheels {sample.wheel_rpm:.0f} rpm, temp {sample.temp_c:.1f} C, "
                f"comms {sample.comms_status}, fuel {sample.fuel_kg:.2f} kg."
            ),
            pass_line,
            history,
        ]
    )
