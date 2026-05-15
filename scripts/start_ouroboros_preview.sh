#!/usr/bin/env bash
set -euo pipefail

ROOT="${WINTRIP_ROOT:-/home/pwintri2/WintripAI}"
COCKPIT_DIR="$ROOT/ouroboros_cockpit"
BACKEND_URL="${WINTRIP_BACKEND_URL:-http://127.0.0.1:8010}"
PREVIEW_URL="${WINTRIP_WEB_PREVIEW_URL:-http://127.0.0.1:1420}"
BRIDGE_URL="${WINTRIP_RCLONE_BRIDGE_URL_HOST:-http://127.0.0.1:8766}"
BRIDGE_PORT="${WINTRIP_RCLONE_BRIDGE_PORT:-8766}"
DOCKER_BRIDGE_URL="${WINTRIP_RCLONE_BRIDGE_URL_DOCKER:-http://host.docker.internal:$BRIDGE_PORT}"
BACKEND_REFRESH_REQUIRED="${WINTRIP_FORCE_BACKEND_REFRESH:-1}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/ouroboros-preview"
LOG_DIR="$STATE_DIR/logs"
PID_FILE="$STATE_DIR/vite.pid"
BACKEND_PID_FILE="$STATE_DIR/backend-local.pid"
BACKEND_LOG="$LOG_DIR/backend-local.log"
TOKEN_PATH="${WINTRIP_RCLONE_BRIDGE_TOKEN_PATH_HOST:-$ROOT/.secrets/rclone_bridge_token}"
NODE_BIN="${WINTRIP_NODE_BIN:-$HOME/.nvm/versions/node/v22.22.2/bin}"
BACKEND_MODE="${WINTRIP_BACKEND_MODE:-auto}"
LOCAL_BACKEND_VENV="${WINTRIP_BACKEND_VENV:-$ROOT/.venv_ouroboros_backend}"
LOCAL_BACKEND_PYTHON="${WINTRIP_BACKEND_PYTHON:-$LOCAL_BACKEND_VENV/bin/python}"
PYTHON311="${WINTRIP_PYTHON311:-$HOME/.local/bin/python3.11}"
DOCKER_BIN="${WINTRIP_DOCKER_BIN:-}"
COMPOSE_BIN="${WINTRIP_DOCKER_COMPOSE_BIN:-}"

if [ -d "$NODE_BIN" ]; then
  export PATH="$NODE_BIN:$PATH"
fi

discover_docker_bin() {
  if [ -n "$DOCKER_BIN" ] && [ -x "$DOCKER_BIN" ]; then
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    DOCKER_BIN="$(command -v docker)"
    export WINTRIP_DOCKER_BIN="$DOCKER_BIN"
    return 0
  fi
  for candidate in /run/host/usr/bin/docker /run/host/usr/local/bin/docker /usr/local/bin/docker /usr/bin/docker; do
    if [ -x "$candidate" ]; then
      DOCKER_BIN="$candidate"
      export WINTRIP_DOCKER_BIN="$DOCKER_BIN"
      export PATH="$(dirname "$DOCKER_BIN"):$PATH"
      return 0
    fi
  done
  return 1
}

discover_compose_bin() {
  if [ -n "$COMPOSE_BIN" ] && [ -x "$COMPOSE_BIN" ]; then
    return 0
  fi
  for candidate in /run/host/usr/lib/docker/cli-plugins/docker-compose /run/host/usr/libexec/docker/cli-plugins/docker-compose /usr/lib/docker/cli-plugins/docker-compose /usr/libexec/docker/cli-plugins/docker-compose; do
    if [ -x "$candidate" ]; then
      COMPOSE_BIN="$candidate"
      export WINTRIP_DOCKER_COMPOSE_BIN="$COMPOSE_BIN"
      return 0
    fi
  done
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN="$(command -v docker-compose)"
    export WINTRIP_DOCKER_COMPOSE_BIN="$COMPOSE_BIN"
    return 0
  fi
  return 1
}

