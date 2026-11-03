"""The only writer that may set a command to transmitted."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.common.audit import append_event
from agents.common.gate import ApprovalView, GateDecision, GateRequest, transmit_allowed
from agents.common.models import Approval, Command
from agents.common.roles import parse_role
from agents.common.timeutil import as_utc

TRANSITIONS: dict[str, set[str]] = {
    "queued": {"awaiting_auth", "failed"},
    "awaiting_auth": {"transmitted", "failed"},
    "transmitted": {"confirmed", "failed"},
    "confirmed": set(),
    "failed": set(),
}


class TransitionError(ValueError):
    pass


def set_status(command: Command, status: str) -> None:
    if status == "transmitted":
        raise TransitionError("transmitted is only reachable through commit_transmit")
    allowed = TRANSITIONS.get(command.status, set())
    if status not in allowed:
        raise TransitionError(f"cannot move {command.status} to {status}")
    command.status = status


def option_public_id(mission_id: str, version: int, key: str) -> str:
    return f"{mission_id}:v{version}:{key}"


def views_for(session: Session, mission_id: str, option_key: str) -> list[ApprovalView]:
    rows = session.scalars(select(Approval).where(Approval.mission_id == mission_id)).all()
    found: list[ApprovalView] = []
    for row in rows:
        if row.option_id.rsplit(":", 1)[-1] != option_key:
            continue
        found.append(
            ApprovalView(
                approver=row.approver,
                role=parse_role(row.role),
                statement=row.statement,
                message_id=row.message_id,
                ts=as_utc(row.ts),
                option_key=option_key,
                option_version=row.option_version,
            )
        )
    return found


def record_approval(
    session: Session,
    *,
    mission_id: str,
    option_id: str,
    option_key: str,
    option_version: int,
    action: str,
    approver: str,
    role: str,
    message_id: str,
    statement: str,
    ts: datetime,
) -> Approval:
    row = Approval(
        mission_id=mission_id,
        option_id=option_id,
        action=action,
        approver=approver,
        role=role,
        message_id=message_id,
        statement=statement,
        ts=as_utc(ts),
        option_version=option_version,
    )
    session.add(row)
    append_event(
        session,
        mission_id,
        "approval.recorded",
        {
            "approver": approver,
            "role": role,
            "option_id": option_id,
            "option_key": option_key,
            "option_version": option_version,
            "message_id": message_id,
            "action": action,
        },
        ts=ts,
    )
    session.flush()
    return row


def commit_transmit(
    session: Session,
    command: Command,
    req: GateRequest,
    now: datetime,
) -> GateDecision:
    """Mark `command` transmitted only when the gate allows it and an approval row exists."""
    if command.status != "awaiting_auth":
        return GateDecision(False, f"command is {command.status}, not awaiting_auth")
    approvals = views_for(session, command.mission_id, req.option_key)
    decision = transmit_allowed(req, approvals, as_utc(now))
    if not decision.allowed:
        append_event(
            session,
            command.mission_id,
            "command.refused",
            {"command_id": command.id, "reason": decision.reason, "seq": command.seq},
            ts=now,
        )
        session.flush()
        return decision
    matching = [row for row in approvals if row.option_version == req.current_version]
    if not matching:
        return GateDecision(False, "Refused: no approval row for the current option version.")
    command.status = "transmitted"
    append_event(
        session,
        command.mission_id,
        "command.transmitted",
        {
            "command_id": command.id,
            "seq": command.seq,
            "option_key": req.option_key,
            "option_version": req.current_version,
            "primary_message_id": decision.primary_message_id,
            "second_message_id": decision.second_message_id,
            "reason": decision.reason,
        },
        ts=now,
    )
    session.flush()
    return decision
