"""One pass of each agent against the mission database.

The HTTP handlers and the live processes call these functions. Transmission
still goes through `try_transmit_all`, which is the only caller of
`commit_transmit`.
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.action_agent.decide import conflicting_keys
from agents.action_agent.sequence import checkpoint
from agents.common.llm import narrate
from agents.common.mission_service import (
    current_mission,
    current_pass,
    latest_options,
    log_room,
    month_incidents,
    propose,
    queue_option,
    recent_samples,
    room_lines,
    sim_now,
    try_transmit_all,
)
from agents.common.models import Command
from agents.context_agent.decide import should_post_context
from agents.context_agent.summary import render_summary
from agents.options_agent.decide import proposal_request
from agents.options_agent.propose import render_options
from core.diagnosis import diagnose


def _public_base() -> str:
    return os.environ.get("DASHBOARD_PUBLIC_URL", "http://localhost:8090").rstrip("/")


def _has(session: Session, mission_id: str, who: str, text: str) -> bool:
    for line in room_lines(session, mission_id):
        if line.get("who") == who and line.get("text") == text:
            return True
    return False


def _say(session: Session, mission_id: str, who: str, role: str, text: str) -> str | None:
    spoken = narrate(text, purpose=role)
    if _has(session, mission_id, who, spoken):
        return None
    log_room(session, who, role, spoken, "")
    return spoken


def run_context(session: Session) -> str | None:
    mission = current_mission(session)
    if mission is None or mission.status in {"recovered", "lost", "closed"}:
        return None
    samples = recent_samples(session, limit=30)
    if not samples:
        return None
    sample = samples[-1]
    lines = room_lines(session, mission.id)
    if not should_post_context(lines, sample, mission.persistence):
        return None
    incidents: list[dict[str, str]] = []
    if mission.persistence:
        incidents = [
            {"id": row.id, "title": row.title} for row in month_incidents(session, sample.ts)
        ]
    text = render_summary(
        sample,
        diagnose(samples),
        sat_name="Kestrel-7",
        window=current_pass(session),
        incidents=incidents,
        persistence=mission.persistence,
        dashboard_url=_public_base(),
    )
    if mission.status == "open":
        mission.status = "diagnosing"
    return _say(session, mission.id, "Context", "context_agent", text)


def run_options(session: Session) -> str | None:
    mission = current_mission(session)
    if mission is None or mission.status in {"recovered", "lost", "closed", "executing"}:
        return None
    if not recent_samples(session, limit=1):
        return None
    lines = room_lines(session, mission.id)
    rows = latest_options(session)
    request = proposal_request(
        lines,
        [row.name for row in rows],
        persistence=mission.persistence,
        current_version=mission.option_version,
    )
    if request is None:
        return None
    version, variant = request
    specs = propose(session, variant, version)
    return _say(session, mission.id, "Options", "options_agent", render_options(specs))


def run_action(session: Session) -> str | None:
    mission = current_mission(session)
    if mission is None:
        return None
    spoken: list[str] = []
    if not mission.persistence:
        queued = _queued_keys(session, mission.id)
        for key in conflicting_keys(room_lines(session, mission.id), queued, persistence=False):
            queue_option(session, key)
    window = current_pass(session)
    moment = sim_now(session)
    if (
        window is not None
        and window.contains(moment)
        and mission.status not in {"lost", "recovered", "closed"}
    ):
        samples = recent_samples(session, limit=2)
        previous = samples[-2].attitude_err_deg if len(samples) > 1 else None
        current_err = samples[-1].attitude_err_deg if samples else 0.0
        for item in try_transmit_all(session):
            if not item.get("allowed"):
                continue
            verdict = checkpoint(str(item.get("step", "")), current_err, previous)
            line = (
                f"TRANSMITTED seq {item['seq']} {item['step']} "
                f"{item.get('payload', '')} ({verdict})"
            )
            posted = _say(session, mission.id, "Action", "action_agent", line)
            if posted:
                spoken.append(posted)
            if verdict == "rollback":
                note = "ROLLBACK: attitude error grew after the pulse. Hold the next step."
                posted_note = _say(session, mission.id, "Action", "action_agent", note)
                if posted_note:
                    spoken.append(posted_note)
    session.refresh(mission)
    samples = recent_samples(session, limit=1)
    if mission.status == "recovered" and samples:
        sample = samples[-1]
        line = (
            f"CONFIRMED recovered. Attitude error {sample.attitude_err_deg:.2f} deg, "
            f"bus {sample.bus_voltage:.2f} V, fuel {sample.fuel_kg:.3f} kg."
        )
        posted = _say(session, mission.id, "Action", "action_agent", line)
        if posted:
            spoken.append(posted)
    if mission.status == "lost":
        line = "No authorisation on record. Bus crossed the survival floor. Mission lost."
        posted = _say(session, mission.id, "Action", "action_agent", line)
        if posted:
            spoken.append(posted)
    if not spoken:
        return None
    return "\n".join(spoken)


def _queued_keys(session: Session, mission_id: str) -> set[str]:
    rows = session.scalars(select(Command).where(Command.mission_id == mission_id)).all()
    return {row.option_id.rsplit(":", 1)[-1] for row in rows}
