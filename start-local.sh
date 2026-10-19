#!/usr/bin/env bash
# Runs the backend on your computer and (optionally) exposes it with a free Cloudflare quick tunnel.
# Usage: ./start-local.sh https://YOUR-USERNAME.github.io     (the address of your GitHub Pages site)
set -euo pipefail
ORIGIN="${1:-}"
[ -z "$ORIGIN" ] && { echo "Usage: ./start-local.sh https://YOUR-USERNAME.github.io"; exit 1; }
[ -f .env.local ] || {
  echo "First run: creating .env.local with fresh secrets (back this file up; losing the master key makes saved API keys unreadable)."
  {
    echo "JOBAGENT_MASTER_KEY=$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
    echo "JOBAGENT_SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
    echo "JOBAGENT_INVITE_CODE=$(python3 -c 'import secrets;print(secrets.token_urlsafe(9))')"
  } > .env.local
}
set -a; . ./.env.local; set +a
export JOBAGENT_CORS_ORIGINS="$ORIGIN"
export JOBAGENT_SCHEDULE_HOURS="${JOBAGENT_SCHEDULE_HOURS:-24}"
echo "Invite code for your users: $JOBAGENT_INVITE_CODE"
if command -v cloudflared >/dev/null 2>&1; then
  cloudflared tunnel --url http://127.0.0.1:8000 2>&1 | grep --line-buffered -E "trycloudflare.com" &
  echo "Look above for the https://....trycloudflare.com address. Share THAT with users as the 'Server address'."
else
  echo "cloudflared not found: install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ (free). Running locally only."
fi
exec jobagent serve --host 127.0.0.1 --port 8000
