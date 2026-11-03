# Security

GroundLink is a hackathon mission room, not a flight-certified command system. The controls below are what the code actually enforces.

## Authority

- A command can become `transmitted` only inside `commit_transmit`. `set_status` refuses that jump.
- Reversible commands need `flight_ops_engineer` or `mission_director`.
- Irreversible commands need the mission director's exact statement, during the pass window, plus a different operator confirming.
- Observers, late messages, and approvals bound to an older option version are refused in the thread.
- Property tests in `tests/test_gate.py` check that a transmitted command has a valid approval set.

## Audit

Events are append-only. Each row stores `sha256(previous hash + canonical JSON)`. `verify_chain` reports a break if a payload changes. The audit page for a mission is the link that answers who authorised a burn.

## Secrets

`.env` is gitignored. `scripts/init_env.py` generates local passwords and `SECRET_KEYS`. Do not commit `.switch/`, which holds agent API keys returned once by Switch.

`LLM_API_KEY` is optional. With no key, agents post the deterministic text.

Discord and Telegram adapters stay off unless their env flags and tokens are set.

## Network

`docker-compose.yml` publishes the dashboard, Switch, and Mattermost on `127.0.0.1` unless `SWITCH_BIND_ADDR` is changed. `deploy/Caddyfile` is the HTTPS front for a VPS. The Mattermost image is pinned to `11.9.0` and runs `linux/amd64`, including under emulation.

## Reporting

Open a private security report on the GitHub repository if you find a way to mark a command transmitted without an approval row. Please include the test that fails today.
