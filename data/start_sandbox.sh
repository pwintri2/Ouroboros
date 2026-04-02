#!/bin/bash
# Wintrip Sandbox Start Script

# Navigeer naar de project root
PROJECT_ROOT="/Users/philip/wintripai"
cd "$PROJECT_ROOT"

# Stel PYTHONPATH in zodat de controller module gevonden kan worden
export PYTHONPATH=$PYTHONPATH:"$PROJECT_ROOT"

# Activeer de virtuele omgeving
source .venv/bin/activate

# Start de sandbox versie van de server
echo "[WINTRIP] Starten van de Sandbox FastAPI server..."
python3 data/main_sandbox.py
