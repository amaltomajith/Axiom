#!/usr/bin/env bash
# Run the Autopilot on this laptop and publish it through a free Cloudflare quick tunnel (no account needed).
#
#   scripts/live-demo.sh start     start the API + cockpit on :8000 and the tunnel, each under a restart loop
#   scripts/live-demo.sh url       print the public URL (it changes whenever the tunnel restarts)
#   scripts/live-demo.sh status    what is running, storage, broker, and the URL
#   scripts/live-demo.sh stop      stop both
#
# Paper only. Secrets (Alpaca paper keys, the LLM key, AXIOM_API_TOKEN) are read by the backend itself from
# backend/.env; this script never reads that file. DATABASE_URL is forced empty so the demo uses local SQLite and
# never the production database that backend/.env may name. Both processes are started detached, so closing the
# terminal does not stop them; a crash or a low-memory kill is restarted after a few seconds.
#
# Settings can be overridden from the environment: BRAIN (desk), SYMBOLS (BTC/USD,ETH/USD), PORT (8000).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
CACHE="$BACKEND/.cache"
PORT="${PORT:-8000}"
BRAIN="${BRAIN:-desk}"
SYMBOLS="${SYMBOLS:-BTC/USD,ETH/USD}"
URL_FILE="$CACHE/public-url.txt"
mkdir -p "$CACHE"

find_cloudflared() {
  command -v cloudflared 2>/dev/null && return
  local la; la="$(cygpath -u "${LOCALAPPDATA:-$HOME/AppData/Local}")"
  for p in "$la/cloudflared/cloudflared.exe" "/c/Program Files (x86)/cloudflared/cloudflared.exe" \
           "/c/Program Files/cloudflared/cloudflared.exe" "$la/Microsoft/WinGet/Links/cloudflared.exe"; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
}

loop_backend() {
  echo $$ > "$CACHE/live-demo-backend.pid"
  cd "$BACKEND" || exit 1
  export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-C:/Users/Amal/.venvs/axiom}"
  export DATABASE_URL=                       # local SQLite, never the production database
  export SERVE_FRONTEND=true TRADER_ENABLED=true TRADER_BROKER=alpaca TRADER_BRAIN="$BRAIN"
  export TRADER_SYMBOLS="$SYMBOLS" TRADER_AUTONOMY_START=SUPERVISED TRADER_GUEST_ACTIONS=true
  while [ ! -f "$CACHE/live-demo.stop" ]; do
    echo "[$(date -u +%FT%TZ)] starting the API on :$PORT" >> "$CACHE/autopilot-live.log"
    uv run uvicorn axiom.api.app:app --host 127.0.0.1 --port "$PORT" >> "$CACHE/autopilot-live.log" 2>&1
    echo "[$(date -u +%FT%TZ)] the API exited ($?); restarting in 5 s" >> "$CACHE/autopilot-live.log"
    sleep 5
  done
}

loop_tunnel() {
  echo $$ > "$CACHE/live-demo-tunnel.pid"
  local cf; cf="$(find_cloudflared)"
  [ -n "$cf" ] || { echo "cloudflared not found" >> "$CACHE/tunnel.log"; exit 1; }
  while [ ! -f "$CACHE/live-demo.stop" ]; do
    rm -f "$URL_FILE"
    "$cf" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" 2>&1 | while IFS= read -r line; do
      echo "$line" >> "$CACHE/tunnel.log"
      if [[ $line =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then echo "${BASH_REMATCH[1]}" > "$URL_FILE"; fi
    done
    echo "[$(date -u +%FT%TZ)] the tunnel exited; restarting in 5 s (the URL will change)" >> "$CACHE/tunnel.log"
    sleep 5
  done
}

detach() {  # start "$0 <role>" in its own hidden process, outside this shell's process tree
  local bash_exe; bash_exe="$(cygpath -w "$(command -v bash)")"
  local self; self="$(cygpath -m "$(cd "$(dirname "$0")" && pwd)/$(basename "$0")")"
  powershell.exe -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath '$bash_exe' -ArgumentList '$self','$1'" \
    || { echo "could not start $1"; exit 1; }
}

running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

case "${1:-}" in
  _backend) loop_backend ;;
  _tunnel) loop_tunnel ;;
  start)
    [ -n "$(find_cloudflared)" ] || {
      echo "Install cloudflared first: winget install --id Cloudflare.cloudflared, or save the official"
      echo "cloudflared-windows-amd64.exe from github.com/cloudflare/cloudflared/releases as %LOCALAPPDATA%\\cloudflared\\cloudflared.exe"
      exit 1; }
    [ -f "$ROOT/dist/index.html" ] || { echo "Build the cockpit first: npm run build:selfhost"; exit 1; }
    rm -f "$CACHE/live-demo.stop"
    running "$CACHE/live-demo-backend.pid" && echo "API loop already running" || detach _backend
    running "$CACHE/live-demo-tunnel.pid" && echo "tunnel loop already running" || detach _tunnel
    printf "waiting for the public URL"
    for _ in $(seq 1 60); do [ -s "$URL_FILE" ] && break; printf "."; sleep 2; done; echo
    if [ -s "$URL_FILE" ]; then echo "Public URL: $(cat "$URL_FILE")/app"; else echo "No URL yet; see $CACHE/tunnel.log"; fi
    ;;
  url) [ -s "$URL_FILE" ] && echo "$(cat "$URL_FILE")/app" || { echo "no tunnel URL yet"; exit 1; } ;;
  status)
    running "$CACHE/live-demo-backend.pid" && echo "API loop: running" || echo "API loop: stopped"
    running "$CACHE/live-demo-tunnel.pid" && echo "tunnel loop: running" || echo "tunnel loop: stopped"
    curl -s -m 5 "http://127.0.0.1:$PORT/api/health" | head -c 400; echo
    [ -s "$URL_FILE" ] && echo "Public URL: $(cat "$URL_FILE")/app"
    ;;
  stop)
    touch "$CACHE/live-demo.stop"
    for f in "$CACHE/live-demo-backend.pid" "$CACHE/live-demo-tunnel.pid"; do running "$f" && kill "$(cat "$f")" 2>/dev/null; rm -f "$f"; done
    for pid in $(netstat -ano | grep -E "127\.0\.0\.1:$PORT .*LISTENING" | awk '{print $NF}' | sort -u); do taskkill //F //T //PID "$pid" >/dev/null 2>&1; done
    taskkill //F //IM cloudflared.exe >/dev/null 2>&1
    rm -f "$URL_FILE"
    echo "stopped"
    ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
