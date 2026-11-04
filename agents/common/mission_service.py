"""Mission writes. Command transmission goes through `commit_transmit` and nowhere else."""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.action_agent.sequence import build_sequence
from agents.common.audit import append_event, load_chain, verify_chain
from agents.common.gate import ApprovalView, GateRequest, review_attempt
from agents.common.irreversibility import is_approval_attempt, is_confirmation, statement_matches
from agents.common.models import (
    Approval,
    Command,
    Incident,
    Mission,
    Operator,
    Option,
    Satellite,
    SimClock,
    Telemetry,
)
from agents.common.operators import resolve_operator
from agents.common.roles import Role, parse_role
from agents.common.timeutil import as_utc, utcnow
from agents.common.transmit import commit_transmit, option_public_id, record_approval, set_status
from core.diagnosis import diagnose
from core.options import OptionSpec, build_options
from core.orbit import countdown_s, next_pass
from core.types import Diagnosis, GroundStation, OrbitalElements, PassWindow, Sample
from demo.elements import KESTREL_ELEMENTS, KESTREL_STATION, epoch


def ensure_clock(session: Session) -> SimClock:
    clock = session.get(SimClock, 1)
    if clock is None:
        clock = SimClock(id=1, sim_now=epoch(), time_scale=20.0, seed=7)
        session.add(clock)
        session.flush()
    return clock


def sim_now(session: Session) -> datetime:
    return as_utc(ensure_clock(session).sim_now)


def set_clock(session: Session, moment: datetime, scale: float | None = None) -> SimClock:
    clock = ensure_clock(session)
    clock.sim_now = as_utc(moment)
    if scale is not None:
        clock.time_scale = scale
    session.flush()
    return clock


def seed_reference(session: Session) -> None:
    if session.get(Satellite, "kestrel-7") is None:
        session.add(
            Satellite(
                id="kestrel-7",
                name="Kestrel-7",
                altitude_km=KESTREL_ELEMENTS.altitude_km,
                inclination_deg=math.degrees(KESTREL_ELEMENTS.inclination_rad),
                raan_deg=math.degrees(KESTREL_ELEMENTS.raan_rad),
                true_anomaly_deg=math.degrees(KESTREL_ELEMENTS.true_anomaly_rad),
                epoch=KESTREL_ELEMENTS.epoch,
                fuel_capacity_kg=6.0,
                wet_mass_kg=122.2,
            )
        )
    for username, display, role in (
        ("priya", "Priya Raman", Role.FLIGHT_OPS_ENGINEER.value),
        ("arjun", "Arjun Mehta", Role.MISSION_DIRECTOR.value),
        ("guest", "Guest", Role.OBSERVER.value),
    ):
        if session.get(Operator, username) is None:
            session.add(Operator(username=username, display_name=display, role=role))
    incidents = [
        (
            "inc-2026-07-02-kestrel7",
            "2 July eclipse sag",
            datetime(2026, 7, 2, tzinfo=epoch().tzinfo),
        ),
        (
            "inc-2026-07-08-kestrel7",
            "8 July eclipse sag",
            datetime(2026, 7, 8, tzinfo=epoch().tzinfo),
        ),
        (
            "inc-2026-07-11-kestrel7",
            "11 July eclipse sag",
            datetime(2026, 7, 11, tzinfo=epoch().tzinfo),
        ),
    ]
    for ident, title, opened in incidents:
        if session.get(Incident, ident) is None:
            session.add(
                Incident(
                    id=ident,
                    sat_id="kestrel-7",
                    title=title,
                    opened=opened,
                    summary="Bus voltage sagged on eclipse exit. Recovered after the pass.",
                    subsystem="bus_voltage",
                )
            )
    ensure_clock(session)
    if current_mission(session) is None:
        open_mission(session)
    session.flush()


def open_mission(session: Session, *, persistence: bool = True) -> Mission:
    mission = Mission(
        id=f"mission-{uuid.uuid4().hex[:12]}",
        sat_id="kestrel-7",
        status="open",
        opened=sim_now(session),
        summary="",
        pass_number=3,
        option_version=1,
        persistence=persistence,
        variant="",
        generation=_next_generation(session),
    )
    session.add(mission)
    append_event(
        session, mission.id, "mission.opened", {"sat_id": mission.sat_id}, ts=mission.opened
    )
    session.flush()
    return mission


