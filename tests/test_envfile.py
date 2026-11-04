from __future__ import annotations

from scripts.envfile import mattermost_url, mission_api_url, switch_url


def test_compose_dns_uses_the_host_port(monkeypatch) -> None:
    monkeypatch.setenv("MISSION_API_URL", "http://mission:8090")
    monkeypatch.setenv("MISSION_HOST_PORT", "8190")
    monkeypatch.setenv("SWITCH_BASE_URL", "http://switch:8000")
    monkeypatch.setenv("API_HOST_PORT", "8000")
    monkeypatch.setenv("MATTERMOST_URL", "http://mattermost:8065")
    monkeypatch.setenv("MATTERMOST_HOST_PORT", "8165")
    assert mission_api_url() == "http://127.0.0.1:8190"
    assert switch_url() == "http://127.0.0.1:8000"
    assert mattermost_url() == "http://127.0.0.1:8165"


def test_explicit_loopback_is_kept(monkeypatch) -> None:
    monkeypatch.setenv("MISSION_API_URL", "http://127.0.0.1:9000")
    assert mission_api_url() == "http://127.0.0.1:9000"
