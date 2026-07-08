#!/usr/bin/env bash
# Launch NBAforecast locally (macOS / Linux).
#
#   ./scripts/dev.sh
#
# Brings up the backend stack (Postgres, Redis, MinIO, MLflow, API) in Docker, waits for the API
# to be healthy, then starts the Next.js frontend dev server in the foreground. Ctrl+C stops the
# frontend; the Docker stack keeps running (stop it with `docker compose down`).
#
# Prerequisites: Docker running, Node 20+, pnpm.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Starting the backend stack (Docker)..."
docker compose up -d

echo "==> Waiting for the API (http://localhost:8000/health)..."
for _ in $(seq 1 60); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "    API is up."
    break
  fi
  sleep 2
done

# The frontend calls the API through a same-origin /backend proxy (no CORS). .env.local is
# git-ignored, so create it on first run.
if [ ! -f frontend/.env.local ]; then
  echo "==> Creating frontend/.env.local"
  printf 'API_PROXY_TARGET=http://127.0.0.1:8000\nNEXT_PUBLIC_API_URL=http://127.0.0.1:3000/backend\n' > frontend/.env.local
fi

if [ ! -d frontend/node_modules ]; then
  echo "==> Installing frontend dependencies..."
  pnpm --dir frontend install
fi

echo "==> Frontend starting at http://localhost:3000  (Ctrl+C to stop)"
pnpm --dir frontend dev
