#!/bin/sh
set -eu

cd "$(dirname "$0")"
mkdir -p data/chromadb data/screenshots

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not available in this terminal." >&2
  exit 127
fi

echo "Starting Resonant Ouroboros Proto 1.1 Fase 1 in Docker..."
echo "Workspace mount: $(pwd) -> /workspace"
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 up --build -d
echo "Dashboard: http://localhost:7860"
echo "ChromaDB:  http://localhost:8000"
