#!/bin/sh
# Deploy the API to Fly with the Neon connection string and the write token as secrets.
# Reads FLY_APP_NAME, FLY_API_TOKEN, DATABASE_URL and MARGINAL_WRITE_TOKEN from the environment
# (or from .env in the repository root). Uses Fly's remote builder, so no local Docker is needed.
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
: "${FLY_APP_NAME:=marginal-alderquist-api}"
: "${DATABASE_URL:?set DATABASE_URL to the Neon connection string}"
: "${MARGINAL_WRITE_TOKEN:?set MARGINAL_WRITE_TOKEN}"
command -v flyctl >/dev/null 2>&1 || { echo "flyctl is not installed: https://fly.io/docs/flyctl/install/"; exit 1; }
if ! flyctl apps list 2>/dev/null | grep -q "^$FLY_APP_NAME"; then
  flyctl apps create "$FLY_APP_NAME" --org personal
fi
flyctl secrets set --app "$FLY_APP_NAME" --stage DATABASE_URL="$DATABASE_URL" MARGINAL_WRITE_TOKEN="$MARGINAL_WRITE_TOKEN"
flyctl deploy --app "$FLY_APP_NAME" --remote-only --ha=false
echo "deployed: https://$FLY_APP_NAME.fly.dev/v1/health"
