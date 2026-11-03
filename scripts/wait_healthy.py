"""Block until the mission API answers. Switch is reported, not required to exit 0."""

from __future__ import annotations

import os
import time
import urllib.request


def _ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return int(response.status) < 300
    except Exception:
        return False


def main() -> None:
    mission = os.environ.get("MISSION_API_URL", "http://127.0.0.1:8090").rstrip("/") + "/health"
    switch = os.environ.get("SWITCH_BASE_URL", "http://127.0.0.1:8000").rstrip("/") + "/health"
    deadline = time.time() + float(os.environ.get("WAIT_TIMEOUT_S", "180"))
    while time.time() < deadline:
        if _ok(mission):
            print(f"mission api healthy ({mission})")
            print("switch healthy" if _ok(switch) else "switch not healthy yet; agents will retry")
            return
        time.sleep(2)
    raise SystemExit(f"timed out waiting for {mission}")


if __name__ == "__main__":
    main()
