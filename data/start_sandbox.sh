#!/bin/bash
set -euo pipefail
# Wintrip Sandbox Start Script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${WINTRIP_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

cd "$PROJECT_ROOT"

# Stel PYTHONPATH in zodat de controller module gevonden kan worden
export PYTHONPATH="${PYTHONPATH:-}:$PROJECT_ROOT"

# Activeer de virtuele omgeving indien aanwezig
if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# Start de sandbox versie van de server
echo "[WINTRIP] Starten van de Sandbox FastAPI server..."
python3 data/main_sandbox.py
