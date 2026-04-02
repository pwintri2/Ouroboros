#!/bin/bash
# WintripAI/start.sh - Universeel Start-Script voor de Wintrip AI-agent

echo "🚀 Wintrip AI Agent wordt opgestart..."

# 1. Start Python Backend (Controller)
cd "$(dirname "$0")/controller" || exit

# Activeer de virtuele omgeving
source ../.venv/bin/activate

# PYTHONPATH instellen
export PYTHONPATH=$PYTHONPATH:$(pwd)/..

# Start de FastAPI server
python3 -m uvicorn main:app --reload &BACKEND_PID=$!
echo "✅ Python Backend gestart op http://127.0.0.1:8000 (PID: $BACKEND_PID)"

# 2. Opschonen bij afsluiten (Ctrl+C)
cleanup() {
    echo ""
    echo "🛑 Wintrip AI wordt afgesloten..."
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
