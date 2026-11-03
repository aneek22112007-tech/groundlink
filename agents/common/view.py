"""JSON the dashboard, the agents, and the simulator all read."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.common.mission_service import (
    chain_status,
    current_mission,
    current_pass,
    diagnosis_of,
    ensure_clock,
    latest_options,
    pass_brief,
    recent_samples,
    room_lines,
    sim_now,
    who_authorised,
)
from agents.common.models import Command
from agents.common.timeutil import iso
from core.types import Sample


def sample_dict(sample: Sample) -> dict[str, object]:
    return {
        "ts": iso(sample.ts),
        "bus_voltage": sample.bus_voltage,
        "battery_soc": sample.battery_soc,
        "attitude_err_deg": sample.attitude_err_deg,
        "wheel_rpm": sample.wheel_rpm,
        "temp_c": sample.temp_c,
        "comms_status": sample.comms_status,
        "fuel_kg": sample.fuel_kg,
        "in_eclipse": sample.in_eclipse,
        "load_w": sample.load_w,
    }


def state_dict(session: Session) -> dict[str, object]:
    mission = current_mission(session)
    moment = sim_now(session)
    clock = ensure_clock(session)
    samples = recent_samples(session, limit=240)
    clock_view = {"time_scale": clock.time_scale, "seed": clock.seed, "now": iso(moment)}
    diagnosis = diagnosis_of(session)
    window = current_pass(session)
    if mission is None:
        return {
            "mission": None,
            "now": iso(moment),
            "sample": None,
            "samples": [],
            "pass": pass_brief(window, moment),
            "options": [],
            "commands": [],
            "approvals": [],
            "lines": [],
            "diagnosis": None,
            "chain": chain_status(session),
            "clock": clock_view,
        }
    commands = session.scalars(
        select(Command).where(Command.mission_id == mission.id).order_by(Command.seq)
    ).all()
    findings = []
    if diagnosis is not None:
        findings = [
            {"subsystem": item.subsystem, "severity": item.severity, "detail": item.detail}
            for item in diagnosis.findings
        ]
    return {
        "mission": {
            "id": mission.id,
            "status": mission.status,
            "persistence": mission.persistence,
            "option_version": mission.option_version,
            "variant": mission.variant,
            "pass_number": mission.pass_number,
            "sat_id": mission.sat_id,
        },
        "now": iso(moment),
        "sample": None if not samples else sample_dict(samples[-1]),
        "samples": [sample_dict(item) for item in samples],
        "pass": pass_brief(window, moment),
        "options": [
            {
                "id": row.id,
                "key": row.key,
                "name": row.name,
                "version": row.version,
                "success_prob": row.success_prob,
                "power_cost": row.power_cost,
                "fuel_cost_kg": row.fuel_cost_kg,
                "fuel_reserve_pct": row.fuel_reserve_pct,
                "service_loss_h": row.service_loss_h,
                "reversible": row.reversible,
                "kind": row.kind,
                "rationale": row.rationale,
            }
            for row in latest_options(session)
        ],
        "commands": [
            {
                "id": row.id,
                "seq": row.seq,
                "option_id": row.option_id,
                "key": row.option_id.rsplit(":", 1)[-1],
                "step": row.step,
                "payload": row.payload,
                "status": row.status,
            }
            for row in commands
        ],
        "approvals": who_authorised(session, mission.id),
        "lines": room_lines(session, mission.id),
        "diagnosis": (
            None
            if diagnosis is None
            else {
                "severity": diagnosis.severity,
                "started_at": iso(diagnosis.started_at),
                "still_works": list(diagnosis.still_works),
                "findings": findings,
            }
        ),
        "chain": chain_status(session),
        "clock": clock_view,
    }
