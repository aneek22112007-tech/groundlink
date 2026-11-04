"""Thin process around one agent endpoint. Switch is optional; the API is not."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

from agents.common.adapters import fanout
from agents.common.switch_client import SwitchClient


def serve(kind: str) -> None:
    endpoint = {
        "context": "/api/agents/context",
        "options": "/api/agents/options",
        "action": "/api/agents/action",
    }[kind]
    base = os.environ.get("MISSION_API_URL", "http://127.0.0.1:8090").rstrip("/")
    port = os.environ.get("AGENT_HEALTH_PORT", "")
    if port:
        _start_health(int(port))
    switch, room_id = _switch(kind)
    incoming: queue.Queue[tuple[str, str, str]] = queue.Queue()
    if switch is not None and room_id:
        threading.Thread(
            target=_listen, args=(switch, room_id, incoming), name=f"{kind}-sse", daemon=True
        ).start()
    client = httpx.Client(timeout=60.0)
    while True:
        while not incoming.empty():
            author, text, message_id = incoming.get()
            try:
                client.post(
                    f"{base}/api/ingest",
                    json={"author": author, "text": text, "message_id": message_id},
                )
            except httpx.HTTPError:
                pass
        try:
            response = client.post(f"{base}{endpoint}")
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError:
            time.sleep(2)
            continue
        text = body.get("text")
        if isinstance(text, str) and text.strip():
            fanout(kind, text, client)
            if switch is not None and room_id:
                try:
                    switch.post_message(room_id, text)
                except httpx.HTTPError:
                    pass
        time.sleep(float(os.environ.get("AGENT_POLL_S", "1")))


def _listen(
    switch: SwitchClient, room_id: str, incoming: queue.Queue[tuple[str, str, str]]
) -> None:
    try:
        for message in switch.iter_messages(room_id):
            author = message.sender_name or message.sender or "unknown"
            incoming.put((author, message.body, message.message_id))
    except Exception:
        return


def _switch(kind: str) -> tuple[SwitchClient | None, str]:
    base = os.environ.get("SWITCH_BASE_URL", "").strip()
    if not base or os.environ.get("SWITCH_DISABLED", "").lower() in {"1", "true", "yes"}:
        return None, ""
    name = os.environ.get("AGENT_NAME", f"{kind}-agent")
    stored = _load_key(name)
    client = SwitchClient(
        base,
        name,
        api_key=stored.get("api_key", ""),
        agent_id=stored.get("agent_id", ""),
        registration_token=os.environ.get("AGENT_REGISTRATION_TOKEN", ""),
        persistence=os.environ.get("PERSISTENCE", "on").lower() not in {"0", "off", "false"},
    )
    try:
        client.register(
            {
                "context": "Reads the bus and writes the one-screen anomaly summary.",
                "options": "Proposes exactly three recovery options with reversibility tags.",
                "action": "Queues the chosen command and transmits it only after the gate.",
            }[kind]
        )
        if client.api_key:
            _save_key(name, client.agent_id, client.api_key)
        client.allow_anyone()
    except (httpx.HTTPError, RuntimeError, KeyError):
        if client.api_key:
            _save_key(name, client.agent_id, client.api_key)
        else:
            return None, ""
    room_id = os.environ.get("SWITCH_ROOM_ID", "") or _load_room()
    return client, room_id


def _key_path(name: str) -> Path:
    root = Path(os.environ.get("SWITCH_STATE_DIR", ".switch"))
    return root / "agents" / f"{name}.json"


def _load_key(name: str) -> dict[str, str]:
    path = _key_path(name)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"api_key": str(raw.get("api_key", "")), "agent_id": str(raw.get("agent_id", ""))}


def _save_key(name: str, agent_id: str, api_key: str) -> None:
    path = _key_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"agent_id": agent_id, "api_key": api_key, "name": name}),
        encoding="utf-8",
    )


def _load_room() -> str:
    path = Path(os.environ.get("SWITCH_STATE_DIR", ".switch")) / "room.json"
    if not path.exists():
        return ""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return str(raw.get("room_id", ""))


def _start_health(port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, format: str, *args: object) -> None:
            return

    thread = threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", port), Handler).serve_forever(),
        name="agent-health",
        daemon=True,
    )
    thread.start()
