from __future__ import annotations

from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

from agents.common.gate import (
    ApprovalView,
    GateRequest,
    review_attempt,
    transmit_allowed,
)
from agents.common.irreversibility import command_statement
from agents.common.models import Command, Mission
from agents.common.roles import Role
from agents.common.transmit import commit_transmit, option_public_id, record_approval, set_status
from tests.conftest import AOS, LOS, T0


def _req(reversible: bool, version: int = 2) -> GateRequest:
    return GateRequest(
        reversible=reversible,
        option_key="B" if not reversible else "C",
        current_version=version,
        pass_number=3,
        window_aos=AOS,
        window_los=LOS,
    )


def _view(
    approver: str,
    role: Role,
    statement: str,
    when: object,
    version: int = 2,
    key: str = "B",
    message_id: str = "m1",
) -> ApprovalView:
    return ApprovalView(approver, role, statement, message_id, when, key, version)  # type: ignore[arg-type]


def test_reversible_accepts_either_operator_and_refuses_observer() -> None:
    req = _req(True)
    priya = review_attempt(
        "Approved Option C",
        approver="priya",
        role=Role.FLIGHT_OPS_ENGINEER,
        moment=AOS + timedelta(minutes=1),
        req=req,
    )
    assert priya.store is True and priya.refusal is False
    guest = review_attempt(
        "Approved Option C",
        approver="guest",
        role=Role.OBSERVER,
        moment=AOS + timedelta(minutes=1),
        req=req,
    )
    assert guest.refusal is True
    assert "observer" in guest.reason


def test_reversible_refuses_after_the_window() -> None:
    req = _req(True)
    late = review_attempt(
        "Approved Option C",
        approver="arjun",
        role=Role.MISSION_DIRECTOR,
        moment=LOS + timedelta(seconds=1),
        req=req,
    )
    assert late.refusal is True
    assert "after the pass window" in late.reason


def test_irreversible_requires_the_statement_the_director_and_a_second_person() -> None:
    req = _req(False)
    text = command_statement("B", 3)
    during = AOS + timedelta(minutes=2)
    foe = review_attempt(
        text, approver="priya", role=Role.FLIGHT_OPS_ENGINEER, moment=during, req=req
    )
    assert foe.refusal is True
    assert "mission_director" in foe.reason

    early = review_attempt(text, approver="arjun", role=Role.MISSION_DIRECTOR, moment=T0, req=req)
    assert early.refusal is True
    assert "before the pass window" in early.reason

    primary = review_attempt(
        text, approver="arjun", role=Role.MISSION_DIRECTOR, moment=during, req=req
    )
    assert primary.store is True

    missing = review_attempt(
        "Authorized Option B please",
        approver="arjun",
        role=Role.MISSION_DIRECTOR,
        moment=during,
        req=req,
    )
    assert missing.refusal is True
    assert "command-responsibility" in missing.reason

    stale = review_attempt(
        text + " v1",
        approver="arjun",
        role=Role.MISSION_DIRECTOR,
        moment=during,
        req=req,
    )
    assert stale.refusal is True
    assert "version 1" in stale.reason

    confirm = review_attempt(
        "Confirmed — Option B. Second operator confirmation.",
        approver="priya",
        role=Role.FLIGHT_OPS_ENGINEER,
        moment=during + timedelta(seconds=5),
        req=req,
    )
    assert confirm.store is True

    approvals = [
        _view("arjun", Role.MISSION_DIRECTOR, text, during, message_id="md"),
        _view(
            "priya",
            Role.FLIGHT_OPS_ENGINEER,
            "Confirmed — Option B. Second operator confirmation.",
            during + timedelta(seconds=5),
            message_id="foe",
        ),
    ]
    decision = transmit_allowed(req, approvals, during + timedelta(seconds=6))
    assert decision.allowed is True
    assert decision.primary_message_id == "md"
    assert decision.second_message_id == "foe"

    alone = transmit_allowed(req, approvals[:1], during)
    assert alone.allowed is False
    assert "second" in alone.reason.casefold()

    self_confirm = [
        approvals[0],
        _view("arjun", Role.MISSION_DIRECTOR, "Confirmed Option B", during, message_id="self"),
    ]
    assert transmit_allowed(req, self_confirm, during).allowed is False


