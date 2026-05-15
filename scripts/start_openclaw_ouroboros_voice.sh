#!/usr/bin/env bash
set -euo pipefail

VOICE_ROOT="${OPENCLAW_VOICE_ROOT:-/home/pwintri2/openclaw-voice}"
OUROBOROS_BACKEND_URL="${OUROBOROS_BACKEND_URL:-http://127.0.0.1:8010}"

if [[ ! -d "$VOICE_ROOT" ]]; then
  echo "OpenClaw Voice root not found: $VOICE_ROOT" >&2
  exit 1
fi

export OPENCLAW_HOST="${OPENCLAW_HOST:-127.0.0.1}"
export OPENCLAW_PORT="${OPENCLAW_PORT:-8765}"
export OPENCLAW_STT_MODEL="${OPENCLAW_STT_MODEL:-tiny}"
export OPENCLAW_STT_DEVICE="${OPENCLAW_STT_DEVICE:-cpu}"
export OPENCLAW_STT_LANGUAGE="${OPENCLAW_STT_LANGUAGE:-nl}"
export OPENCLAW_REQUIRE_AUTH="${OPENCLAW_REQUIRE_AUTH:-false}"
export OPENCLAW_GATEWAY_URL="${OPENCLAW_GATEWAY_URL:-${OUROBOROS_BACKEND_URL%/}/api/openclaw-voice}"
export OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-local-ouroboros-voice}"

cd "$VOICE_ROOT"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="${PYTHON:-python3}"
fi

deps_ready() {
  "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import fastapi
import numpy
import openai
import uvicorn
PY
}

if ! deps_ready; then
  if [[ "${OPENCLAW_AUTO_INSTALL:-1}" != "1" ]]; then
    cat >&2 <<EOF
OpenClaw Voice dependencies are not available for: $PYTHON_BIN

Create/install its environment first, for example:
  cd $VOICE_ROOT
  python3 -m venv .venv
  .venv/bin/pip install -e '.[stt]'

Then run this script again.
EOF
    exit 1
  fi

  if [[ ! -x ".venv/bin/python" ]]; then
    "${PYTHON:-python3}" -m venv .venv
  fi
  PYTHON_BIN=".venv/bin/python"
  echo "Installing OpenClaw Voice core + STT dependencies into $VOICE_ROOT/.venv ..."
  OPENCLAW_DEPS=(
    "fastapi>=0.109.0"
    "uvicorn[standard]>=0.27.0"
    "websockets>=12.0"
    "pydantic>=2.5.0"
    "pydantic-settings>=2.1.0"
    "numpy>=1.26.0"
    "openai>=1.6.0"
    "httpx>=0.26.0"
    "loguru>=0.7.2"
    "python-dotenv>=1.0.0"
    "faster-whisper>=1.0.0"
  )
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$PYTHON_BIN" "${OPENCLAW_DEPS[@]}"
  else
    "$PYTHON_BIN" -m pip install --upgrade pip
    "$PYTHON_BIN" -m pip install "${OPENCLAW_DEPS[@]}"
  fi
  deps_ready || {
    echo "OpenClaw Voice dependencies are still unavailable after install." >&2
    exit 1
  }
fi

cat <<EOF
OpenClaw Voice -> Ouroboros
  voice server: http://${OPENCLAW_HOST}:${OPENCLAW_PORT}
  websocket:    ws://${OPENCLAW_HOST}:${OPENCLAW_PORT}/ws
  gateway:      ${OPENCLAW_GATEWAY_URL}/v1/chat/completions
EOF

exec env PYTHONPATH="$VOICE_ROOT${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m uvicorn src.server.main:app --host "$OPENCLAW_HOST" --port "$OPENCLAW_PORT"
