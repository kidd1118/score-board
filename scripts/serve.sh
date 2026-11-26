#!/usr/bin/env bash
# Serve the whole site (frontend build + API) from the backend on one port and
# publish it at a fixed https://<machine>.<tailnet>.ts.net address with Tailscale Funnel.
# The address belongs to this machine in your tailnet, so it survives IP changes.
#
#   scripts/serve.sh             build the frontend, turn on Funnel, start the backend
#   scripts/serve.sh --no-build  skip `npm run build` (nothing changed in src/)
#
# PORT (default 8080) stays clear of the development backend on 8000.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8080}"

if [[ "${1:-}" != "--no-build" ]]; then
  npm run build
fi

TS="$(command -v tailscale || true)"
if [[ -z "$TS" && -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]]; then
  TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
fi
if [[ -z "$TS" ]]; then
  echo "找不到 tailscale 指令，只在本機啟動：http://localhost:${PORT}（安裝方式見 README「固定網址」）" >&2
else
  # --bg keeps the Funnel on after this script stops and across reboots; rerunning is harmless.
  "$TS" funnel --bg "$PORT"
  "$TS" funnel status
fi

cd src/api
exec ../../.venv/bin/uvicorn main:app --host 127.0.0.1 --port "$PORT"