def test_stale_rows_do_not_transmit() -> None:
    req = _req(False, version=3)
    during = AOS + timedelta(minutes=1)
    old = _view(
        "arjun",
        Role.MISSION_DIRECTOR,
        command_statement("B", 3),
        during,
        version=2,
    )
    decision = transmit_allowed(req, [old], during)
    assert decision.allowed is False
    assert "version 2" in decision.reason


def test_commit_transmit_writes_a_row_and_blocks_the_shortcut(factory) -> None:  # type: ignore[no-untyped-def]
    session = factory()
    mission = Mission(
        id="m1",
        sat_id="kestrel-7",
        status="deciding",
        opened=T0,
        pass_number=3,
        option_version=2,
    )
    session.add(mission)
    option_id = option_public_id("m1", 2, "B")
    command = Command(
        id="c1",
        seq=1,
        mission_id="m1",
        option_id=option_id,
        step="fire",
        payload="{}",
        status="queued",
    )
    session.add(command)
    session.flush()
    try:
        set_status(command, "transmitted")
        raised = False
    except Exception:
        raised = True
    assert raised is True
    set_status(command, "awaiting_auth")
    during = AOS + timedelta(minutes=1)
    req = _req(False)
    blocked = commit_transmit(session, command, req, during)
    assert blocked.allowed is False
    assert command.status == "awaiting_auth"
    record_approval(
        session,
        mission_id="m1",
        option_id=option_id,
        option_key="B",
        option_version=2,
        action="authorise",
        approver="arjun",
        role=Role.MISSION_DIRECTOR.value,
        message_id="md",
        statement=command_statement("B", 3),
        ts=during,
    )
    still = commit_transmit(session, command, req, during)
    assert still.allowed is False
    record_approval(
        session,
        mission_id="m1",
        option_id=option_id,
        option_key="B",
        option_version=2,
        action="confirm",
        approver="priya",
        role=Role.FLIGHT_OPS_ENGINEER.value,
        message_id="foe",
        statement="Confirmed — Option B. Second operator confirmation.",
        ts=during + timedelta(seconds=2),
    )
    done = commit_transmit(session, command, req, during + timedelta(seconds=3))
    assert done.allowed is True
    assert command.status == "transmitted"
    session.close()


@given(
    role=st.sampled_from(list(Role)),
    when=st.sampled_from(["before", "during", "after"]),
    kind=st.sampled_from(["exact", "confirm", "vague"]),
    with_second=st.booleans(),
    second_same=st.booleans(),
    version_tag=st.sampled_from([None, 2, 9]),
)
def test_property_transmit_implies_a_valid_approval_set(
    role: Role,
    when: str,
    kind: str,
    with_second: bool,
    second_same: bool,
    version_tag: int | None,
) -> None:
    req = _req(False)
    moment = {
        "before": T0,
        "during": AOS + timedelta(minutes=1),
        "after": LOS + timedelta(minutes=1),
    }[when]
    statement = command_statement("B", 3)
    if kind == "confirm":
        statement = "Confirmed Option B"
    elif kind == "vague":
        statement = "looks fine to me, Option B"
    if version_tag is not None:
        statement = f"{statement} v{version_tag}"
    attempt = review_attempt(statement, approver="arjun", role=role, moment=moment, req=req)
    stored: list[ApprovalView] = []
    if attempt.store:
        stored.append(_view("arjun", role, statement, moment))
    if with_second:
        second_approver = "arjun" if second_same else "priya"
        second_role = Role.FLIGHT_OPS_ENGINEER
        second_text = "Confirmed Option B"
        second = review_attempt(
            second_text,
            approver=second_approver,
            role=second_role,
            moment=moment,
            req=req,
        )
        if second.store:
            stored.append(_view(second_approver, second_role, second_text, moment, message_id="m2"))
    decision = transmit_allowed(
        req, stored, moment if when == "during" else AOS + timedelta(minutes=3)
    )
    if decision.allowed:
        assert stored
        assert any(
            row.role == Role.MISSION_DIRECTOR
            and "taking command responsibility" in row.statement.casefold()
            or "taking command responsibility" in row.statement
            for row in stored
        )
        primaries = [row for row in stored if row.role == Role.MISSION_DIRECTOR]
        assert primaries
        assert any(row.approver != primaries[-1].approver for row in stored)
        assert all(row.option_version == req.current_version for row in stored)
        assert when == "during"
