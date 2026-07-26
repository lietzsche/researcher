#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname -- "$script_dir")
cd "$repo_dir"

# Rebuild and recreate only the app container after a code change. redis,
# searxng, and cloudflared are left untouched -- Compose only recreates
# services whose config/image changed, so the running Quick Tunnel and its
# URL survive this. Compose's internal DNS routes cloudflared's traffic to
# the new app container automatically once it is healthy.
docker compose up -d --build app

attempt=0
while [ "$attempt" -lt 60 ]; do
  container_id=$(docker compose ps -q app)
  if [ -n "$container_id" ]; then
    state=$(docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$container_id")
    if [ "$state" = "healthy" ] || [ "$state" = "running" ]; then
      echo "app redeployed and healthy."
      exit 0
    fi
  fi
  attempt=$((attempt + 1))
  sleep 2
done

echo "app did not become healthy in time." >&2
docker compose logs --tail 30 app >&2
exit 1
