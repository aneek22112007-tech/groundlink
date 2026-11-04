"""Open a fresh persistent Kestrel-7 mission on a running API."""

from __future__ import annotations

import os

import httpx


def main() -> None:
    from scripts.envfile import mission_api_url

    base = mission_api_url()
    response = httpx.post(
        f"{base}/api/reset",
        json={"persistence": True, "seed": int(os.environ.get("SEED", "7")), "time_scale": 20},
        timeout=30,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
