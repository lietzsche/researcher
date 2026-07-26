#!/usr/bin/env bash
set -euo pipefail

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is required but was not found in PATH." >&2
  echo "Install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
  exit 127
fi

MCP_HOST="${MCP_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-8765}"

exec cloudflared tunnel --url "http://${MCP_HOST}:${MCP_PORT}"
