"""Kestrel-7 live demo. The heartbeat advances the bus; this script speaks as Priya and Arjun."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.export_report import main as export_main
from scripts.room_loop import run_live, save_log, transcript


def main() -> None:
    state = run_live(persistence=True, humans=True, time_scale=20, timeout_s=240)
    path = save_log("demo-on.json", state)
    status = (state.get("mission") or {}).get("status")
    print(f"demo status={status} log={path}")
    print(transcript(state)[-2000:])
    if status != "recovered":
        raise SystemExit("demo did not recover")
    export_main()


if __name__ == "__main__":
    main()
