#!/usr/bin/env bash
# One command for a fresh Ubuntu VPS. Run as a user who can sudo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi
if ! command -v caddy >/dev/null 2>&1; then
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
  sudo apt-get update
  sudo apt-get install -y caddy
fi
cd "$ROOT"
python3 scripts/init_env.py
sudo mkdir -p /opt/groundlink
sudo rsync -a --delete --exclude .venv --exclude .git "$ROOT"/ /opt/groundlink/
sudo cp "$ROOT/deploy/groundlink.service" /etc/systemd/system/groundlink.service
sudo systemctl daemon-reload
sudo systemctl enable --now groundlink
echo "Caddy: set SITE_HOST and CADDY_EMAIL, then install deploy/Caddyfile."
echo "Dashboard will listen on 127.0.0.1:8090 after the images finish pulling."
