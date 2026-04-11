#!/bin/bash
set -euo pipefail
# Wintrip AI Launcher — Dubbelklik om te starten (no-terminal)
cd "$(dirname "$0")"

# Start OrbStack if available
open -a OrbStack >/dev/null 2>&1 || true
sleep 5

# Build webui if dependencies are available and the project exists
if [ -d "webui" ] && command -v npm >/dev/null 2>&1; then
  if [ ! -d "webui/node_modules" ]; then
    (cd webui && npm install)
  fi
  (cd webui && npm run build)
fi

# Start docker-compose in background
docker compose up --build -d 2>/dev/null || docker-compose up --build -d 2>/dev/null

echo "Starting Wintrip AI services..."

# Wait for health endpoint
for i in $(seq 1 60); do
  if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Open default browser
open "http://localhost:8080"

exit 0
