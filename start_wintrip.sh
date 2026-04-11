#!/bin/bash
set -euo pipefail
# Wintrip Start Script - Geoptimaliseerd voor FastAPI

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${WINTRIP_PROJECT_ROOT:-$SCRIPT_DIR}"

cd "$PROJECT_ROOT"

# Stel PYTHONPATH in zodat de controller module gevonden kan worden
export PYTHONPATH="${PYTHONPATH:-}:$PROJECT_ROOT"

# Activeer de virtuele omgeving indien deze bestaat
if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# Start de server
echo "[WINTRIP] Starten van de Wintrip Controller API..."
python3 controller/main.py
