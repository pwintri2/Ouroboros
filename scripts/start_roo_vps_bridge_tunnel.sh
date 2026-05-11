#!/bin/sh
# Start a reverse SSH tunnel so the VPS backend can reach the laptop Roo bridge.

set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .secrets/vps.env ]; then
  set -a
  . .secrets/vps.env
  set +a
fi

HOST="${WINTRIP_VPS_SSH_ALIAS:-${WINTRIP_VPS_HOST:-}}"
USER="${WINTRIP_VPS_USER:-}"
LOCAL_PORT="${WINTRIP_LOCAL_RCLONE_BRIDGE_PORT:-8766}"
REMOTE_PORT="${WINTRIP_VPS_ROO_BRIDGE_PORT:-18766}"
PIDFILE=".secrets/ouroboros_roo_bridge_tunnel.pid"

if [ -z "$HOST" ]; then
  echo "missing WINTRIP_VPS_HOST or WINTRIP_VPS_SSH_ALIAS" >&2
  exit 2
fi

mkdir -p .secrets

if [ -s "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running: pid=$(cat "$PIDFILE")"
  exit 0
fi

LOGIN="$HOST"
if [ -n "$USER" ]; then
  LOGIN="$USER@$HOST"
fi

PORT_ARGS=""
if [ -n "${WINTRIP_VPS_PORT:-}" ]; then
  PORT_ARGS="-p ${WINTRIP_VPS_PORT}"
fi

ssh -f -N \
  -o ExitOnForwardFailure=yes \
  -o BatchMode=yes \
  -o PasswordAuthentication=no \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  $PORT_ARGS \
  -R "0.0.0.0:${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}" \
  "$LOGIN"

PID="$(pgrep -f "ssh .*${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}" | tail -n 1 || true)"
if [ -n "$PID" ]; then
  echo "$PID" > "$PIDFILE"
fi

echo "started Roo VPS bridge tunnel: local 127.0.0.1:${LOCAL_PORT} -> VPS 127.0.0.1:${REMOTE_PORT}"