def current_mission(session: Session) -> Mission | None:
    return session.scalar(select(Mission).order_by(Mission.generation.desc()).limit(1))


def _next_generation(session: Session) -> int:
    current = session.scalar(
        select(Mission.generation).order_by(Mission.generation.desc()).limit(1)
    )
    return 1 if current is None else int(current) + 1


def elements_of(sat: Satellite) -> OrbitalElements:
    return OrbitalElements(
        altitude_km=sat.altitude_km,
        inclination_rad=math.radians(sat.inclination_deg),
        raan_rad=math.radians(sat.raan_deg),
        true_anomaly_rad=math.radians(sat.true_anomaly_deg),
        epoch=as_utc(sat.epoch),
    )


def station() -> GroundStation:
    return KESTREL_STATION


def reset_run(
    session: Session, *, persistence: bool, seed: int = 7, time_scale: float = 20.0
) -> Mission:
    """Open a fresh mission at epoch. The previous mission stays in the audit log."""
    seed_reference(session)
    clock = set_clock(session, epoch(), time_scale)
    clock.seed = seed
    session.flush()
    return open_mission(session, persistence=persistence)


def current_pass(session: Session) -> PassWindow | None:
    sat = session.get(Satellite, "kestrel-7")
    if sat is None:
        elements = KESTREL_ELEMENTS
    else:
        elements = elements_of(sat)
    return next_pass(elements, [station()], sim_now(session))


def record_telemetry(session: Session, sample: Sample) -> None:
    set_clock(session, sample.ts)
    mission = current_mission(session)
    session.add(
        Telemetry(
            ts=sample.ts,
            sat_id="kestrel-7",
            bus_voltage=sample.bus_voltage,
            battery_soc=sample.battery_soc,
            attitude_err_deg=sample.attitude_err_deg,
            wheel_rpm=sample.wheel_rpm,
            temp_c=sample.temp_c,
            comms_status=sample.comms_status,
            fuel_kg=sample.fuel_kg,
            in_eclipse=sample.in_eclipse,
            load_w=sample.load_w,
            mission_id="" if mission is None else mission.id,
        )
    )
    if mission is not None and mission.status not in {"recovered", "lost", "closed"}:
        if sample.bus_voltage < 22.5 or sample.battery_soc < 0.18:
            mission.status = "lost"
            append_event(
                session,
                mission.id,
                "mission.lost",
                {"bus_voltage": sample.bus_voltage, "battery_soc": sample.battery_soc},
                ts=sample.ts,
            )
    session.flush()


def recent_samples(session: Session, limit: int = 240) -> list[Sample]:
    mission = current_mission(session)
    query = select(Telemetry).order_by(Telemetry.id.desc()).limit(limit)
    if mission is not None:
        query = (
            select(Telemetry)
            .where(Telemetry.mission_id == mission.id)
            .order_by(Telemetry.id.desc())
            .limit(limit)
        )
    rows = session.scalars(query).all()
    samples = [
        Sample(
            ts=as_utc(row.ts),
            bus_voltage=row.bus_voltage,
            battery_soc=row.battery_soc,
            attitude_err_deg=row.attitude_err_deg,
            wheel_rpm=row.wheel_rpm,
            temp_c=row.temp_c,
            comms_status=row.comms_status,
            fuel_kg=row.fuel_kg,
            in_eclipse=row.in_eclipse,
            load_w=row.load_w,
        )
        for row in reversed(rows)
    ]
    return samples


def month_incidents(session: Session, moment: datetime) -> list[Incident]:
    rows = session.scalars(select(Incident).where(Incident.sat_id == "kestrel-7")).all()
    return [
        row
        for row in rows
        if as_utc(row.opened).year == moment.year and as_utc(row.opened).month == moment.month
    ]


def log_room(session: Session, who: str, role: str, text: str, message_id: str = "") -> None:
    mission = current_mission(session)
    if mission is None:
        return
    append_event(
        session,
        mission.id,
        "room.message",
        {"who": who, "role": role, "text": text, "message_id": message_id},
        ts=sim_now(session),
    )
    session.flush()


