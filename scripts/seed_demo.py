"""Open a fresh persistent Kestrel-7 mission on a running API."""

from __future__ import annotations

import os

import httpx


def main() -> None:
    base = os.environ.get("MISSION_API_URL", "http://127.0.0.1:8090").rstrip("/")
    response = httpx.post(
        f"{base}/api/reset",
        json={"persistence": True, "seed": int(os.environ.get("SEED", "7")), "time_scale": 20},
        timeout=30,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
