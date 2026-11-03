"""Drive a live mission API until it reaches a terminal status."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from agents.common.irreversibility import command_statement

ROOT = Path(__file__).resolve().parents[1]
PRIYA_REJECT = "Option A is too slow. We cannot wait out a magnetorquer desat."
PRIYA_FUEL = "Request a fuel-saving variant of Option B."
PRIYA_CONFIRM = "Confirmed — Option B. Second operator confirmation."


def wait_api(base: str, timeout_s: float = 60) -> httpx.Client:
    client = httpx.Client(base_url=base, timeout=30)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if client.get("/health").status_code == 200:
                return client
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit(f"mission API did not answer at {base}")


def ensure_heartbeat(client: httpx.Client) -> None:
    """Start a local heartbeat and agent poller when nothing else is advancing the clock."""
    first = client.get("/api/state").json()
    time.sleep(6)
    second = client.get("/api/state").json()
    if (first.get("sample") or {}).get("ts") != (second.get("sample") or {}).get(
        "ts"
    ) and second.get("sample"):
        print("heartbeat already running")
        return
    if (first.get("now") != second.get("now")) and second.get("sample"):
        print("heartbeat already running")
        return
    print("no heartbeat detected; starting a local simulator and agent poller")

    def _sim() -> None:
        from telemetry.simulator import main as sim_main

        sim_main()

    def _agents() -> None:
        local = httpx.Client(base_url=str(client.base_url), timeout=60)
        while True:
            for path in ("/api/agents/context", "/api/agents/options", "/api/agents/action"):
                try:
                    local.post(path)
                except httpx.HTTPError:
                    pass
            time.sleep(1)

    threading.Thread(target=_sim, name="local-sim", daemon=True).start()
    threading.Thread(target=_agents, name="local-agents", daemon=True).start()


def transcript(state: dict[str, Any]) -> str:
    return "\n".join(str(line.get("text", "")) for line in state.get("lines", []))


def ingest(client: httpx.Client, author: str, text: str, message_id: str) -> None:
    response = client.post(
        "/api/ingest", json={"author": author, "text": text, "message_id": message_id}
    )
    response.raise_for_status()
    _mattermost(author, text)


def _mattermost(author: str, text: str) -> None:
    base = os.environ.get("MATTERMOST_URL", "http://127.0.0.1:8065").rstrip("/")
    username = (
        "priya"
        if author.lower().startswith("priya")
        else "arjun" if author.lower().startswith("arjun") else ""
    )
    if not username:
        return
    password = os.environ.get("MATTERMOST_USER_PASSWORD", "")
    channel = os.environ.get("MATTERMOST_CHANNEL_ID", "")
    if not password or not channel:
        return
    try:
        client = httpx.Client(timeout=10)
        login = client.post(
            f"{base}/api/v4/users/login", json={"login_id": username, "password": password}
        )
        login.raise_for_status()
        client.post(
            f"{base}/api/v4/posts",
            headers={"Authorization": f"Bearer {login.headers.get('Token', '')}"},
            json={"channel_id": channel, "message": text},
        )
    except httpx.HTTPError as exc:
        print(f"mattermost post skipped ({exc})")


def run_live(
    *, persistence: bool, humans: bool, time_scale: float, timeout_s: float
) -> dict[str, Any]:
    base = os.environ.get("MISSION_API_URL", "http://127.0.0.1:8090").rstrip("/")
    client = wait_api(base)
    created = client.post(
        "/api/reset",
        json={
            "persistence": persistence,
            "seed": int(os.environ.get("SEED", "7")),
            "time_scale": time_scale,
        },
    )
    created.raise_for_status()
    ensure_heartbeat(client)
    asked = False
    authed = False
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        state = client.get("/api/state").json()
        last = state
        text = transcript(state)
        sample = state.get("sample") or {}
        elapsed = _elapsed(str(sample.get("ts", "")))
        if humans and persistence and not asked and "OPTIONS v" in text and elapsed > 900:
            ingest(client, "Priya Raman", PRIYA_REJECT, "priya-reject")
            ingest(client, "Priya Raman", PRIYA_FUEL, "priya-fuel")
            asked = True
        if (
            humans
            and persistence
            and not authed
            and (state.get("pass") or {}).get("open")
            and "Fuel-saving" in text
        ):
            ingest(client, "Arjun Mehta", command_statement("B", 3), "arjun-auth")
            ingest(client, "Priya Raman", PRIYA_CONFIRM, "priya-confirm")
            authed = True
        status = (state.get("mission") or {}).get("status")
        if status in {"recovered", "lost"}:
            time.sleep(2)
            return client.get("/api/state").json()
        time.sleep(1)
    return last


def save_log(name: str, state: dict[str, Any]) -> Path:
    folder = ROOT / "logs"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def _elapsed(ts: str) -> float:
    if not ts:
        return 0.0
    from datetime import datetime

    moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    start = datetime.fromisoformat("2026-07-14T12:00:00+00:00")
    return (moment - start).total_seconds()
