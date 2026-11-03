"""Threshold checks over a telemetry window. The caller supplies the samples."""

from __future__ import annotations

from datetime import datetime

from core.types import Diagnosis, Finding, Sample

VOLTAGE_WARN = 26.5
VOLTAGE_CRIT = 24.8
SOC_WARN = 0.45
SOC_CRIT = 0.30
ATT_WARN = 1.5
ATT_CRIT = 3.0
WHEEL_WARN = 4500.0
WHEEL_CRIT = 5500.0
TEMP_WARN = 35.0
TEMP_CRIT = 45.0


def _sev(value: float, warn: float, crit: float, *, low_is_bad: bool) -> str:
    if low_is_bad:
        if value <= crit:
            return "crit"
        if value <= warn:
            return "warn"
        return "nominal"
    if value >= crit:
        return "crit"
    if value >= warn:
        return "warn"
    return "nominal"


def _worst(levels: list[str]) -> str:
    if "crit" in levels:
        return "crit"
    if "warn" in levels:
        return "warn"
    return "nominal"


def diagnose(samples: list[Sample]) -> Diagnosis:
    if not samples:
        raise ValueError("diagnose requires at least one sample")
    latest = samples[-1]
    findings: list[Finding] = []

    voltage = _sev(latest.bus_voltage, VOLTAGE_WARN, VOLTAGE_CRIT, low_is_bad=True)
    if voltage != "nominal":
        findings.append(Finding("bus_voltage", voltage, f"bus voltage {latest.bus_voltage:.2f} V"))

    soc = _sev(latest.battery_soc, SOC_WARN, SOC_CRIT, low_is_bad=True)
    if soc != "nominal":
        findings.append(Finding("battery_soc", soc, f"state of charge {latest.battery_soc:.0%}"))

    att = _sev(latest.attitude_err_deg, ATT_WARN, ATT_CRIT, low_is_bad=False)
    if att != "nominal":
        findings.append(
            Finding("attitude", att, f"attitude error {latest.attitude_err_deg:.2f} deg")
        )

    wheel = _sev(latest.wheel_rpm, WHEEL_WARN, WHEEL_CRIT, low_is_bad=False)
    if wheel != "nominal":
        findings.append(
            Finding("reaction_wheels", wheel, f"wheel speed {latest.wheel_rpm:.0f} rpm")
        )

    thermal = _sev(latest.temp_c, TEMP_WARN, TEMP_CRIT, low_is_bad=False)
    if thermal != "nominal":
        findings.append(Finding("thermal", thermal, f"bus temperature {latest.temp_c:.1f} C"))

    carrier_lost = latest.comms_status == "no_carrier"
    if carrier_lost:
        findings.append(Finding("comms", "crit", "no carrier on the downlink"))
    elif latest.comms_status == "degraded":
        findings.append(Finding("comms", "warn", "downlink degraded"))

    started = _onset(samples)
    works: list[str] = []
    if thermal == "nominal":
        works.append("thermal control")
    if latest.battery_soc > SURVIVAL_FLOOR:
        works.append("battery above the survival floor")
    if latest.fuel_kg > 0.2:
        works.append("propulsion still has propellant")
    if not carrier_lost:
        works.append("downlink")
    else:
        works.append("on-board computer (no downlink, bus still reporting locally)")

    levels = [item.severity for item in findings]
    return Diagnosis(
        findings=tuple(findings),
        started_at=started,
        still_works=tuple(works),
        severity=_worst(levels) if levels else "nominal",
    )


SURVIVAL_FLOOR = 0.18


def _onset(samples: list[Sample]) -> datetime:
    for sample in samples:
        if (
            sample.comms_status == "no_carrier"
            or sample.attitude_err_deg >= ATT_WARN
            or sample.bus_voltage <= VOLTAGE_WARN
        ):
            return sample.ts
    return samples[-1].ts
