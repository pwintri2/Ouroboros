#!/bin/bash
echo "--- WintripAI VPS Initialisatie ---"

# Dwing de juiste Docker context en fallback via DOCKER_HOST
docker context use vps-wintrip 2>/dev/null || echo "⚠️ Kon 'vps-wintrip' context niet selecteren. Zorg dat deze bestaat in ~/.docker/contexts/"
export DOCKER_HOST="ssh://root@87.106.137.223"

# Test de verbinding
if docker ps >/dev/null 2>&1; then
    echo "✅ Verbinding met Strato VPS (87.106.137.223) is ACTIEF."
    echo "Docker commando's worden nu uitgevoerd op de VPS."
else
    echo "❌ FOUT: Kan geen verbinding maken met de VPS."
    echo "Check op macOS of je terminal Full Disk Access heeft als je 'Operation not permitted' krijgt."
    echo "Check ook of je SSH-sleutel is toegevoegd via: ssh-copy-id root@87.106.137.223"
    exit 1
fi
