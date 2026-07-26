#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname -- "$script_dir")
cd "$repo_dir"

docker compose up -d

services="redis searxng app"
attempt=0
while [ "$attempt" -lt 60 ]; do
  ready=true
  for service in $services; do
    container_id=$(docker compose ps -q "$service")
    if [ -z "$container_id" ]; then
      ready=false
      break
    fi
    state=$(docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$container_id")
    if [ "$state" != "healthy" ] && [ "$state" != "running" ]; then
      ready=false
      break
    fi
  done
  if [ "$ready" = true ]; then
    exec "$script_dir/get-tunnel-url.sh"
  fi
  attempt=$((attempt + 1))
  sleep 2
done

echo "Services did not become healthy in time." >&2
docker compose ps >&2
exit 1