def save_options(session: Session, specs: list[OptionSpec]) -> list[Option]:
    mission = current_mission(session)
    if mission is None:
        raise RuntimeError("no mission")
    stored: list[Option] = []
    for spec in specs:
        ident = option_public_id(mission.id, spec.version, spec.key)
        row = session.get(Option, ident)
        if row is None:
            row = Option(
                id=ident,
                mission_id=mission.id,
                key=spec.key,
                version=spec.version,
                name=spec.name,
                success_prob=spec.success_prob,
                power_cost=spec.power_cost_wh,
                fuel_cost_kg=spec.fuel_cost_kg,
                fuel_reserve_pct=spec.fuel_reserve_pct,
                service_loss_h=spec.service_loss_h,
                reversible=spec.reversible,
                rationale=spec.rationale,
                reversibility_reason=spec.reversibility_reason,
                kind=spec.kind,
                pass_number=spec.pass_number,
            )
            session.add(row)
        stored.append(row)
    mission.option_version = specs[0].version
    mission.status = "deciding"
    append_event(
        session,
        mission.id,
        "options.posted",
        {"version": specs[0].version, "keys": [item.key for item in specs]},
        ts=sim_now(session),
    )
    session.flush()
    return stored


def latest_options(session: Session) -> list[Option]:
    mission = current_mission(session)
    if mission is None:
        return []
    return list(
        session.scalars(
            select(Option)
            .where(Option.mission_id == mission.id, Option.version == mission.option_version)
            .order_by(Option.key.asc())
        )
    )


def option_spec(row: Option) -> OptionSpec:
    return OptionSpec(
        key=row.key,
        name=row.name,
        version=row.version,
        success_prob=row.success_prob,
        power_cost_wh=row.power_cost,
        fuel_cost_kg=row.fuel_cost_kg,
        fuel_reserve_pct=row.fuel_reserve_pct,
        service_loss_h=row.service_loss_h,
        reversible=row.reversible,
        reversibility_reason=row.reversibility_reason or row.rationale,
        rationale=row.rationale,
        kind=row.kind,
        pass_number=row.pass_number,
    )


def propose(session: Session, variant: str | None, version: int) -> list[OptionSpec]:
    samples = recent_samples(session, limit=30)
    if not samples:
        raise RuntimeError("no telemetry")
    specs = build_options(
        samples[-1],
        current_pass(session),
        version=version,
        variant=variant,
        pass_number=3,
    )
    save_options(session, specs)
    mission = current_mission(session)
    if mission is not None:
        mission.variant = variant or ""
        session.flush()
    return specs


def queue_option(session: Session, key: str) -> list[Command]:
    mission = current_mission(session)
    if mission is None:
        raise RuntimeError("no mission")
    row = session.scalar(
        select(Option).where(
            Option.mission_id == mission.id,
            Option.version == mission.option_version,
            Option.key == key,
        )
    )
    if row is None:
        raise RuntimeError(f"option {key} is not on the current version")
    existing = session.scalars(
        select(Command).where(Command.mission_id == mission.id, Command.option_id == row.id)
    ).all()
    if existing:
        return list(existing)
    spec = option_spec(row)
    used = session.scalars(select(Command.seq).where(Command.mission_id == mission.id)).all()
    start = (max(used) if used else 0) + 1
    created: list[Command] = []
    for offset, item in enumerate(build_sequence(spec)):
        command = Command(
            id=f"cmd-{uuid.uuid4().hex[:12]}",
            seq=start + offset,
            mission_id=mission.id,
            option_id=row.id,
            step=item["step"],
            payload=item["payload"],
            status="queued",
        )
        session.add(command)
        session.flush()
        set_status(command, "awaiting_auth")
        created.append(command)
    append_event(
        session,
        mission.id,
        "commands.queued",
        {"option_id": row.id, "steps": [item.step for item in created]},
        ts=sim_now(session),
    )
    session.flush()
    return created


def gate_request_for(session: Session, option: Option) -> GateRequest:
    window = current_pass(session)
    return GateRequest(
        reversible=option.reversible,
        option_key=option.key,
        current_version=option.version,
        pass_number=option.pass_number or 3,
        window_aos=None if window is None else window.aos,
        window_los=None if window is None else window.los,
    )


