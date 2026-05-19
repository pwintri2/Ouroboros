#!/usr/bin/env bash
set -euo pipefail

ROOT="${WINTRIP_ROOT:-/home/pwintri2/WintripAI}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ENTRY="$DESKTOP_DIR/ouroboros-chat.desktop"
ICON="$ROOT/ouroboros_cockpit/src-tauri/icons/icon.png"

mkdir -p "$DESKTOP_DIR"

cat >"$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=Ouroboros Chat
Comment=Start de standalone Ouroboros Chat Tauri UI
Exec=$ROOT/scripts/start_ouroboros_chat.sh
Icon=$ICON
Terminal=false
Categories=Development;Utility;
StartupNotify=true
EOF

chmod +x "$ENTRY"
echo "Installed $ENTRY"