docker_available() {
  discover_docker_bin && "$DOCKER_BIN" version >/dev/null 2>&1
}

compose_up() {
  export WINTRIP_RCLONE_BRIDGE_URL="$DOCKER_BRIDGE_URL"
  # docker compose up -d --build chroma ouroboros-backend
  if discover_docker_bin && "$DOCKER_BIN" compose version >/dev/null 2>&1; then
    if (cd "$ROOT" && "$DOCKER_BIN" compose up -d --build chroma ouroboros-backend); then
      return 0
    fi
    echo "docker compose build faalde; probeer bestaande image met force-recreate omdat /workspace gemount is."
    (cd "$ROOT" && "$DOCKER_BIN" compose up -d --no-build --force-recreate chroma ouroboros-backend)
    return $?
  fi
  if discover_compose_bin; then
    if (cd "$ROOT" && "$COMPOSE_BIN" up -d --build chroma ouroboros-backend); then
      return 0
    fi
    echo "docker-compose build faalde; probeer bestaande image met force-recreate omdat /workspace gemount is."
    (cd "$ROOT" && "$COMPOSE_BIN" up -d --no-build --force-recreate chroma ouroboros-backend)
    return $?
  fi
  return 1
}

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

first_free_bridge_port() {
  local candidate
  for candidate in 8767 8768 8769 8770 8771 8772 8773 8774 8775 8776; do
    if ! port_open 127.0.0.1 "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
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
required = ["Ouroboros Cockpit", "/src/main.tsx", "Runtime Doctor", "/api/ouroboros/runtime/doctor", "Roo Code Agent"]
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
if data.get("status") != "online":
    raise SystemExit(1)
request = urllib.request.Request(base + "/roo/status", headers={"X-Ouroboros-Bridge-Token": token})
try:
    with urllib.request.urlopen(request, timeout=2.5) as response:
        roo = json.loads(response.read().decode("utf-8") or "{}")
except Exception as exc:
    print(exc)
    raise SystemExit(1)
if "available" not in roo:
    raise SystemExit(1)
request = urllib.request.Request(base + "/roo/models", headers={"X-Ouroboros-Bridge-Token": token})
try:
    with urllib.request.urlopen(request, timeout=8) as response:
        roo_models = json.loads(response.read().decode("utf-8") or "{}")
except Exception as exc:
    print(exc)
    raise SystemExit(1)
if "models" not in roo_models:
    raise SystemExit(1)

# Endpoint existence check for the VPS UI artifact and Chroma merge bridge.
# The Chroma status itself may be degraded when SSH/Chroma are not configured;
# only a missing route means this is a stale bridge process.
request = urllib.request.Request(base + "/chroma-sync/status?timeout_seconds=10", headers={"X-Ouroboros-Bridge-Token": token})
try:
    with urllib.request.urlopen(request, timeout=12) as response:
        chroma_sync = json.loads(response.read().decode("utf-8") or "{}")
except Exception as exc:
    print(exc)
    raise SystemExit(1)
if chroma_sync.get("reason") == "not_found":
    raise SystemExit(1)
request = urllib.request.Request(base + "/vps/status", headers={"X-Ouroboros-Bridge-Token": token})
try:
    with urllib.request.urlopen(request, timeout=4) as response:
        vps = json.loads(response.read().decode("utf-8") or "{}")
except Exception as exc:
    print(exc)
    raise SystemExit(1)
excludes = set(vps.get("default_excludes") or [])
required_excludes = {"out/", "out/**", ".roo/", ".roo/**", "logs/", "logs/**", "*.log", "**/*.log"}
if not required_excludes.issubset(excludes):
    print("stale vps bridge excludes")
    raise SystemExit(1)
raise SystemExit(0)
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

backend_is_current() {
  python3 - "$BACKEND_URL" <<'PY'
import json, sys, urllib.request
base = sys.argv[1].rstrip("/")
try:
    with urllib.request.urlopen(base + "/health", timeout=2.5) as response:
        if response.status >= 500:
            raise SystemExit(1)
    with urllib.request.urlopen(base + "/agent/status", timeout=4.0) as response:
        data = json.loads(response.read().decode("utf-8") or "{}")
except Exception as exc:
    print(exc)
    raise SystemExit(1)
tools = set(data.get("available_tools") or [])
required = {"vps_ui_sync_preview", "vps_ui_sync_execute", "chroma_sync_preview", "chroma_sync_execute"}
missing = sorted(required - tools)
if missing:
    print("backend mist actuele tools: " + ", ".join(missing))
    raise SystemExit(1)
raise SystemExit(0)
PY
}

wait_for_backend_current() {
  local attempts="${1:-90}"
  for _ in $(seq 1 "$attempts"); do
    backend_is_current && return 0
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

refresh_local_backend_pid_file() {
  local backend_pid
  backend_pid="$(
    ps -eo pid=,args= \
      | awk '$2 ~ /python/ && index($0, " -m uvicorn controller.main:app --host 0.0.0.0 --port 8010") {print $1}' \
      | tail -n 1
  )"
  if [ -n "$backend_pid" ]; then
    echo "$backend_pid" > "$BACKEND_PID_FILE"
  fi
}

ensure_backend() {
  if [ "$BACKEND_REFRESH_REQUIRED" != "1" ] && backend_is_current; then
    refresh_local_backend_pid_file
    echo "Backend is al bereikbaar."
    return 0
  fi
  if [ "$BACKEND_MODE" != "local" ] && docker_available; then
    echo "Refreshing Docker backend and Chroma..."
    compose_up || {
      [ "$BACKEND_MODE" = "docker" ] && fail "Docker is bereikbaar, maar docker compose kon niet worden gestart."
      echo "Docker is bereikbaar, maar compose startte niet; probeer lokale backend fallback."
    }
    if wait_for_backend_current 90; then
      return 0
    fi
    [ "$BACKEND_MODE" = "docker" ] && fail "backend route $BACKEND_URL/health werd niet bereikbaar via Docker."
    echo "Docker backend werd niet bereikbaar; probeer lokale backend fallback."
  elif [ "$BACKEND_MODE" = "docker" ]; then
    fail "docker ontbreekt; WINTRIP_BACKEND_MODE=docker kan de backend niet starten."
  elif [ "$BACKEND_MODE" = "local" ]; then
    echo "Lokale backend mode actief; start lokale backend fallback."
  else
    echo "Docker CLI ontbreekt; probeer lokale backend fallback."
  fi
  ensure_local_backend
}

ensure_local_backend_python() {
  if [ -x "$LOCAL_BACKEND_PYTHON" ]; then
    return 0
  fi
  [ "${WINTRIP_BOOTSTRAP_LOCAL_BACKEND:-0}" = "1" ] || fail "lokale backend venv ontbreekt: $LOCAL_BACKEND_PYTHON. Zet WINTRIP_BOOTSTRAP_LOCAL_BACKEND=1 om deze automatisch te maken, of installeer Docker."
  local bootstrap_python=""
  if [ -x "$PYTHON311" ]; then
    bootstrap_python="$PYTHON311"
  elif command -v python3.11 >/dev/null 2>&1; then
    bootstrap_python="$(command -v python3.11)"
  else
    bootstrap_python="$(command -v python3)"
  fi
  echo "Lokale backend venv ontbreekt; bootstrap met $bootstrap_python..."
  "$bootstrap_python" -m venv "$LOCAL_BACKEND_VENV"
  "$LOCAL_BACKEND_PYTHON" -m pip install --upgrade pip
  "$LOCAL_BACKEND_PYTHON" -m pip install -r "$ROOT/controller/requirements.txt"
}

ensure_local_backend() {
  ensure_local_backend_python
  need_cmd setsid
  echo "Starting local Python backend on $BACKEND_URL..."
  (
    cd "$ROOT"
    setsid -f env \
      PYTHONPATH="$ROOT" \
      WINTRIP_WORKSPACE="$ROOT" \
      WINTRIP_HOST_WORKSPACE="$ROOT" \
      WINTRIP_DB_PATH="${WINTRIP_DB_PATH:-$ROOT/wintrip_brain}" \
      WINTRIP_CHROMA_HTTP_URL="${WINTRIP_CHROMA_HTTP_URL:-}" \
      WINTRIP_RCLONE_BRIDGE_URL="${WINTRIP_RCLONE_BRIDGE_URL_LOCAL:-$BRIDGE_URL}" \
      WINTRIP_RCLONE_BRIDGE_TOKEN_PATH="${WINTRIP_RCLONE_BRIDGE_TOKEN_PATH:-$TOKEN_PATH}" \
      OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}" \
      "$LOCAL_BACKEND_PYTHON" -m uvicorn controller.main:app --host 0.0.0.0 --port 8010 >"$BACKEND_LOG" 2>&1 < /dev/null
  )
  if wait_for_backend_current 90; then
    refresh_local_backend_pid_file
    echo "Local backend online."
    return 0
  fi
  tail -n 120 "$BACKEND_LOG" >&2 || true
  fail "lokale backend route $BACKEND_URL/health werd niet bereikbaar."
}

