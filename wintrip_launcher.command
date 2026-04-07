#!/bin/bash
# Wintrip AI Launcher — Dubbelklik om te starten (no-terminal)
cd "$(dirname "$0")"

# Start docker-compose in background
docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null

echo "Starting Wintrip AI services..."

# Wait for health endpoint
for i in $(seq 1 30); do
  if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Open default browser
open "http://localhost:8000"

exit 0
