"""Append-only hash chain. Each row stores sha256(prev_hash + canonical row)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.common.models import Event
from agents.common.timeutil import as_utc, iso, utcnow

GENESIS = "0" * 64


def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return iso(value)
    raise TypeError(f"not serialisable: {type(value).__name__}")


def link_hash(prev_hash: str, material: dict[str, Any]) -> str:
    raw = (prev_hash + canonical(material)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _material(
    mission_id: str, kind: str, ts: datetime, payload_json: str, prev_hash: str
) -> dict[str, Any]:
    return {
        "kind": kind,
        "mission_id": mission_id,
        "payload": payload_json,
        "prev_hash": prev_hash,
        "ts": iso(ts),
    }


def append_event(
    session: Session,
    mission_id: str,
    kind: str,
    payload: dict[str, Any],
    ts: datetime | None = None,
) -> Event:
    moment = as_utc(ts or utcnow())
    payload_json = canonical(payload)
    last = session.scalar(select(Event).order_by(Event.id.desc()).limit(1))
    prev = last.row_hash if last is not None else GENESIS
    digest = link_hash(prev, _material(mission_id, kind, moment, payload_json, prev))
    row = Event(
        mission_id=mission_id,
        kind=kind,
        ts=moment,
        payload_json=payload_json,
        prev_hash=prev,
        row_hash=digest,
    )
    session.add(row)
    session.flush()
    return row


def verify_chain(rows: list[Event]) -> tuple[bool, str]:
    prev = GENESIS
    for row in rows:
        expect = link_hash(
            prev, _material(row.mission_id, row.kind, as_utc(row.ts), row.payload_json, prev)
        )
        if row.prev_hash != prev or row.row_hash != expect:
            return False, f"chain break at event {row.id}"
        prev = row.row_hash
    return True, "chain intact"


def load_chain(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.id.asc())))
