from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SCREENS = ROOT / "docs" / "screens"


@pytest.mark.site
def test_landing_page_has_no_console_errors_and_loads_assets() -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    SCREENS.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    failed: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on(
                "response",
                lambda response: (
                    failed.append(f"{response.status} {response.url}")
                    if response.status >= 400
                    else None
                ),
            )
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="networkidle")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(SCREENS / "site-hero.png"))
            page.locator("#gate").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.screenshot(path=str(SCREENS / "site-gate.png"))
            assert page.locator("#replay-log .glass").count() > 0
            browser.close()
    finally:
        server.shutdown()
    assert errors == []
    assert failed == []


@pytest.mark.site
def test_dashboard_screenshot() -> None:
    import threading

    import uvicorn

    from dashboard.app import create_app

    app = create_app("sqlite://")
    config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            import urllib.request

            urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=1)
            break
        except Exception:
            import time

            time.sleep(0.1)
    SCREENS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        page.screenshot(path=str(SCREENS / "dashboard.png"))
        browser.close()
    server.should_exit = True
