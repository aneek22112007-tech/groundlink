from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_alembic_upgrade_creates_the_mission_table(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    root = Path(__file__).resolve().parents[1]
    subprocess.check_call(
        [str(root / ".venv" / "bin" / "alembic"), "upgrade", "head"], cwd=root, env=env
    )
    import sqlite3

    connection = sqlite3.connect(tmp_path / "migrate.db")
    names = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"missions", "commands", "approvals", "events", "telemetry"} <= names
