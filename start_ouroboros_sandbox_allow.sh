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

docker exec -w /workspace "${CONTAINER}" sh -lc '
  if [ -f /tmp/wintrip_backend.pid ]; then
    kill "$(cat /tmp/wintrip_backend.pid)" 2>/dev/null || true
  fi
  set -a
  . /workspace/artifacts/ouroboros_sandbox_allow.env
  set +a
  nohup uvicorn controller.main:app --host 0.0.0.0 --port 8010 \
    > /workspace/artifacts/backend_sandbox_allow.log 2>&1 &
  echo $! > /tmp/wintrip_backend.pid
'

echo "Ouroboros backend started with sandbox allow env on http://localhost:8010"
