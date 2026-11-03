"""Human gate. A command reaches transmitted only through `commit_transmit`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agents.common.irreversibility import (
    is_confirmation,
    mentions_option,
    stated_version,
    statement_matches,
)
from agents.common.roles import (
    IRREVERSIBLE_PRIMARY,
    REVERSIBLE_ROLES,
    SECOND_ROLES,
    Role,
)


@dataclass(frozen=True)
class ApprovalView:
    approver: str
    role: Role
    statement: str
    message_id: str
    ts: datetime
    option_key: str
    option_version: int


@dataclass(frozen=True)
class GateRequest:
    reversible: bool
    option_key: str
    current_version: int
    pass_number: int
    window_aos: datetime | None
    window_los: datetime | None


@dataclass(frozen=True)
class AttemptResult:
    """What to do with one human message."""

    store: bool
    refusal: bool
    reason: str
    binds_version: int | None = None


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    primary_message_id: str | None = None
    second_message_id: str | None = None


def _window_ok(moment: datetime, req: GateRequest) -> bool:
    if req.window_aos is None or req.window_los is None:
        return False
    return req.window_aos <= moment <= req.window_los


def _stale_reason(text: str, req: GateRequest) -> str | None:
    stated = stated_version(text)
    if stated is not None and stated != req.current_version:
        return (
            f"Refused: approval refers to option version {stated}; "
            f"current version is {req.current_version}."
        )
    return None


def _outside_reason(moment: datetime, req: GateRequest) -> str | None:
    if req.window_aos is None or req.window_los is None:
        return "Refused: no pass window is on record."
    if moment > req.window_los:
        return (
            "Refused: approval came after the pass window closed "
            f"({req.window_los.isoformat()})."
        )
    if moment < req.window_aos:
        return (
            "Refused: approval came before the pass window opened "
            f"({req.window_aos.isoformat()})."
        )
    return None


def review_attempt(
    text: str,
    *,
    approver: str,
    role: Role,
    moment: datetime,
    req: GateRequest,
) -> AttemptResult:
    """Accept, refuse, or ignore one message. Refusal is posted back to the thread."""
    stale = _stale_reason(text, req)
    if stale is not None:
        return AttemptResult(False, True, stale, None)

    if req.reversible:
        return _review_reversible(text, role, moment, req)
    return _review_irreversible(text, approver, role, moment, req)


def _review_reversible(text: str, role: Role, moment: datetime, req: GateRequest) -> AttemptResult:
    if not mentions_option(text, req.option_key):
        return AttemptResult(False, False, "not an approval for this option")
    if role == Role.OBSERVER or role not in REVERSIBLE_ROLES:
        return AttemptResult(
            False,
            True,
            f"Refused: {role.value} cannot authorise a command. "
            "Need flight_ops_engineer or mission_director.",
        )
    if req.window_los is not None and moment > req.window_los:
        return AttemptResult(
            False,
            True,
            "Refused: approval came after the pass window closed "
            f"({req.window_los.isoformat()}).",
        )
    return AttemptResult(
        True,
        False,
        "Approval recorded. Transmission waits for an open pass window.",
        req.current_version,
    )


def _review_irreversible(
    text: str,
    approver: str,
    role: Role,
    moment: datetime,
    req: GateRequest,
) -> AttemptResult:
    del approver
    outside = _outside_reason(moment, req)
    confirming = is_confirmation(text, req.option_key)
    primary = statement_matches(text, req.option_key, req.pass_number)

    if not primary and not confirming and not mentions_option(text, req.option_key):
        return AttemptResult(False, False, "not an approval for this option")

    if role == Role.OBSERVER:
        return AttemptResult(False, True, "Refused: observer cannot authorise a command.")

    if outside is not None and (primary or confirming or mentions_option(text, req.option_key)):
        return AttemptResult(False, True, outside)

    if primary:
        if role not in IRREVERSIBLE_PRIMARY:
            return AttemptResult(
                False,
                True,
                "Refused: irreversible command requires mission_director, " f"not {role.value}.",
            )
        return AttemptResult(
            True,
            False,
            "Mission-director statement recorded. A second operator must confirm.",
            req.current_version,
        )

    if confirming:
        if role not in SECOND_ROLES:
            return AttemptResult(
                False,
                True,
                f"Refused: {role.value} cannot confirm an irreversible command.",
            )
        return AttemptResult(
            True,
            False,
            "Second-operator confirmation recorded.",
            req.current_version,
        )

    if role not in IRREVERSIBLE_PRIMARY:
        return AttemptResult(
            False,
            True,
            "Refused: irreversible command requires mission_director, "
            f"not {role.value}, plus the command-responsibility statement.",
        )
    return AttemptResult(
        False,
        True,
        "Refused: missing the command-responsibility statement "
        f"for Option {req.option_key} on pass {req.pass_number}.",
    )


def transmit_allowed(
    req: GateRequest,
    approvals: list[ApprovalView],
    now: datetime,
) -> GateDecision:
    """Whether this command may be marked transmitted at `now`."""
    current = [
        row
        for row in approvals
        if row.option_key == req.option_key and row.option_version == req.current_version
    ]
    stale = [
        row
        for row in approvals
        if row.option_key == req.option_key and row.option_version != req.current_version
    ]
    if not current and stale:
        version = stale[-1].option_version
        return GateDecision(
            False,
            "Refused: approval refers to option version "
            f"{version}; current version is {req.current_version}.",
        )
    if req.window_aos is None or req.window_los is None:
        return GateDecision(False, "Refused: no pass window is on record.")
    if now > req.window_los:
        return GateDecision(False, "Refused: the pass window has closed.")
    if now < req.window_aos:
        return GateDecision(False, "Pass window is not open yet.")

    if req.reversible:
        good = [row for row in current if row.role in REVERSIBLE_ROLES and row.ts <= req.window_los]
        if not good:
            return GateDecision(False, "No valid approval on record.")
        return GateDecision(True, "Reversible command authorised.", good[-1].message_id, None)

    primaries = [
        row
        for row in current
        if row.role in IRREVERSIBLE_PRIMARY
        and statement_matches(row.statement, req.option_key, req.pass_number)
        and _window_ok(row.ts, req)
    ]
    if not primaries:
        return GateDecision(False, "No mission-director statement on record for this version.")
    primary = primaries[-1]
    seconds = [
        row
        for row in current
        if row.approver != primary.approver
        and row.role in SECOND_ROLES
        and is_confirmation(row.statement, req.option_key)
        and _window_ok(row.ts, req)
    ]
    if not seconds:
        return GateDecision(
            False,
            "Waiting for a second operator to confirm.",
            primary.message_id,
            None,
        )
    second = seconds[-1]
    return GateDecision(
        True,
        "Irreversible command authorised.",
        primary.message_id,
        second.message_id,
    )
