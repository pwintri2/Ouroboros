#!/usr/bin/env bash
set -euo pipefail

ROOT="${WINTRIP_ROOT:-/home/pwintri2/WintripAI}"
LAUNCHER="$ROOT/scripts/start_ouroboros_cockpit.sh"
ICON="$ROOT/ouroboros_cockpit/src-tauri/icons/icon.png"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APP_DIR/ouroboros-cockpit.desktop"

if [ ! -x "$LAUNCHER" ]; then
  chmod +x "$LAUNCHER"
fi

mkdir -p "$APP_DIR"
cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Ouroboros Cockpit
GenericName=WintripAI Agent Cockpit
Comment=Start de native WintripAI Ouroboros cockpit
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Development;
StartupNotify=true
StartupWMClass=ai.wintrip.ouroboros-cockpit
X-GNOME-UsesNotifications=true
EOF

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "$DESKTOP_FILE"
