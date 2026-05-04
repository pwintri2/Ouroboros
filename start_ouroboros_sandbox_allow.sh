#!/usr/bin/env bash
# Start the Ouroboros backend inside the existing Docker sandbox with allow env.
#
# Purpose:
#   Load artifacts/ouroboros_sandbox_allow.env and run Uvicorn in the
#   wintrip-standalone-ui container.
# Inputs:
#   Existing Docker container `wintrip-standalone-ui` with /workspace mounted to
#   this repository.
# Outputs:
#   Backend on http://localhost:8010 and logs in artifacts/backend_sandbox_allow.log.
# Safety notes:
#   The env file contains no secrets. It enables live adapter attempts, but the
#   adapters still redact outputs and report missing token files honestly.
# Akkoord requirements:
#   This script is for the sandbox mode Philip approved on 2026-05-02.
#
# Why this change:
#   The container command is `sleep infinity`, so a restart does not
#   automatically relaunch the backend or carry the allow env.

set -euo pipefail

CONTAINER="${WINTRIP_CONTAINER:-wintrip-standalone-ui}"
BRIDGE_PORT="${WINTRIP_RCLONE_BRIDGE_PORT:-8766}"
BRIDGE_HOST_IP="${WINTRIP_RCLONE_BRIDGE_HOST_IP:-}"
HOST_BRIDGE_PYTHON="${WINTRIP_HOST_BRIDGE_PYTHON:-}"
if [ -z "${HOST_BRIDGE_PYTHON}" ] && [ -x ".venv_world_agent/bin/python" ]; then
  HOST_BRIDGE_PYTHON=".venv_world_agent/bin/python"
fi
HOST_BRIDGE_PYTHON="${HOST_BRIDGE_PYTHON:-python3}"

mkdir -p .secrets artifacts
if [ ! -s .secrets/rclone_bridge_token ]; then
  python3 - <<'PY'
from pathlib import Path
import secrets
p = Path(".secrets/rclone_bridge_token")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(secrets.token_urlsafe(32), encoding="utf-8")
p.chmod(0o600)
PY
fi

bridge_endpoint_ready() {
  python3 - "$BRIDGE_PORT" <<'PY'
from pathlib import Path
import sys
import urllib.request

port = sys.argv[1]
try:
    token = Path(".secrets/rclone_bridge_token").read_text(encoding="utf-8").strip()
    for path in ("/agents/status", "/world/status"):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            headers={"X-Ouroboros-Bridge-Token": token},
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status != 200:
                raise SystemExit(1)
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
}

bridge_uses_expected_python() {
  if [ "${HOST_BRIDGE_PYTHON}" = "python3" ]; then
    return 0
  fi
  pgrep -af "[r]clone_host_bridge.py" | grep -F -- "${HOST_BRIDGE_PYTHON}" >/dev/null 2>&1
}

if pgrep -f "[r]clone_host_bridge.py" >/dev/null 2>&1 && { ! bridge_endpoint_ready || ! bridge_uses_expected_python; }; then
  pkill -f "[r]clone_host_bridge.py" || true
  sleep 0.5
fi

if ! pgrep -f "[r]clone_host_bridge.py" >/dev/null 2>&1; then
  setsid -f "${HOST_BRIDGE_PYTHON}" scripts/rclone_host_bridge.py --bind 0.0.0.0 --port "${BRIDGE_PORT}" \
    > artifacts/rclone_host_bridge.log 2>&1
fi

if [ -z "${BRIDGE_HOST_IP}" ]; then
  for candidate in $(hostname -I 2>/dev/null || printf '172.17.0.1'); do
    if docker exec -w /workspace "${CONTAINER}" sh -lc "python3 - <<'PY'
from pathlib import Path
import sys
import urllib.request
token = Path('/workspace/.secrets/rclone_bridge_token').read_text(encoding='utf-8').strip()
req = urllib.request.Request('http://${candidate}:${BRIDGE_PORT}/status', headers={'X-Ouroboros-Bridge-Token': token})
try:
    with urllib.request.urlopen(req, timeout=2) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY"; then
      BRIDGE_HOST_IP="${candidate}"
      break
    fi
  done
fi

BRIDGE_HOST_IP="${BRIDGE_HOST_IP:-172.17.0.1}"

docker exec -w /workspace "${CONTAINER}" sh -lc '
  if [ -f /tmp/wintrip_backend.pid ]; then
    kill "$(cat /tmp/wintrip_backend.pid)" 2>/dev/null || true
  fi
  set -a
  . /workspace/artifacts/ouroboros_sandbox_allow.env
  set +a
  export WINTRIP_RCLONE_BRIDGE_URL="http://'"${BRIDGE_HOST_IP}:${BRIDGE_PORT}"'"
  export WINTRIP_RCLONE_BRIDGE_TOKEN_PATH="/workspace/.secrets/rclone_bridge_token"
  nohup uvicorn controller.main:app --host 0.0.0.0 --port 8010 \
    > /workspace/artifacts/backend_sandbox_allow.log 2>&1 &
  echo $! > /tmp/wintrip_backend.pid
'

echo "Ouroboros backend started with sandbox allow env on http://localhost:8010"
