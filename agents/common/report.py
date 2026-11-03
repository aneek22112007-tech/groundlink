"""Post-incident report. The markdown is the insurer copy; the PDF is the same text."""

from __future__ import annotations

import json

from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.common.audit import load_chain, verify_chain
from agents.common.mission_service import (
    audit_link,
    chain_status,
    room_lines,
    who_authorised,
)
from agents.common.models import Command, Mission, Option


def render_markdown(session: Session, mission: Mission, *, base_url: str) -> str:
    options = session.scalars(
        select(Option).where(Option.mission_id == mission.id).order_by(Option.version, Option.key)
    ).all()
    commands = session.scalars(
        select(Command).where(Command.mission_id == mission.id).order_by(Command.seq)
    ).all()
    ok, detail = verify_chain(load_chain(session))
    lines = room_lines(session, mission.id)
    approvals = who_authorised(session, mission.id)
    authorisers = [row for row in approvals if row["action"] == "authorise"]
    who = authorisers[-1]["approver"] if authorisers else "nobody"
    option_id = authorisers[-1]["option_id"] if authorisers else "n/a"
    parts = [
        f"# Kestrel-7 post-incident report ({mission.id})",
        "",
        f"Status: **{mission.status}**. Persistence: **{'on' if mission.persistence else 'off'}**.",
        f"Who authorised this burn? **{who}** on `{option_id}`.",
        f"Audit link: {audit_link(mission.id, base_url)}",
        "",
        "## Decision trail",
        "",
    ]
    for line in lines:
        parts.append(f"- `{line['ts']}` **{line['who']}** ({line['role']}): {line['text']}")
    parts.extend(["", "## Options", ""])
    for option in options:
        tag = "REVERSIBLE" if option.reversible else "IRREVERSIBLE"
        parts.append(
            f"- v{option.version} {option.key} {option.name} [{tag}] "
            f"P={option.success_prob:.3f} fuel={option.fuel_cost_kg:.3f} kg "
            f"power={option.power_cost:.1f} Wh service_loss={option.service_loss_h:.2f} h"
        )
    parts.extend(["", "## Commands", ""])
    for command in commands:
        parts.append(
            f"- seq {command.seq} {command.step} status={command.status} option={command.option_id}"
        )
    parts.extend(["", "## Approvals", ""])
    if not approvals:
        parts.append("No approval row was stored.")
    for approval in approvals:
        parts.append(
            f"- {approval['ts']} {approval['approver']} ({approval['role']}) "
            f"{approval['action']}: {approval['statement']}"
        )
    chain = chain_status(session)
    parts.extend(
        [
            "",
            "## Hash chain",
            "",
            f"Verified: {ok}. {detail}. Events: {chain['length']}.",
            "",
            "Each event stores sha256(previous hash + canonical row). "
            "A changed payload breaks the chain.",
            "",
        ]
    )
    return "\n".join(parts)


def render_pdf(markdown: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    safe = (
        markdown.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2212", "-")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )
    pdf.multi_cell(0, 5, safe)
    raw = pdf.output()
    return bytes(raw)


def event_payloads(session: Session, mission_id: str) -> list[dict[str, object]]:
    rows = []
    for row in load_chain(session):
        if row.mission_id != mission_id:
            continue
        rows.append(
            {
                "id": row.id,
                "kind": row.kind,
                "ts": row.ts.isoformat(),
                "hash": row.row_hash,
                "prev": row.prev_hash,
                "payload": json.loads(row.payload_json),
            }
        )
    return rows
