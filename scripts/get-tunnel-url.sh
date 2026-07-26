#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname -- "$script_dir")
cd "$repo_dir"

attempt=0
while [ "$attempt" -lt 30 ]; do
  tunnel_url=$(
    docker compose logs --no-color cloudflared 2>&1 \
      | grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' \
      | tail -n 1 \
      || true
  )
  if [ -n "$tunnel_url" ]; then
    printf '%s\n' "$tunnel_url"
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 2
done

echo "Cloudflare Quick Tunnel URL was not found." >&2
docker compose logs --no-color --tail 30 cloudflared >&2
exit 1
