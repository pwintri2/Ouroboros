#!/usr/bin/env bash
set -u

ROOT="${WINTRIP_ROOT:-/home/pwintri2/WintripAI}"
CHAT_DIR="${OUROBOROS_CHAT_DIR:-/home/pwintri2/ouroboros-chat}"
BACKEND_URL="${TAURI_BACKEND_URL:-${VITE_BACKEND_URL:-http://localhost:8010}}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/ouroboros-chat"
LOG_DIR="$STATE_DIR/logs"
LOCK_FILE="$STATE_DIR/launcher.lock"
BRIDGE_PORT="${WINTRIP_RCLONE_BRIDGE_PORT:-8766}"
BRIDGE_URL="http://127.0.0.1:$BRIDGE_PORT"
TOKEN_PATH="${WINTRIP_RCLONE_BRIDGE_TOKEN_PATH_HOST:-$ROOT/.secrets/rclone_bridge_token}"
VITE_PORT="${OUROBOROS_CHAT_VITE_PORT:-1421}"

mkdir -p "$LOG_DIR"
exec >>"$LOG_DIR/launcher.log" 2>&1

echo ""
echo "[$(date -Is)] Starting Ouroboros Chat"
echo "root=$ROOT"
echo "chat_dir=$CHAT_DIR"
echo "backend=$BACKEND_URL"

notify() {
  if command -v notify-send >/dev/null 2>&1; then
    notify-send -a "Ouroboros Chat" "$1" "${2:-}" >/dev/null 2>&1 || true
  fi
}

port_is_up() {
  python3 - "$1" "$2" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.socket() as sock:
    sock.settimeout(1.0)
    raise SystemExit(0 if sock.connect_ex((host, port)) == 0 else 1)
PY
}

url_is_up() {
  python3 - "$1" <<'PY'
import sys
import urllib.request

url = sys.argv[1].rstrip("/") + "/health"
try:
    with urllib.request.urlopen(url, timeout=1.5) as response:
        raise SystemExit(0 if response.status < 500 else 1)
except Exception:
    raise SystemExit(1)
PY
}

bridge_is_current() {
  python3 - "$BRIDGE_URL" "$TOKEN_PATH" <<'PY'
import json
import sys
import urllib.request

base, token_path = sys.argv[1].rstrip("/"), sys.argv[2]
try:
    token = open(token_path, encoding="utf-8").read().strip()
except Exception:
    raise SystemExit(1)

request = urllib.request.Request(
    base + "/vps/status",
    headers={"X-Ouroboros-Bridge-Token": token},
)
try:
    with urllib.request.urlopen(request, timeout=4.0) as response:
        data = json.loads(response.read().decode("utf-8") or "{}")
except Exception:
    raise SystemExit(1)

excludes = set(data.get("default_excludes") or [])
required = {"out/", "out/**", ".roo/", ".roo/**", "logs/", "logs/**", "*.log", "**/*.log"}
raise SystemExit(0 if required.issubset(excludes) else 1)
PY
}

wait_for_backend() {
  for _ in $(seq 1 45); do
    url_is_up "$BACKEND_URL" && return 0
    sleep 1
  done
  return 1
}

ensure_backend() {
  if url_is_up "$BACKEND_URL"; then
    echo "Backend already online."
    return 0
  fi

  if command -v docker >/dev/null 2>&1; then
    echo "Backend offline; trying docker compose up -d ouroboros-backend."
    (cd "$ROOT" && docker compose up -d ouroboros-backend) || true
    if wait_for_backend; then
      echo "Backend online after docker compose."
      return 0
    fi
  fi

  echo "Backend is still offline; launching Ouroboros Chat anyway."
  notify "Ouroboros backend offline" "Ouroboros Chat start, maar $BACKEND_URL is nog niet bereikbaar."
  return 0
}

ensure_host_bridge() {
  if port_is_up 127.0.0.1 "$BRIDGE_PORT"; then
    if bridge_is_current; then
      echo "Host bridge already online on port $BRIDGE_PORT."
      return 0
    fi
    echo "Host bridge on port $BRIDGE_PORT is stale; restarting it."
    pkill -f "scripts/rclone_host_bridge.py.*--port $BRIDGE_PORT" >/dev/null 2>&1 || true
    pkill -f "python3 scripts/rclone_host_bridge.py$" >/dev/null 2>&1 || true
    for _ in $(seq 1 10); do
      port_is_up 127.0.0.1 "$BRIDGE_PORT" || break
      sleep 0.5
    done
  fi

  if [ ! -f "$ROOT/scripts/rclone_host_bridge.py" ]; then
    echo "Host bridge script missing; continuing without bridge."
    return 0
  fi

  echo "Starting Ouroboros host bridge on port $BRIDGE_PORT."
  (cd "$ROOT" && setsid -f python3 scripts/rclone_host_bridge.py --bind 0.0.0.0 --port "$BRIDGE_PORT" >"$LOG_DIR/host_bridge.log" 2>&1)
  for _ in $(seq 1 20); do
    port_is_up 127.0.0.1 "$BRIDGE_PORT" && bridge_is_current && {
      echo "Host bridge online."
      return 0
    }
    sleep 0.5
  done
  echo "Host bridge did not open port $BRIDGE_PORT yet; continuing with local fallbacks."
  return 0
}

