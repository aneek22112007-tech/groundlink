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
    from scripts.envfile import mission_api_url, switch_url

    mission = mission_api_url() + "/health"
    switch = switch_url() + "/health"
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
