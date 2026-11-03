"""Download the current mission's markdown and PDF report."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    base = os.environ.get("MISSION_API_URL", "http://127.0.0.1:8090").rstrip("/")
    client = httpx.Client(timeout=60)
    state = client.get(f"{base}/api/state").json()
    mission = state.get("mission") or {}
    mission_id = str(mission.get("id", ""))
    if not mission_id:
        raise SystemExit("no mission")
    folder = ROOT / "reports"
    folder.mkdir(exist_ok=True)
    markdown = client.get(f"{base}/api/report/{mission_id}.md")
    markdown.raise_for_status()
    pdf = client.get(f"{base}/api/report/{mission_id}.pdf")
    pdf.raise_for_status()
    (folder / f"{mission_id}.md").write_bytes(markdown.content)
    (folder / f"{mission_id}.pdf").write_bytes(pdf.content)
    print(folder / f"{mission_id}.md")
    print(folder / f"{mission_id}.pdf")


if __name__ == "__main__":
    main()