wait_for_vite() {
  for _ in $(seq 1 40); do
    port_is_up 127.0.0.1 "$VITE_PORT" && return 0
    sleep 0.5
  done
  return 1
}

paths_newer_than() {
  local binary="$1"
  shift
  [ -e "$binary" ] || return 0
  find "$@" -newer "$binary" -print -quit 2>/dev/null | grep -q .
}

release_binary_is_fresh() {
  local binary="$1"
  [ -x "$binary" ] || return 1
  ! paths_newer_than \
    "$binary" \
    "$CHAT_DIR/src" \
    "$CHAT_DIR/dist" \
    "$CHAT_DIR/index.html" \
    "$CHAT_DIR/package.json" \
    "$CHAT_DIR/vite.config.ts" \
    "$CHAT_DIR/src-tauri/src" \
    "$CHAT_DIR/src-tauri/capabilities" \
    "$CHAT_DIR/src-tauri/tauri.conf.json" \
    "$CHAT_DIR/src-tauri/Cargo.toml"
}

debug_binary_native_is_fresh() {
  local binary="$1"
  [ -x "$binary" ] || return 1
  ! paths_newer_than \
    "$binary" \
    "$CHAT_DIR/src-tauri/src" \
    "$CHAT_DIR/src-tauri/capabilities" \
    "$CHAT_DIR/src-tauri/tauri.conf.json" \
    "$CHAT_DIR/src-tauri/Cargo.toml"
}

ensure_vite_for_debug_binary() {
  if port_is_up 127.0.0.1 "$VITE_PORT"; then
    echo "Vite already online."
    return 0
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is not available; cannot start Vite for debug binary."
    notify "Ouroboros Chat kan niet starten" "npm ontbreekt en er is geen release binary gevonden."
    return 1
  fi
  echo "Starting Vite dev server for Tauri debug binary."
  (cd "$CHAT_DIR" && nohup npm run dev >"$LOG_DIR/vite.log" 2>&1 &)
  wait_for_vite
}

launch_chat() {
  if [ ! -d "$CHAT_DIR" ]; then
    echo "Ouroboros Chat directory missing: $CHAT_DIR"
    notify "Ouroboros Chat ontbreekt" "$CHAT_DIR bestaat nog niet."
    exit 1
  fi

  export TAURI_BACKEND_URL="$BACKEND_URL"
  export VITE_BACKEND_URL="$BACKEND_URL"

  local release_binary="$CHAT_DIR/src-tauri/target/release/ouroboros-chat"
  local debug_binary="$CHAT_DIR/src-tauri/target/debug/ouroboros-chat"

  if release_binary_is_fresh "$release_binary"; then
    echo "Launching release Tauri binary."
    exec "$release_binary"
  elif [ -x "$release_binary" ]; then
    echo "Release Tauri binary is older than Ouroboros Chat sources; using live Tauri dev path."
  fi

  if debug_binary_native_is_fresh "$debug_binary"; then
    ensure_vite_for_debug_binary || exit 1
    echo "Launching debug Tauri binary."
    exec "$debug_binary"
  elif [ -x "$debug_binary" ]; then
    echo "Debug Tauri binary is older than native Tauri sources; rebuilding through npm run tauri -- dev."
  fi

  if command -v npm >/dev/null 2>&1; then
    echo "No binary found; falling back to npm run tauri -- dev."
    cd "$CHAT_DIR" || exit 1
    exec npm run tauri -- dev
  fi

  echo "No Tauri binary and npm is unavailable."
  notify "Ouroboros Chat kan niet starten" "Geen Tauri binary en npm ontbreekt."
  exit 1
}

(
  flock -n 9 || {
    echo "Another launcher instance is preparing Ouroboros Chat; continuing with UI launch."
    launch_chat
  }
  ensure_host_bridge
  ensure_backend
  launch_chat
) 9>"$LOCK_FILE"
