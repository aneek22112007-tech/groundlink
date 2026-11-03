"""FastAPI mission API. This process is the only database writer besides Alembic."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.common.db import create_all, database_url, session_scope
from agents.common.mission_service import (
    confirm_if_recovered,
    current_mission,
    ingest_human,
    record_telemetry,
    reset_run,
    seed_reference,
)
from agents.common.models import Incident, Mission
from agents.common.report import render_markdown, render_pdf
from agents.common.timeutil import as_utc
from agents.common.view import state_dict
from agents.orchestration import run_action, run_context, run_options
from core.types import Sample

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))


class ResetIn(BaseModel):
    persistence: bool = True
    seed: int = 7
    time_scale: float = 20.0


class SampleIn(BaseModel):
    ts: str
    bus_voltage: float
    battery_soc: float
    attitude_err_deg: float
    wheel_rpm: float
    temp_c: float
    comms_status: str
    fuel_kg: float = 0.0
    in_eclipse: bool = False
    load_w: float = 0.0


class IngestIn(BaseModel):
    author: str
    text: str
    message_id: str = ""


def _parse_ts(value: str) -> datetime:
    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _sample(body: SampleIn) -> Sample:
    return Sample(
        ts=_parse_ts(body.ts),
        bus_voltage=body.bus_voltage,
        battery_soc=body.battery_soc,
        attitude_err_deg=body.attitude_err_deg,
        wheel_rpm=body.wheel_rpm,
        temp_c=body.temp_c,
        comms_status=body.comms_status,
        fuel_kg=body.fuel_kg,
        in_eclipse=body.in_eclipse,
        load_w=body.load_w,
    )


def _base() -> str:
    return os.environ.get("DASHBOARD_PUBLIC_URL", "http://localhost:8090")


def create_app(url: str | None = None) -> FastAPI:
    application = FastAPI(title="GroundLink", version="1.0.0")
    application.state.factory = create_all(url or database_url())
    with session_scope(application.state.factory) as session:
        seed_reference(session)

    def db() -> Iterator[Session]:
        with session_scope(application.state.factory) as session:
            yield session

    static_dir = ROOT / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @application.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @application.get("/api/state")
    def api_state(session: Session = Depends(db)) -> dict[str, object]:
        return state_dict(session)

    @application.post("/api/reset")
    def api_reset(body: ResetIn, session: Session = Depends(db)) -> dict[str, object]:
        mission = reset_run(
            session, persistence=body.persistence, seed=body.seed, time_scale=body.time_scale
        )
        return {"mission_id": mission.id, "persistence": mission.persistence}

    @application.post("/api/telemetry")
    def api_telemetry(body: SampleIn, session: Session = Depends(db)) -> dict[str, object]:
        sample = _sample(body)
        record_telemetry(session, sample)
        recovered = confirm_if_recovered(session, sample)
        mission = current_mission(session)
        return {
            "status": None if mission is None else mission.status,
            "recovered": recovered,
            "ts": body.ts,
        }

    @application.post("/api/ingest")
    def api_ingest(body: IngestIn, session: Session = Depends(db)) -> dict[str, object]:
        return ingest_human(session, body.author, body.text, body.message_id)

    @application.post("/api/agents/context")
    def api_context(session: Session = Depends(db)) -> dict[str, object]:
        text = run_context(session)
        return {"posted": text is not None, "text": text}

    @application.post("/api/agents/options")
    def api_options(session: Session = Depends(db)) -> dict[str, object]:
        text = run_options(session)
        return {"posted": text is not None, "text": text}

    @application.post("/api/agents/action")
    def api_action(session: Session = Depends(db)) -> dict[str, object]:
        text = run_action(session)
        return {"posted": text is not None, "text": text}

    @application.get("/api/audit/{mission_id}")
    def api_audit(mission_id: str, session: Session = Depends(db)) -> dict[str, object]:
        mission = session.get(Mission, mission_id)
        if mission is None:
            raise HTTPException(404, "mission not found")
        return {
            "mission_id": mission.id,
            "status": mission.status,
            "markdown": render_markdown(session, mission, base_url=_base()),
        }

    @application.get("/api/report/{mission_id}.md")
    def api_report_md(mission_id: str, session: Session = Depends(db)) -> Response:
        mission = session.get(Mission, mission_id)
        if mission is None:
            raise HTTPException(404, "mission not found")
        body = render_markdown(session, mission, base_url=_base())
        return Response(content=body, media_type="text/markdown")

    @application.get("/api/report/{mission_id}.pdf")
    def api_report_pdf(mission_id: str, session: Session = Depends(db)) -> Response:
        mission = session.get(Mission, mission_id)
        if mission is None:
            raise HTTPException(404, "mission not found")
        markdown = render_markdown(session, mission, base_url=_base())
        return Response(content=render_pdf(markdown), media_type="application/pdf")

    @application.get("/", response_class=HTMLResponse)
    def home(request: Request, session: Session = Depends(db)) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "index.html", {"request": request, "state": state_dict(session)}
        )

    @application.get("/partials/board", response_class=HTMLResponse)
    def board(request: Request, session: Session = Depends(db)) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "board.html", {"request": request, "state": state_dict(session)}
        )

    @application.get("/audit/{mission_id}", response_class=HTMLResponse)
    def audit_page(
        mission_id: str, request: Request, session: Session = Depends(db)
    ) -> HTMLResponse:
        mission = session.get(Mission, mission_id)
        if mission is None:
            raise HTTPException(404, "mission not found")
        return templates.TemplateResponse(
            request,
            "audit.html",
            {
                "request": request,
                "mission": mission,
                "markdown": render_markdown(session, mission, base_url=_base()),
            },
        )

    @application.get("/incidents/{incident_id}", response_class=HTMLResponse)
    def incident_page(
        incident_id: str, request: Request, session: Session = Depends(db)
    ) -> HTMLResponse:
        row = session.get(Incident, incident_id)
        if row is None:
            raise HTTPException(404, "incident not found")
        return templates.TemplateResponse(
            request, "incident.html", {"request": request, "incident": row}
        )

    return application


app = create_app()