def ingest_human(session: Session, author: str, text: str, message_id: str) -> dict[str, object]:
    resolved = resolve_operator(author)
    if resolved is None:
        log_room(session, author, "unknown", text, message_id)
        return {"stored": False, "refusal": False, "reason": "unknown operator"}
    display, role = resolved
    mission = current_mission(session)
    if mission is not None and _room_has(session, mission.id, display, text):
        return {"stored": False, "refusal": False, "reason": "duplicate"}
    log_room(session, display, role.value, text, message_id)
    options = latest_options(session)
    if mission is None or not options:
        return {"stored": False, "refusal": False, "reason": "no options yet"}
    target = _targeted_option(text, options)
    if target is None:
        return {"stored": False, "refusal": False, "reason": "no option named"}
    if not _looks_like_gate_text(text, target):
        return {"stored": False, "refusal": False, "reason": "noted"}
    req = gate_request_for(session, target)
    moment = sim_now(session)
    attempt = review_attempt(text, approver=display, role=role, moment=moment, req=req)
    result: dict[str, object] = {
        "stored": attempt.store,
        "refusal": attempt.refusal,
        "reason": attempt.reason,
        "option": target.key,
    }
    if attempt.refusal:
        append_event(
            session,
            mission.id,
            "approval.refused",
            {
                "approver": display,
                "role": role.value,
                "reason": attempt.reason,
                "message_id": message_id,
            },
            ts=moment,
        )
        if not _room_has(session, mission.id, "Action", attempt.reason):
            log_room(session, "Action", "action_agent", attempt.reason, message_id)
    if attempt.store and attempt.binds_version is not None:
        record_approval(
            session,
            mission_id=mission.id,
            option_id=target.id,
            option_key=target.key,
            option_version=attempt.binds_version,
            action="confirm" if "confirm" in text.casefold() else "authorise",
            approver=display,
            role=role.value,
            message_id=message_id or f"local-{uuid.uuid4().hex[:8]}",
            statement=text,
            ts=moment,
        )
        queue_option(session, target.key)
    session.flush()
    return result


def _looks_like_gate_text(text: str, option: Option) -> bool:
    if is_approval_attempt(text) or is_confirmation(text, option.key):
        return True
    return statement_matches(text, option.key, option.pass_number or 3)


def _room_has(session: Session, mission_id: str, who: str, text: str) -> bool:
    for line in room_lines(session, mission_id):
        if line.get("who") == who and line.get("text") == text:
            return True
    return False


def _targeted_option(text: str, options: list[Option]) -> Option | None:
    folded = text.casefold()
    for row in options:
        if f"option {row.key.casefold()}" in folded:
            return row
    return None


def try_transmit_all(session: Session, limit: int | None = None) -> list[dict[str, object]]:
    """Transmit authorised steps in order. `limit` caps how many go out this call."""
    mission = current_mission(session)
    if mission is None:
        return []
    moment = sim_now(session)
    window = current_pass(session)
    if window is None or not window.contains(moment):
        reason = (
            "Pass window is not open yet."
            if window and moment < window.aos
            else "Refused: the pass window has closed."
        )
        if window is None:
            reason = "Refused: no pass window is on record."
        return [{"allowed": False, "reason": reason}]
    commands = list(
        session.scalars(
            select(Command)
            .where(Command.mission_id == mission.id, Command.status == "awaiting_auth")
            .order_by(Command.seq.asc())
        )
    )
    outcomes: list[dict[str, object]] = []
    for command in commands:
        if limit is not None and sum(1 for item in outcomes if item["allowed"]) >= limit:
            break
        option = session.get(Option, command.option_id)
        if option is None or option.version != mission.option_version:
            outcomes.append(
                {
                    "seq": command.seq,
                    "allowed": False,
                    "reason": "stale option",
                    "step": command.step,
                }
            )
            continue
        if _already_refused(session, command.id):
            outcomes.append(
                {
                    "seq": command.seq,
                    "allowed": False,
                    "reason": "already refused",
                    "step": command.step,
                }
            )
            continue
        decision = commit_transmit(session, command, gate_request_for(session, option), moment)
        outcomes.append(
            {
                "seq": command.seq,
                "step": command.step,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "status": command.status,
                "payload": command.payload,
            }
        )
    if any(item["allowed"] for item in outcomes):
        mission.status = "executing"
    session.flush()
    return outcomes


