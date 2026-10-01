#!/usr/bin/env bash
# Pull latest code, rebuild, run migrations (api runs alembic on start), and health check.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"

git pull --ff-only
$COMPOSE up -d --build

echo "Waiting for api to become healthy..."
for i in $(seq 1 30); do
    if $COMPOSE exec -T api curl -fs localhost:8000/health > /dev/null 2>&1; then
        echo "api healthy"
        $COMPOSE ps
        exit 0
    fi
    sleep 5
done

echo "api did not become healthy, recent logs:" >&2
$COMPOSE logs --tail=50 api >&2
exit 1
