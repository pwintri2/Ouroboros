#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

API_URL="${AWAKE_KEEPER_API_URL:-http://127.0.0.1:7861}"
export AWAKE_KEEPER_API_URL="$API_URL"

PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" - <<'PY'
import importlib.util
import sys

missing = []
if importlib.util.find_spec("customtkinter") is None:
    missing.append("customtkinter")
if importlib.util.find_spec("tkinter") is None:
    missing.append("tkinter / python3-tk")
if missing:
    print("Missing desktop UI dependency: " + ", ".join(missing), file=sys.stderr)
    print("Install customtkinter with: python3 -m pip install -r goose_like_ui/requirements.txt", file=sys.stderr)
    print("Install Tk from your OS package manager if tkinter is missing.", file=sys.stderr)
    raise SystemExit(1)
PY

exec "$PYTHON_BIN" "$SCRIPT_DIR/awake_keeper_goose_ui.py"
