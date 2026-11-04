"""Register the three agents and try to open the Kestrel-7 room.

create_room is attempted through the agent op catalogue. If this Switch build
rejects it, the script writes what it learned and exits 0 so the rest of the
stack can still boot. Human accounts are created in Mattermost when it answers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
AGENTS = (
    ("context-agent", "Reads the bus and writes the one-screen anomaly summary."),
    ("options-agent", "Proposes exactly three recovery options with reversibility tags."),
    ("action-agent", "Queues commands and transmits them only after the gate."),
)


def _load_env() -> None:
    from scripts.envfile import load_env

    load_env()


def main() -> None:
    _load_env()
    from scripts.envfile import switch_url

    base = switch_url()
    token = os.environ.get("AGENT_REGISTRATION_TOKEN", "")
    state = Path(os.environ.get("SWITCH_STATE_DIR", str(ROOT / ".switch")))
    state.mkdir(parents=True, exist_ok=True)
    if not token:
        print("AGENT_REGISTRATION_TOKEN is empty; skipping Switch registration")
        return
    from agents.common.switch_client import SwitchClient

    room_id = ""
    for name, description in AGENTS:
        client = SwitchClient(base, name, registration_token=token)
        try:
            client.register(description)
            client.allow_anyone()
        except (httpx.HTTPError, RuntimeError) as exc:
            print(f"{name}: register failed ({exc})")
            continue
        (state / "agents").mkdir(exist_ok=True)
        (state / "agents" / f"{name}.json").write_text(
            json.dumps({"agent_id": client.agent_id, "api_key": client.api_key, "name": name}),
            encoding="utf-8",
        )
        print(f"registered {name} as {client.agent_id}")
        if room_id:
            continue
        for operation, arguments in (
            ("create_room", {"name": "Kestrel-7", "topic": "anomaly response"}),
            (
                "create_room_from_yaml",
                {"yaml": (ROOT / "room_templates" / "mission_room.yaml").read_text()},
            ),
        ):
            try:
                result = client.call(operation, arguments)
            except httpx.HTTPError:
                continue
            if isinstance(result, dict):
                room_id = str(result.get("room_id") or result.get("id") or "")
            if room_id:
                print(f"room {room_id} via {operation}")
                break
    (state / "room.json").write_text(json.dumps({"room_id": room_id}), encoding="utf-8")
    _mattermost()


def _mattermost() -> None:
    from scripts.envfile import mattermost_url

    base = mattermost_url()
    admin = os.environ.get("MATTERMOST_ADMIN_USER", "admin")
    password = os.environ.get("MATTERMOST_ADMIN_PASSWORD", "")
    if not password:
        print("Mattermost admin password is empty; skipping human accounts")
        return
    client = httpx.Client(timeout=20)
    try:
        response = client.post(
            f"{base}/api/v4/users/login", json={"login_id": admin, "password": password}
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"Mattermost login failed ({exc})")
        return
    token = response.headers.get("Token", "")
    headers = {"Authorization": f"Bearer {token}"}
    for username, email, display, secret_key in (
        ("priya", "priya@groundlink.local", "Priya Raman", "PRIYA_PASSWORD"),
        ("arjun", "arjun@groundlink.local", "Arjun Mehta", "ARJUN_PASSWORD"),
    ):
        secret = os.environ.get(secret_key) or os.environ.get(
            "MATTERMOST_USER_PASSWORD", "groundlink-demo"
        )
        created = client.post(
            f"{base}/api/v4/users",
            headers=headers,
            json={
                "email": email,
                "username": username,
                "password": secret,
                "first_name": display.split()[0],
                "last_name": display.split()[-1],
            },
        )
        print(f"mattermost {username}: {created.status_code}")


if __name__ == "__main__":
    main()
