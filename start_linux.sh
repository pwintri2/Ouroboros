#!/usr/bin/env bash
# ============================================================
# start_linux.sh — Wintrip Grok op Linux/Pop!_OS
# ============================================================
# Gebruik:
#   chmod +x start_linux.sh
#   ./start_linux.sh
#
# Optionele flags:
#   --headless    Alleen de backend starten (geen GUI)
#   --no-install  Geen automatische dependency-installatie
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
ENV_FILE="$SCRIPT_DIR/.env"
HEADLESS=false
NO_INSTALL=false

# ── Argumenten ─────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --headless)   HEADLESS=true ;;
    --no-install) NO_INSTALL=true ;;
    *) echo "Onbekend argument: $arg"; exit 1 ;;
  esac
done

# ── Kleuren ────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERR ]${NC} $*"; }

# ── .env-check ─────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  warn ".env niet gevonden — kopieer .env copy naar .env en vul je XAI_API_KEY in."
  if [ -f "$SCRIPT_DIR/.env copy" ]; then
    cp "$SCRIPT_DIR/.env copy" "$ENV_FILE"
    warn ".env aangemaakt vanuit '.env copy'. Vul XAI_API_KEY in!"
  fi
fi

# ── Systeemafhankelijkheden (GTK4) ─────────────────────────
if [ "$NO_INSTALL" = false ] && [ "$HEADLESS" = false ]; then
  info "GTK4-afhankelijkheden controleren…"
  MISSING_APT=()
  for pkg in python3-gi gir1.2-gtk-4.0 gir1.2-adw-1; do
    dpkg -s "$pkg" &>/dev/null || MISSING_APT+=("$pkg")
  done
  if [ ${#MISSING_APT[@]} -gt 0 ]; then
    info "Ontbrekende pakketten installeren: ${MISSING_APT[*]}"
    sudo apt-get install -y "${MISSING_APT[@]}"
  fi
fi

# ── Python venv ────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  info "Virtuele omgeving aanmaken in $VENV_DIR …"
  python3 -m venv "$VENV_DIR" --system-site-packages
fi

# Activeer venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Python-afhankelijkheden ────────────────────────────────
if [ "$NO_INSTALL" = false ]; then
  info "Python-pakketten installeren/bijwerken…"
  pip install --quiet --upgrade pip
  pip install --quiet -r "$SCRIPT_DIR/controller/requirements.txt"
fi

# ── Backend starten ────────────────────────────────────────
info "Wintrip-backend starten op http://127.0.0.1:8000 …"
cd "$SCRIPT_DIR"

if [ "$HEADLESS" = true ]; then
  info "Headless modus — alleen backend."
  python -m uvicorn controller.main:app --host 127.0.0.1 --port 8000
else
  # Backend in achtergrond
  python -m uvicorn controller.main:app \
    --host 127.0.0.1 --port 8000 \
    --log-level warning &
  BACKEND_PID=$!
  info "Backend PID: $BACKEND_PID"

  # Wacht tot backend beschikbaar is (max 15 s)
  info "Wachten op backend…"
  for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
      info "Backend klaar!"
      break
    fi
    sleep 0.5
  done

  # ── GTK4-app starten ─────────────────────────────────────
  info "Wintrip Grok-app starten…"
  python linux_app/app.py --no-autostart || true

  # Ruim backend op als de app sluit
  info "App gesloten — backend stoppen (PID $BACKEND_PID)…"
  kill "$BACKEND_PID" 2>/dev/null || true
fi
