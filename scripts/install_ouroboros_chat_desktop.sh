#!/usr/bin/env bash
set -euo pipefail

ROOT="${WINTRIP_ROOT:-/home/pwintri2/WintripAI}"
CHAT_DIR="${OUROBOROS_CHAT_DIR:-/home/pwintri2/ouroboros-chat}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
ENTRY="$DESKTOP_DIR/ouroboros-chat.desktop"
ICON_NAME="ouroboros-chat"

mkdir -p "$DESKTOP_DIR"
install -Dm644 "$CHAT_DIR/src-tauri/icons/32x32.png" "$ICON_DIR/32x32/apps/$ICON_NAME.png"
install -Dm644 "$CHAT_DIR/src-tauri/icons/128x128.png" "$ICON_DIR/128x128/apps/$ICON_NAME.png"
install -Dm644 "$CHAT_DIR/src-tauri/icons/128x128@2x.png" "$ICON_DIR/256x256@2/apps/$ICON_NAME.png"
install -Dm644 "$CHAT_DIR/src-tauri/icons/icon.png" "$ICON_DIR/1024x1024/apps/$ICON_NAME.png"

cat >"$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=Ouroboros Chat
Comment=Start de standalone Ouroboros Chat Tauri UI
Exec=$ROOT/scripts/start_ouroboros_chat.sh
Icon=$ICON_NAME
Terminal=false
Categories=Development;
StartupNotify=true
StartupWMClass=ouroboros-chat
X-GNOME-UsesNotifications=true
EOF

chmod +x "$ENTRY"
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$ICON_DIR" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
echo "Installed $ENTRY"