def _already_refused(session: Session, command_id: str) -> bool:
    for row in load_chain(session):
        if row.kind != "command.refused":
            continue
        payload = json.loads(row.payload_json)
        if payload.get("command_id") == command_id:
            return True
    return False


def confirm_if_recovered(session: Session, sample: Sample) -> bool:
    mission = current_mission(session)
    if mission is None or mission.status != "executing":
        return False
    if sample.attitude_err_deg > 1.0 or sample.comms_status == "no_carrier":
        return False
    commands = session.scalars(
        select(Command).where(Command.mission_id == mission.id, Command.status == "transmitted")
    ).all()
    for command in commands:
        set_status(command, "confirmed")
    mission.status = "recovered"
    append_event(
        session,
        mission.id,
        "mission.recovered",
        {
            "bus_voltage": sample.bus_voltage,
            "attitude_err_deg": sample.attitude_err_deg,
            "fuel_kg": sample.fuel_kg,
        },
        ts=sample.ts,
    )
    session.flush()
    return True


def approval_views(session: Session, mission_id: str, option: Option) -> list[ApprovalView]:
    rows = session.scalars(select(Approval).where(Approval.mission_id == mission_id)).all()
    views: list[ApprovalView] = []
    for row in rows:
        if row.option_id != option.id and not row.option_id.endswith(f":{option.key}"):
            continue
        views.append(
            ApprovalView(
                approver=row.approver,
                role=parse_role(row.role),
                statement=row.statement,
                message_id=row.message_id,
                ts=as_utc(row.ts),
                option_key=option.key,
                option_version=row.option_version,
            )
        )
    return views


def diagnosis_of(session: Session) -> Diagnosis | None:
    samples = recent_samples(session, limit=12)
    if not samples:
        return None
    return diagnose(samples)


def pass_brief(window: PassWindow | None, moment: datetime) -> dict[str, object]:
    if window is None:
        return {"open": False, "countdown_s": None, "station": None}
    remaining = countdown_s(window, moment)
    return {
        "open": window.contains(moment),
        "countdown_s": remaining,
        "station": window.station_name,
        "aos": window.aos.isoformat(),
        "los": window.los.isoformat(),
        "max_elevation_deg": window.max_elevation_deg,
        "duration_s": window.duration_s,
    }


def chain_status(session: Session) -> dict[str, object]:
    rows = load_chain(session)
    ok, detail = verify_chain(rows)
    return {"ok": ok, "detail": detail, "length": len(rows)}


def audit_link(mission_id: str, base: str) -> str:
    return f"{base.rstrip('/')}/audit/{mission_id}"


def room_lines(session: Session, mission_id: str) -> list[dict[str, object]]:
    rows = load_chain(session)
    lines = []
    for row in rows:
        if row.mission_id != mission_id or row.kind != "room.message":
            continue
        payload = json.loads(row.payload_json)
        lines.append({"ts": as_utc(row.ts).isoformat(), "hash": row.row_hash, **payload})
    return lines


def stale_after(moment: datetime, minutes: float = 40.0) -> datetime:
    return moment + timedelta(minutes=minutes)


def who_authorised(session: Session, mission_id: str) -> list[dict[str, object]]:
    rows = session.scalars(
        select(Approval).where(Approval.mission_id == mission_id).order_by(Approval.id)
    ).all()
    return [
        {
            "approver": row.approver,
            "role": row.role,
            "statement": row.statement,
            "message_id": row.message_id,
            "ts": as_utc(row.ts).isoformat(),
            "option_id": row.option_id,
            "action": row.action,
        }
        for row in rows
    ]


def touch_status(session: Session, status: str) -> None:
    mission = current_mission(session)
    if mission is not None:
        mission.status = status
        append_event(session, mission.id, "mission.status", {"status": status}, ts=sim_now(session))
        session.flush()


def utc_stamp() -> str:
    return utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