ensure_host_bridge() {
  local fallback_port
  if port_open 127.0.0.1 "$BRIDGE_PORT"; then
    if bridge_is_valid; then
      echo "Host bridge online."
      return 0
    fi
    echo "Host bridge op poort $BRIDGE_PORT is oud; herstarten voor actuele endpoints..."
    pkill -f "scripts/rclone_host_bridge.py.*--port $BRIDGE_PORT" >/dev/null 2>&1 || true
    for _ in $(seq 1 10); do
      port_open 127.0.0.1 "$BRIDGE_PORT" || break
      sleep 1
    done
    if port_open 127.0.0.1 "$BRIDGE_PORT"; then
      fallback_port="$(first_free_bridge_port)" || fail "poort $BRIDGE_PORT is bezet door een oude host bridge en er is geen vrije fallbackpoort gevonden."
      BRIDGE_PORT="$fallback_port"
      BRIDGE_URL="http://127.0.0.1:$BRIDGE_PORT"
      DOCKER_BRIDGE_URL="http://host.docker.internal:$BRIDGE_PORT"
      BACKEND_REFRESH_REQUIRED=1
      echo "Gebruik fallback host bridge op $BRIDGE_URL."
    fi
  fi
  [ -f "$ROOT/scripts/rclone_host_bridge.py" ] || fail "scripts/rclone_host_bridge.py ontbreekt."
  need_cmd setsid
  echo "Starting host bridge on $BRIDGE_URL..."
  (cd "$ROOT" && setsid -f python3 scripts/rclone_host_bridge.py --bind 0.0.0.0 --port "$BRIDGE_PORT" >"$LOG_DIR/host_bridge.log" 2>&1 < /dev/null)
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
  if ! python3 "$ROOT/scripts/doctor_ouroboros_runtime.py" \
    --backend-url "$BACKEND_URL" \
    --preview-url "$PREVIEW_URL" \
    --bridge-url "$BRIDGE_URL" \
    --smoke \
    --json; then
    if [ "$BACKEND_MODE" = "local" ] || ! docker_available; then
      echo "Runtime doctor is degraded, maar backend/preview/bridge zijn gestart. Docker runner blijft unavailable zonder Docker CLI." >&2
    else
      fail "runtime doctor smoke faalde."
    fi
  fi
  echo "Ouroboros preview ready: $PREVIEW_URL"
}

main "$@"
