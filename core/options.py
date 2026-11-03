"""Three recovery options, each scored by stepping the same physics forward."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.attitude import drift_step, settle_rate_deg_s
from core.constants import BUS_DRY_MASS_KG, FUEL_CAPACITY_KG, SURVIVAL_SOC, SURVIVAL_VOLTAGE
from core.fuel import delta_v_for_recovery, fuel_for_delta_v, reserve_pct
from core.power import bus_voltage, energy_wh, soc_step
from core.reversibility import classify
from core.thermal import temp_step
from core.types import OptionSpec, PassWindow, Sample, SimResult


@dataclass(frozen=True)
class _Policy:
    kind: str
    load_w: float
    variant: str | None
    wait_for_pass: bool
    immediate_safe: bool


def _round_prob(value: float) -> float:
    return round(min(0.99, max(0.05, value)), 3)


def success_probability(result: SimResult, kind: str) -> float:
    """Map a simulated trace to a probability. The LLM does not choose this."""
    prob = 0.93
    if result.min_voltage < 26.5:
        prob -= (26.5 - result.min_voltage) * 0.035
    if result.end_attitude_deg > 0.8 and kind != "safe_mode":
        prob -= min(0.4, (result.end_attitude_deg - 0.8) * 0.05)
    if not result.survived:
        prob -= 0.45
    if kind == "safe_mode" and result.survived:
        prob = max(prob, 0.9)
    if kind == "magnetorquer" and result.service_loss_h > 1.2:
        prob -= 0.08
    return _round_prob(prob)


def simulate(
    sample: Sample,
    policy: _Policy,
    window: PassWindow | None,
    *,
    horizon_s: float = 3 * 3600,
    dt_s: float = 30.0,
) -> SimResult:
    soc = sample.battery_soc
    err = sample.attitude_err_deg
    fuel = sample.fuel_kg
    temp = sample.temp_c
    moment = sample.ts
    end = sample.ts + timedelta(seconds=horizon_s)
    min_v = bus_voltage(soc, sample.load_w)
    power = 0.0
    burned = False
    service_loss_s = 0.0
    restored_at: datetime | None = None

    while moment < end:
        in_pass = window is not None and window.contains(moment)
        load = policy.load_w
        rate = 0.012 if err < 8 else 0.004
        if policy.kind == "safe_mode":
            load = 42.0
            rate = 0.0
            err = max(err, 6.0)
        elif policy.wait_for_pass and in_pass:
            rate = settle_rate_deg_s(policy.kind, policy.variant)
            if policy.kind == "rcs" and not burned:
                dv = delta_v_for_recovery(err, policy.variant)
                spent = fuel_for_delta_v(dv, BUS_DRY_MASS_KG + fuel)
                fuel = max(0.0, fuel - spent)
                burned = True
        eclipse = sample.in_eclipse
        soc = soc_step(soc, load, eclipse, dt_s)
        err = drift_step(err, rate, dt_s)
        temp = temp_step(temp, eclipse, load, dt_s)
        volts = bus_voltage(soc, load)
        min_v = min(min_v, volts)
        power += energy_wh(max(0.0, load - (0.0 if eclipse else 190.0)), dt_s)
        nominal = volts >= 26.0 and (err <= 0.8 or policy.kind == "safe_mode") and soc > 0.35
        if policy.kind == "safe_mode":
            nominal = volts >= 26.0 and soc > 0.4
        if not nominal:
            service_loss_s += dt_s
            restored_at = None
        elif restored_at is None:
            restored_at = moment
        moment += timedelta(seconds=dt_s)

    survived = min_v >= SURVIVAL_VOLTAGE and soc >= SURVIVAL_SOC
    return SimResult(
        min_voltage=round(min_v, 3),
        end_voltage=round(bus_voltage(soc, policy.load_w), 3),
        end_soc=round(soc, 4),
        end_attitude_deg=round(err, 3),
        end_fuel_kg=round(fuel, 4),
        service_loss_h=round(service_loss_s / 3600.0, 2),
        power_cost_wh=round(max(0.0, power), 1),
        survived=survived,
    )


def build_options(
    sample: Sample,
    window: PassWindow | None,
    *,
    version: int,
    variant: str | None = None,
    pass_number: int = 3,
) -> list[OptionSpec]:
    """Return exactly three options. `variant` replaces option B with a fuel-saving burn."""
    if version < 1:
        raise ValueError("version starts at 1")
    policies = [
        (
            "A",
            "Magnetorquer desaturation on the next pass",
            "magnetorquer",
            _Policy("magnetorquer", 160.0, None, True, False),
        ),
        (
            "B",
            (
                "Fuel-saving RCS recovery on pass 3"
                if variant == "fuel-saving"
                else "RCS attitude recovery on pass 3"
            ),
            "rcs",
            _Policy("rcs", 110.0, "fuel-saving" if variant == "fuel-saving" else None, True, False),
        ),
        (
            "C",
            "Safe mode, payload shed, sun-point",
            "safe_mode",
            _Policy("safe_mode", 42.0, None, False, True),
        ),
    ]
    options: list[OptionSpec] = []
    for key, name, kind, policy in policies:
        result = simulate(sample, policy, window)
        rev = classify(kind)
        fuel_cost = round(max(0.0, sample.fuel_kg - result.end_fuel_kg), 4)
        if kind != "rcs":
            fuel_cost = 0.0
        remaining = sample.fuel_kg - fuel_cost
        rationale = _rationale(key, name, result, rev.tag, fuel_cost, window)
        options.append(
            OptionSpec(
                key=key,
                name=name,
                version=version,
                success_prob=success_probability(result, kind),
                power_cost_wh=result.power_cost_wh,
                fuel_cost_kg=round(fuel_cost, 3),
                fuel_reserve_pct=round(reserve_pct(remaining, FUEL_CAPACITY_KG), 1),
                service_loss_h=result.service_loss_h,
                reversible=rev.reversible,
                reversibility_reason=rev.reason,
                rationale=rationale,
                kind=kind,
                pass_number=pass_number if kind != "safe_mode" else 0,
            )
        )
    if len(options) != 3:
        raise RuntimeError("options builder must return exactly three")
    return options


def _rationale(
    key: str,
    name: str,
    result: SimResult,
    tag: str,
    fuel_cost: float,
    window: PassWindow | None,
) -> str:
    station = window.station_name if window else "no station"
    return (
        f"Option {key} ({name}) is {tag}. "
        f"Simulated minimum bus voltage {result.min_voltage:.2f} V, "
        f"ending attitude error {result.end_attitude_deg:.2f} deg, "
        f"propellant {fuel_cost:.3f} kg, "
        f"service loss {result.service_loss_h:.2f} h, "
        f"next geometry {station}."
    )
