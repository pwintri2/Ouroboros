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

# Controleer of de minimale backend dependencies beschikbaar zijn
if ! python3 -c "import fastapi, uvicorn, dotenv, docker" >/dev/null 2>&1; then
    echo "[WINTRIP FOUT] Vereiste Python packages ontbreken in deze omgeving."
    echo "Voer uit:"
    echo "  source .venv/bin/activate"
    echo "  python -m pip install -r controller/requirements.txt"
    exit 1
fi

# Start de server
echo "[WINTRIP] Starten van de Wintrip Controller API..."
python3 controller/main.py
