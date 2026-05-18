#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

echo "🚀 Ouroboros AI Agent wordt opgestart..."

if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Virtuele omgeving ontbreekt; .venv wordt aangemaakt..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r "$ROOT_DIR/controller/requirements.txt"

# 1. Start Python Backend (Controller)
cd "$ROOT_DIR/controller" || exit

# PYTHONPATH instellen
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

# Start de FastAPI server
python3 -m uvicorn main:app --reload &BACKEND_PID=$!
echo "✅ Python Backend gestart op http://127.0.0.1:8000 (PID: $BACKEND_PID)"

# 2. Opschonen bij afsluiten (Ctrl+C)
cleanup() {
    echo ""
    echo "🛑 Ouroboros AI wordt afgesloten..."
    # Stop de backend uvicorn server
    kill $BACKEND_PID 2>/dev/null
    exit 0
}

# Vang signalen op voor een nette afsluiting (SIGINT voor Ctrl+C, SIGTERM voor processtop)
trap cleanup SIGINT SIGTERM EXIT

# 3. Wacht tot de server online is
echo "⏳ Wachten op backend initialisatie..."
sleep 2

# 4. Start SwiftUI Regiekamer (Frontend)
echo "🖥️  SwiftUI Regiekamer wordt geladen via Swift Run..."
cd ../regiekamer || exit
# Swift run start de SwiftUI app als executable
swift run

# Houd het script actief totdat de Swift app stopt
wait $BACKEND_PID
