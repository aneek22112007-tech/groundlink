"""In-process Kestrel-7. The live agents call the same functions one message at a time."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from agents.action_agent.sequence import build_sequence, checkpoint
from agents.common.gate import GateRequest, review_attempt, transmit_allowed
from agents.common.irreversibility import command_statement
from agents.common.roles import Role
from agents.context_agent.summary import render_summary
from agents.options_agent.propose import render_options, wants_fuel_saving
from core.diagnosis import diagnose
from core.options import build_options
from core.orbit import next_pass
from core.types import GroundStation, OptionSpec, OrbitalElements, Sample
from demo.elements import KESTREL_ELEMENTS, KESTREL_STATION, epoch
from telemetry.plant import Plant, apply_recovery, step


@dataclass
class Line:
    who: str
    role: str
    text: str
    sim_t: str


@dataclass
class StoryResult:
    persistence: bool
    outcome: str
    lines: list[Line] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    transmitted: bool = False
    option_version: int = 0
    fuel_cost_kg: float = 0.0
    authoriser: str | None = None
    confirmer: str | None = None
    audit_note: str = ""


def _say(result: StoryResult, who: str, role: str, text: str, moment: datetime) -> None:
    result.lines.append(Line(who, role, text, moment.strftime("%Y-%m-%dT%H:%M:%SZ")))


def run_kestrel(*, persistence: bool, seed: int = 7, humans: bool = True) -> StoryResult:
    """Replay the anomaly.

    With persistence and humans, Priya rejects option A, asks for a fuel-saving
    burn, and Arjun's statement plus Priya's confirmation transmit option B.
    With persistence off, room memory is empty and the authorisation is not
    visible, so nothing is transmitted and the bus is lost.
    """
    rng = random.Random(seed)
    start = epoch()
    initial = Sample(
        ts=start,
        bus_voltage=28.1,
        battery_soc=0.70,
        attitude_err_deg=0.25,
        wheel_rpm=1100.0,
        temp_c=18.0,
        comms_status="nominal",
        fuel_kg=4.2,
        in_eclipse=False,
        load_w=80.0,
    )
    plant = Plant(sample=initial, drift_rate_deg_s=0.0, load_w=80.0, comms_status="nominal")
    result = StoryResult(persistence=persistence, outcome="open")
    incidents = _incidents() if persistence else []
    diagnosed = False
    proposed: list[OptionSpec] | None = None
    version = 1
    variant: str | None = None
    rejected_a = False
    approvals: list[tuple[str, Role, str, datetime, str]] = []
    fired = False
    previous_err: float | None = None
    dt = 30.0
    # 70 minutes of sim time. The pass opens at about 40 minutes.
    for _ in range(140):
        sample = plant.snapshot()
        result.samples.append(sample)
        elapsed = (sample.ts - start).total_seconds()
        if not plant.lost and plant.recovering is None:
            if elapsed >= 600:
                plant.drift_rate_deg_s = 0.0025
                plant.load_w = 320.0
                plant.comms_status = "no_carrier"
            elif elapsed >= 180:
                plant.comms_status = "no_carrier"
                plant.load_w = 140.0
        window = next_pass(KESTREL_ELEMENTS, [KESTREL_STATION], sample.ts)
        anomaly = sample.comms_status == "no_carrier" or sample.attitude_err_deg >= 1.5
        if anomaly and not diagnosed:
            diagnosis = diagnose(result.samples[-8:] or [sample])
            text = render_summary(
                sample,
                diagnosis,
                sat_name="Kestrel-7",
                window=window,
                incidents=incidents,
                persistence=persistence,
                dashboard_url="http://localhost:8090",
            )
            _say(result, "context-agent", "agent", text, sample.ts)
            diagnosed = True
            result.outcome = "diagnosing"
        if diagnosed and proposed is None and not plant.lost:
            proposed = build_options(
                sample, window, version=version, variant=variant, pass_number=3
            )
            _say(result, "options-agent", "agent", render_options(proposed), sample.ts)
            result.option_version = version
            result.outcome = "deciding"
        if humans and persistence and proposed is not None and not rejected_a and elapsed > 900:
            _say(
                result,
                "Priya Raman",
                "flight_ops_engineer",
                "Option A is too slow. We cannot wait out a magnetorquer desat.",
                sample.ts,
            )
            rejected_a = True
            _say(
                result,
                "Priya Raman",
                "flight_ops_engineer",
                "Request a fuel-saving variant of Option B.",
                sample.ts,
            )
            if wants_fuel_saving("Request a fuel-saving variant of Option B."):
                version += 1
                variant = "fuel-saving"
                proposed = build_options(
                    sample, window, version=version, variant=variant, pass_number=3
                )
                result.option_version = version
                _say(result, "options-agent", "agent", render_options(proposed), sample.ts)
        if (
            humans
            and persistence
            and proposed is not None
            and window is not None
            and window.contains(sample.ts)
            and not approvals
            and not plant.lost
        ):
            chosen = next(item for item in proposed if item.key == "B")
            statement = command_statement("B", chosen.pass_number)
            approvals.extend(_collect_auth(result, sample.ts, chosen, statement))
        if proposed is not None and approvals and not fired and not plant.lost:
            chosen = next(item for item in proposed if item.key == "B")
            req = GateRequest(
                reversible=chosen.reversible,
                option_key=chosen.key,
                current_version=chosen.version,
                pass_number=chosen.pass_number,
                window_aos=None if window is None else window.aos,
                window_los=None if window is None else window.los,
            )
            views = _views(approvals, chosen)
            decision = transmit_allowed(req, views, sample.ts)
            if decision.allowed:
                sequence = build_sequence(chosen)
                for index, item in enumerate(sequence, start=1):
                    verdict = checkpoint(item["step"], sample.attitude_err_deg, previous_err)
                    _say(
                        result,
                        "action-agent",
                        "agent",
                        f"TRANSMITTED seq {index} {item['step']} {item['payload']} ({verdict})",
                        sample.ts,
                    )
                apply_recovery(plant, chosen.kind, chosen.fuel_cost_kg, variant)
                fired = True
                result.transmitted = True
                result.fuel_cost_kg = chosen.fuel_cost_kg
                result.authoriser = "Arjun Mehta"
                result.confirmer = "Priya Raman"
                result.outcome = "executing"
                result.audit_note = (
                    "Authorised by Arjun Mehta (mission_director), confirmed by "
                    "Priya Raman (flight_ops_engineer)."
                )
            elif "second" not in decision.reason.casefold():
                _say(result, "action-agent", "agent", decision.reason, sample.ts)
        previous_err = sample.attitude_err_deg
        if plant.lost:
            result.outcome = "lost"
            _say(
                result,
                "action-agent",
                "agent",
                "No authorisation on record. Bus crossed the survival floor. Mission lost.",
                sample.ts,
            )
            break
        if fired and sample.attitude_err_deg <= 0.8 and plant.sample.comms_status == "nominal":
            # look at the sample we are about to leave; the corrected one arrives after step
            pass
        nxt = step(plant, dt, rng)
        if fired and nxt.attitude_err_deg <= 0.9 and nxt.comms_status == "nominal":
            result.samples.append(nxt)
            result.outcome = "recovered"
            _say(
                result,
                "action-agent",
                "agent",
                (
                    f"CONFIRMED recovered. Attitude error {nxt.attitude_err_deg:.2f} deg, "
                    f"bus {nxt.bus_voltage:.2f} V, fuel {nxt.fuel_kg:.3f} kg. "
                    f"{result.audit_note}"
                ),
                nxt.ts,
            )
            break
        if fired and (nxt.ts - start) > timedelta(minutes=65):
            result.outcome = "recovered" if nxt.attitude_err_deg < 2.0 else "executing"
            break
    else:
        if plant.lost:
            result.outcome = "lost"
        elif not fired:
            result.outcome = "lost"
            _say(
                result,
                "action-agent",
                "agent",
                "Pass window missed without a transmitted command. Mission lost.",
                plant.sample.ts,
            )
    return result


def _collect_auth(
    result: StoryResult,
    moment: datetime,
    chosen: OptionSpec,
    statement: str,
) -> list[tuple[str, Role, str, datetime, str]]:
    req = GateRequest(
        reversible=False,
        option_key="B",
        current_version=chosen.version,
        pass_number=chosen.pass_number,
        window_aos=moment - timedelta(minutes=1),
        window_los=moment + timedelta(minutes=8),
    )
    # The real window is applied by transmit_allowed. review uses a window that
    # contains `moment` because the caller already checked the pass is open.
    primary = review_attempt(
        statement,
        approver="Arjun Mehta",
        role=Role.MISSION_DIRECTOR,
        moment=moment,
        req=req,
    )
    _say(result, "Arjun Mehta", "mission_director", statement, moment)
    if primary.refusal:
        _say(result, "action-agent", "agent", primary.reason, moment)
        return []
    confirm_text = "Confirmed — Option B. Second operator confirmation."
    second = review_attempt(
        confirm_text,
        approver="Priya Raman",
        role=Role.FLIGHT_OPS_ENGINEER,
        moment=moment + timedelta(seconds=20),
        req=req,
    )
    _say(result, "Priya Raman", "flight_ops_engineer", confirm_text, moment + timedelta(seconds=20))
    if second.refusal or not primary.store or not second.store:
        _say(result, "action-agent", "agent", second.reason, moment)
        return []
    return [
        ("Arjun Mehta", Role.MISSION_DIRECTOR, statement, moment, "mm-arjun"),
        (
            "Priya Raman",
            Role.FLIGHT_OPS_ENGINEER,
            confirm_text,
            moment + timedelta(seconds=20),
            "mm-priya",
        ),
    ]


def _views(approvals: list[tuple[str, Role, str, datetime, str]], chosen: OptionSpec):  # type: ignore[no-untyped-def]
    from agents.common.gate import ApprovalView

    return [
        ApprovalView(name, role, text, message_id, ts, chosen.key, chosen.version)
        for name, role, text, ts, message_id in approvals
    ]


def _incidents() -> list[dict[str, str]]:
    return [
        {
            "id": "inc-2026-07-02-kestrel7",
            "title": "2 July eclipse sag",
        },
        {
            "id": "inc-2026-07-08-kestrel7",
            "title": "8 July eclipse sag",
        },
        {
            "id": "inc-2026-07-11-kestrel7",
            "title": "11 July eclipse sag",
        },
    ]


def elements_for_tests() -> tuple[OrbitalElements, GroundStation]:
    return KESTREL_ELEMENTS, KESTREL_STATION
