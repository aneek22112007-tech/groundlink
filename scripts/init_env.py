"""Fill a local .env from .env.example. Existing non-empty values are kept."""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {
    "DB_PASSWORD",
    "DB_OWNER_PASSWORD",
    "AGENT_REGISTRATION_TOKEN",
    "GATEWAY_ADMIN_PASSWORD",
    "MATTERMOST_ADMIN_PASSWORD",
    "MATTERMOST_USER_PASSWORD",
    "CONTROLLER_TOKEN_SECRET",
}


def _parse(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            rows.append(("", line))
            continue
        key, value = line.split("=", 1)
        rows.append((key.strip(), value))
    return rows


def _render(rows: list[tuple[str, str]]) -> str:
    lines = []
    for key, value in rows:
        if not key:
            lines.append(value)
        else:
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def main() -> None:
    example = ROOT / ".env.example"
    target = ROOT / ".env"
    source = target if target.exists() else example
    rows = _parse(source.read_text(encoding="utf-8"))
    found = {key for key, _ in rows if key}
    if "SECRET_KEYS" not in found:
        rows.append(("SECRET_KEYS", ""))
    updated: list[tuple[str, str]] = []
    for key, value in rows:
        if key in GENERATED and not value.strip():
            updated.append((key, secrets.token_urlsafe(32)))
        elif key == "SECRET_KEYS" and not value.strip():
            updated.append((key, f"local:{secrets.token_urlsafe(48)}"))
        else:
            updated.append((key, value))
    target.write_text(_render(updated), encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
