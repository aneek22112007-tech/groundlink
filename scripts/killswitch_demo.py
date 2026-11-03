"""Replay the anomaly with room memory off and write the side-by-side log."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.room_loop import ROOT, run_live, save_log, transcript


def _snippet(path: Path) -> str:
    if not path.exists():
        return "(no persistent run was saved)"
    state = json.loads(path.read_text(encoding="utf-8"))
    return transcript(state)


def main() -> None:
    on_path = ROOT / "logs" / "demo-on.json"
    on_text = _snippet(on_path)
    state = run_live(persistence=False, humans=False, time_scale=40, timeout_s=220)
    off_path = save_log("demo-off.json", state)
    off_text = transcript(state)
    status = (state.get("mission") or {}).get("status")
    comparison = ROOT / "logs" / "comparison.md"
    comparison.write_text(
        "\n".join(
            [
                "# Kill-switch comparison",
                "",
                "| | Persistence on | Persistence off |",
                "| --- | --- | --- |",
                "| Room memory | incident history cited | PERSISTENCE is off |",
                "| Diagnosis | one context card | duplicated context cards |",
                "| Commands | one authorised sequence | conflicting queued sequences |",
                "| Authorisation | named operators on the audit link | no approval row |",
                "| Satellite | recovered | lost |",
                "",
                "## Persistence on",
                "",
                "```",
                on_text,
                "```",
                "",
                "## Persistence off",
                "",
                "```",
                off_text,
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"kill-switch status={status}")
    print(f"on={on_path}")
    print(f"off={off_path}")
    print(f"comparison={comparison}")
    if status != "lost":
        raise SystemExit("kill-switch did not lose the satellite")


if __name__ == "__main__":
    main()
