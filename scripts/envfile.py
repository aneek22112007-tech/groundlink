"""Read the local .env and resolve host URLs for scripts that run outside compose."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _loopback(url_key: str, port_key: str, default_port: str, compose_host: str) -> str:
    load_env()
    configured = os.environ.get(url_key, "").strip()
    if configured and f"://{compose_host}" not in configured:
        return configured.rstrip("/")
    port = os.environ.get(port_key, default_port).strip() or default_port
    return f"http://127.0.0.1:{port}"


def mission_api_url() -> str:
    return _loopback("MISSION_API_URL", "MISSION_HOST_PORT", "8090", "mission")


def switch_url() -> str:
    return _loopback("SWITCH_BASE_URL", "API_HOST_PORT", "8000", "switch")


def mattermost_url() -> str:
    return _loopback("MATTERMOST_URL", "MATTERMOST_HOST_PORT", "8065", "mattermost")
