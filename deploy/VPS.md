# VPS

This is the path for one Ubuntu machine. There is no AWS in this repository.

## What you get

- Docker Engine and the Compose plugin, installed by `deploy/deploy.sh` if they are missing.
- Caddy, for HTTPS in front of the dashboard.
- A systemd unit, `deploy/groundlink.service`, that runs `docker compose --profile collab --profile gateway up -d` from `/opt/groundlink`.

## Command

From a checkout, as a user who can `sudo`:

```bash
bash deploy/deploy.sh
```

The script copies the tree to `/opt/groundlink`, writes `.env` if needed, and starts the unit. The first start pulls the Switch images and the amd64 Mattermost image. That pull is large.

## HTTPS

Set `SITE_HOST` and `CADDY_EMAIL`, then install `deploy/Caddyfile` as `/etc/caddy/Caddyfile` and reload Caddy. The file proxies `/` to `127.0.0.1:8090`, `/mm` to Mattermost, and `/switch` to the gateway.

Leave `SWITCH_BIND_ADDR=127.0.0.1` so the published ports stay on the loopback and Caddy is the public door.

## After it is up

```bash
cd /opt/groundlink
python3 -m scripts.replay_demo
python3 -m scripts.killswitch_demo
```

The dashboard is `http://127.0.0.1:8090` on the machine, and `https://$SITE_HOST` once Caddy has a certificate.

## What this does not do

It does not open cloud security groups, create a domain, or store telemetry off the box. SQLite lives in the `gldata` volume. Switch state lives in Postgres in the `pgdata` volume.
