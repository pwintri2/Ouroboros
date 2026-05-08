#!/usr/bin/env bash
set -euo pipefail

ROOT="${WINTRIP_ROOT:-/home/pwintri2/WintripAI}"
COCKPIT_DIR="$ROOT/ouroboros_cockpit"
BACKEND_URL="${WINTRIP_BACKEND_URL:-http://127.0.0.1:8010}"
PREVIEW_URL="${WINTRIP_WEB_PREVIEW_URL:-http://127.0.0.1:1420}"
BRIDGE_URL="${WINTRIP_RCLONE_BRIDGE_URL_HOST:-http://127.0.0.1:8766}"
BRIDGE_PORT="${WINTRIP_RCLONE_BRIDGE_PORT:-8766}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/ouroboros-preview"
LOG_DIR="$STATE_DIR/logs"
PID_FILE="$STATE_DIR/vite.pid"
TOKEN_PATH="${WINTRIP_RCLONE_BRIDGE_TOKEN_PATH_HOST:-$ROOT/.secrets/rclone_bridge_token}"

mkdir -p "$LOG_DIR" "$ROOT/.secrets"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 ontbreekt; de officiële preview start niet half."
}

http_ok() {
  python3 - "$1" <<'PY'
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2.0) as response:
        raise SystemExit(0 if response.status < 500 else 1)
except Exception:
    raise SystemExit(1)
PY
}

port_open() {
  python3 - "$1" "$2" <<'PY'
import socket, sys
with socket.socket() as sock:
    sock.settimeout(1.0)
    raise SystemExit(0 if sock.connect_ex((sys.argv[1], int(sys.argv[2]))) == 0 else 1)
PY
}

preview_is_current() {
  python3 - "$PREVIEW_URL" <<'PY'
import sys, urllib.request
base = sys.argv[1].rstrip("/")
try:
    html = urllib.request.urlopen(base + "/", timeout=2.5).read(200000).decode("utf-8", "replace")
    app = urllib.request.urlopen(base + "/src/App.tsx", timeout=2.5).read(2000000).decode("utf-8", "replace")
except Exception as exc:
    print(exc)
    raise SystemExit(1)
required = ["Ouroboros Cockpit", "/src/main.tsx", "Runtime Doctor", "/api/ouroboros/runtime/doctor"]
missing = [item for item in required if item not in (html + app)]
if missing:
    print("missing source hints: " + ", ".join(missing))
    raise SystemExit(1)
raise SystemExit(0)
PY
}

bridge_is_valid() {
  python3 - "$BRIDGE_URL" "$TOKEN_PATH" <<'PY'
import json, sys, urllib.request
base, token_path = sys.argv[1].rstrip("/"), sys.argv[2]
try:
    token = open(token_path, encoding="utf-8").read().strip()
except Exception as exc:
    print(exc)
    raise SystemExit(1)
request = urllib.request.Request(base + "/computer/status", headers={"X-Ouroboros-Bridge-Token": token})
try:
    with urllib.request.urlopen(request, timeout=2.5) as response:
        data = json.loads(response.read().decode("utf-8") or "{}")
except Exception as exc:
    print(exc)
    raise SystemExit(1)
raise SystemExit(0 if data.get("status") == "online" else 1)
PY
}

wait_for_url() {
  local url="$1"
  local attempts="${2:-60}"
  for _ in $(seq 1 "$attempts"); do
    http_ok "$url" && return 0
    sleep 1
  done
  return 1
}

wait_for_preview() {
  for _ in $(seq 1 60); do
    preview_is_current && return 0
    sleep 1
  done
  return 1
}

ensure_backend() {
  need_cmd docker
  echo "Refreshing Docker backend and Chroma..."
  (cd "$ROOT" && docker compose up -d --build chroma ouroboros-backend)
  wait_for_url "$BACKEND_URL/health" 90 || fail "backend route $BACKEND_URL/health werd niet bereikbaar."
}

ensure_host_bridge() {
  if port_open 127.0.0.1 "$BRIDGE_PORT"; then
    bridge_is_valid || fail "poort $BRIDGE_PORT is bezet door een oude of verkeerde host bridge; /computer/status werkt niet met de Ouroboros bridge token."
    echo "Host bridge online."
    return 0
  fi
  [ -f "$ROOT/scripts/rclone_host_bridge.py" ] || fail "scripts/rclone_host_bridge.py ontbreekt."
  echo "Starting host bridge on $BRIDGE_URL..."
  (cd "$ROOT" && nohup python3 scripts/rclone_host_bridge.py --bind 0.0.0.0 --port "$BRIDGE_PORT" >"$LOG_DIR/host_bridge.log" 2>&1 &)
  for _ in $(seq 1 30); do
    if port_open 127.0.0.1 "$BRIDGE_PORT" && bridge_is_valid; then
      echo "Host bridge online."
      return 0
    fi
    sleep 1
  done
  fail "host bridge startte niet geldig op $BRIDGE_URL."
}

ensure_preview() {
  need_cmd node
  need_cmd npm
  [ -d "$COCKPIT_DIR" ] || fail "cockpit directory ontbreekt: $COCKPIT_DIR"
  [ -d "$COCKPIT_DIR/node_modules" ] || fail "node_modules ontbreekt in $COCKPIT_DIR; voer eerst npm install uit."

  if port_open 127.0.0.1 1420; then
    preview_is_current || fail "poort 1420 is bezet door een oude of verkeerde preview."
    echo "Vite preview is al actueel."
    return 0
  fi

  echo "Starting Vite dev server on fixed port 1420..."
  (
    cd "$COCKPIT_DIR"
    VITE_BACKEND_URL="$BACKEND_URL" TAURI_BACKEND_URL="$BACKEND_URL" nohup npm run dev -- --host 0.0.0.0 --port 1420 --strictPort >"$LOG_DIR/vite.log" 2>&1 &
    echo "$!" >"$PID_FILE"
  )
  wait_for_preview || fail "Vite preview werd niet actueel bereikbaar op $PREVIEW_URL. Zie $LOG_DIR/vite.log."
}

main() {
  need_cmd python3
  ensure_host_bridge
  ensure_backend
  ensure_preview
  echo "Running runtime doctor smoke..."
  python3 "$ROOT/scripts/doctor_ouroboros_runtime.py" \
    --backend-url "$BACKEND_URL" \
    --preview-url "$PREVIEW_URL" \
    --bridge-url "$BRIDGE_URL" \
    --smoke \
    --json
  echo "Ouroboros preview ready: $PREVIEW_URL"
}

main "$@"
