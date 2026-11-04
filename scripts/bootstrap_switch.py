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


def _host_state() -> Path:
    """Agent keys on the host live in .switch. /data is the container path."""
    fallback = ROOT / ".switch"
    raw = os.environ.get("SWITCH_STATE_DIR", "")
    candidate = Path(raw) if raw else fallback
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        candidate = fallback
        candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _load_env() -> None:
    from scripts.envfile import load_env

    load_env()


def main() -> None:
    _load_env()
    from scripts.envfile import switch_url

    base = switch_url()
    token = os.environ.get("AGENT_REGISTRATION_TOKEN", "")
    state = _host_state()
    if not token:
        print("AGENT_REGISTRATION_TOKEN is empty; skipping Switch registration")
        return
    from agents.common.switch_client import SwitchClient

    room_id = ""
    for name, description in AGENTS:
        client = SwitchClient(base, name, registration_token=token)
        key_path = state / "agents" / f"{name}.json"
        try:
            client.register(description)
        except RuntimeError:
            if key_path.exists():
                print(f"{name}: already registered")
                continue
            try:
                client.register(description, overwrite=True)
            except (httpx.HTTPError, RuntimeError) as exc:
                print(f"{name}: register failed ({exc})")
                continue
        except httpx.HTTPError as exc:
            print(f"{name}: register failed ({exc})")
            continue
        if client.api_key:
            key_path.parent.mkdir(exist_ok=True)
            key_path.write_text(
                json.dumps({"agent_id": client.agent_id, "api_key": client.api_key, "name": name}),
                encoding="utf-8",
            )
        try:
            client.allow_anyone()
        except httpx.HTTPError as exc:
            print(f"{name}: addressing failed ({exc})")
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
                result = client.call(operation, arguments, connection=False)
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
        user_id = ""
        if created.status_code == 201:
            user_id = str(created.json().get("id", ""))
        if not user_id:
            existing = client.get(f"{base}/api/v4/users/username/{username}", headers=headers)
            if existing.status_code == 200:
                user_id = str(existing.json().get("id", ""))
        if not user_id:
            continue
        team_id = _team_id(client, headers)
        if team_id:
            client.post(
                f"{base}/api/v4/teams/{team_id}/members",
                headers=headers,
                json={"team_id": team_id, "user_id": user_id},
            )
        channel_id = _channel_id(client, headers, team_id)
        if channel_id:
            os.environ["MATTERMOST_CHANNEL_ID"] = channel_id
            client.post(
                f"{base}/api/v4/channels/{channel_id}/members",
                headers=headers,
                json={"user_id": user_id},
            )
    _remember_channel()


def _team_id(client: httpx.Client, headers: dict[str, str]) -> str:
    from scripts.envfile import mattermost_url

    name = os.environ.get("MATTERMOST_TEAM_NAME", "switch")
    response = client.get(f"{mattermost_url()}/api/v4/teams", headers=headers)
    if response.status_code != 200:
        return ""
    for team in response.json():
        if team.get("name") == name:
            return str(team.get("id", ""))
    return ""


def _channel_id(client: httpx.Client, headers: dict[str, str], team_id: str) -> str:
    if not team_id:
        return ""
    from scripts.envfile import mattermost_url

    base = mattermost_url()
    found = client.get(f"{base}/api/v4/teams/{team_id}/channels/name/kestrel-7", headers=headers)
    if found.status_code == 200:
        return str(found.json().get("id", ""))
    created = client.post(
        f"{base}/api/v4/channels",
        headers=headers,
        json={
            "team_id": team_id,
            "name": "kestrel-7",
            "display_name": "Kestrel-7",
            "type": "O",
            "purpose": "GroundLink anomaly response",
        },
    )
    if created.status_code not in {200, 201}:
        return ""
    return str(created.json().get("id", ""))


def _remember_channel() -> None:
    channel_id = os.environ.get("MATTERMOST_CHANNEL_ID", "").strip()
    if not channel_id:
        return
    path = ROOT / ".env"
    if not path.exists():
        return
    rows = path.read_text(encoding="utf-8").splitlines()
    updated = False
    out: list[str] = []
    for line in rows:
        if line.startswith("MATTERMOST_CHANNEL_ID="):
            current = line.split("=", 1)[1].strip()
            out.append(line if current else f"MATTERMOST_CHANNEL_ID={channel_id}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"MATTERMOST_CHANNEL_ID={channel_id}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
