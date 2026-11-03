"""Switch agent protocol: SSE in, HTTP out.

Custom agents take room events from `GET /agents/{id}/events` and post with
`POST /agents/{id}/message`. Heartbeats go to `POST /agents/{id}/connection/beat`.
See the Switch agent-connection docs. SSE is the contract this project implements.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RoomMessage:
    sequence: int | None
    room_id: str
    sender: str
    sender_name: str
    body: str
    message_id: str
    addressed: bool


def parse_sse(buffer: str) -> tuple[list[dict[str, str]], str]:
    """Pull complete SSE events out of a buffer. The remainder is incomplete."""
    events: list[dict[str, str]] = []
    while "\n\n" in buffer:
        block, buffer = buffer.split("\n\n", 1)
        event: dict[str, str] = {}
        data: list[str] = []
        for raw in block.split("\n"):
            line = raw.rstrip("\r")
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif line.startswith("id:"):
                event["id"] = line[3:].lstrip()
            elif line.startswith("event:"):
                event["event"] = line[6:].lstrip()
        if data:
            event["data"] = "\n".join(data)
        if event:
            events.append(event)
    return events, buffer


def message_from_event(event: dict[str, str]) -> RoomMessage | None:
    raw = event.get("data", "")
    if not raw:
        return None
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(frame, dict):
        return None
    body: Any = frame.get("data", frame)
    if isinstance(frame.get("event"), str) and frame["event"] not in {"message", ""}:
        return None
    if not isinstance(body, dict):
        return None
    kind = body.get("type") or frame.get("event") or event.get("event")
    if kind not in {None, "message"}:
        return None
    payload = body.get("payload", body)
    if not isinstance(payload, dict):
        return None
    text = payload.get("body") or payload.get("content") or ""
    if not isinstance(text, str) or not text.strip():
        return None
    sequence_raw = frame.get("id", event.get("id"))
    try:
        sequence = int(sequence_raw) if sequence_raw is not None else None
    except (TypeError, ValueError):
        sequence = None
    return RoomMessage(
        sequence=sequence,
        room_id=str(body.get("room_id", "")),
        sender=str(payload.get("sender", "")),
        sender_name=str(payload.get("sender_name") or payload.get("sender") or ""),
        body=text,
        message_id=str(payload.get("message_id") or sequence or ""),
        addressed=bool(payload.get("addressed", False)),
    )


class SwitchClient:
    """HTTP client for one registered GroundLink agent."""

    def __init__(
        self,
        base_url: str,
        agent_name: str,
        *,
        api_key: str = "",
        agent_id: str = "",
        registration_token: str = "",
        connection_id: str | None = None,
        persistence: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_name = agent_name
        self.api_key = api_key
        self.agent_id = agent_id
        self.registration_token = registration_token
        self.connection_id = connection_id or str(uuid.uuid5(uuid.NAMESPACE_DNS, agent_name))
        self.persistence = persistence
        self.cursor = 0
        self._stop = threading.Event()
        self._http = httpx.Client(timeout=httpx.Timeout(30.0, read=120.0))

    def close(self) -> None:
        self._stop.set()
        self._http.close()

    def _headers(self, token: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token if token is not None else self.api_key}"}

    def register(self, description: str) -> None:
        if self.api_key and self.agent_id:
            return
        response = self._http.post(
            f"{self.base_url}/agents",
            headers=self._headers(self.registration_token),
            json={
                "name": self.agent_name,
                "description": description,
                "connector_type": "groundlink",
                "integration_profile": {
                    "connection_model": "always_on",
                    "message_exchange": True,
                    "pre_invocation_mediation": [],
                    "post_invocation_mediation": [],
                    "event_reporting": [],
                },
            },
        )
        if response.status_code == 409:
            raise RuntimeError(
                f"{self.agent_name} is already registered. Put its api key in .switch/agents."
            )
        response.raise_for_status()
        body = response.json()
        self.agent_id = str(body["id"])
        self.api_key = str(body["api_key"])

    def call(self, operation: str, arguments: dict[str, Any]) -> Any:
        response = self._http.post(
            f"{self.base_url}/agents/{self.agent_id}/ops/{operation}",
            headers={**self._headers(), "X-Switch-Connection-Id": self.connection_id},
            json=arguments,
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict) and "result" in body:
            return body["result"]
        return body

    def allow_anyone(self) -> None:
        self.call("update_agent_detail", {"agent_id": self.agent_id, "addressing": "anyone"})

    def post_message(self, room_id: str, content: str) -> dict[str, Any]:
        response = self._http.post(
            f"{self.base_url}/agents/{self.agent_id}/message",
            headers=self._headers(),
            json={"room_id": room_id, "content": content},
        )
        if response.status_code == 404:
            result = self.call("post_message", {"room_id": room_id, "content": content})
            return result if isinstance(result, dict) else {"result": result}
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"ok": True}

    def read_context(self, room_id: str) -> str:
        if not self.persistence:
            return ""
        try:
            result = self.call("read_context", {"room_id": room_id})
        except httpx.HTTPError:
            return ""
        if isinstance(result, str):
            return result
        return json.dumps(result, sort_keys=True)

    def iter_messages(self, room_id: str) -> Iterator[RoomMessage]:
        beater = threading.Thread(
            target=self._beat_loop, name=f"{self.agent_name}-beat", daemon=True
        )
        beater.start()
        while not self._stop.is_set():
            try:
                yield from self._read_once(room_id)
            except httpx.HTTPError:
                if self._stop.is_set():
                    return
                time.sleep(2)

    def run(self, room_id: str, on_message: Callable[[RoomMessage], None]) -> None:
        for message in self.iter_messages(room_id):
            on_message(message)

    def _read_once(self, room_id: str) -> Iterator[RoomMessage]:
        params = {
            "connection_id": self.connection_id,
            "scope": "single",
            "filter": "all",
            "rooms": room_id,
            "start_from": str(self.cursor) if self.cursor else "head",
            "client": "groundlink",
            "client_version": "1.0.0",
        }
        buffer = ""
        with self._http.stream(
            "GET",
            f"{self.base_url}/agents/{self.agent_id}/events",
            params=params,
            headers={**self._headers(), "Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_text():
                if self._stop.is_set():
                    return
                buffer += chunk
                events, buffer = parse_sse(buffer)
                for event in events:
                    message = message_from_event(event)
                    if message is None:
                        continue
                    if message.sequence is not None:
                        self.cursor = max(self.cursor, message.sequence)
                    yield message

    def _beat_loop(self) -> None:
        while not self._stop.is_set():
            if self.agent_id and self.api_key:
                try:
                    self._http.post(
                        f"{self.base_url}/agents/{self.agent_id}/connection/beat",
                        headers=self._headers(),
                        json={"connection_id": self.connection_id, "cursor": self.cursor},
                    )
                except httpx.HTTPError:
                    pass
            self._stop.wait(2.0)
