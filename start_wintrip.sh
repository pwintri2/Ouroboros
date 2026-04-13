#!/bin/bash
# Wintrip Start Script - Geoptimaliseerd voor FastAPI

# Navigeer naar de project root (map waar dit script staat)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# Stel PYTHONPATH in zodat de controller module gevonden kan worden
export PYTHONPATH=$PYTHONPATH:"$PROJECT_ROOT"

# Activeer de virtuele omgeving indien deze bestaat
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Start de server
echo "[WINTRIP] Starten van de Wintrip Controller API..."
python3 controller/main.py
