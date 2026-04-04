#!/bin/bash
# Eenmalig uitvoeren: bash /Users/philip/WintripAI/create_mac_app.sh
# Daarna staat WintripAI.app op je bureaublad, sleep hem naar je Dock.

APP_NAME="WintripAI"
APP_DIR="$HOME/Desktop/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

mkdir -p "$MACOS" "$RESOURCES"

# ── Info.plist ────────────────────────────────────────────────────────────────
cat > "$CONTENTS/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>WintripAI</string>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>CFBundleIdentifier</key>
  <string>nl.wintrip.ai</string>
  <key>CFBundleVersion</key>
  <string>6.3</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>LSUIElement</key>
  <false/>
</dict>
</plist>
EOF

# ── Launch script ─────────────────────────────────────────────────────────────
cat > "$MACOS/launch" << 'EOF'
#!/bin/bash
cd /Users/philip/WintripAI
exec .venv/bin/python start_wintrip.py
EOF

chmod +x "$MACOS/launch"

# ── Icoon maken (simpel, werkt zonder Xcode) ──────────────────────────────────
# Maakt een blauw vierkant met "W" als tijdelijk icoon
python3 - << 'PYEOF'
import struct, zlib, os

def png(w, h, pixels):
    def chunk(name, data):
        c = zlib.crc32(name + data) & 0xffffffff
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', c)
    raw = b''.join(b'\x00' + bytes([p for px in row for p in px]) for row in pixels)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')

size = 512
bg = [30, 41, 59]
acc = [96, 165, 250]
pixels = [[bg[:] for _ in range(size)] for _ in range(size)]

# Cirkel
cx, cy, r = size//2, size//2, size//2 - 20
for y in range(size):
    for x in range(size):
        if (x-cx)**2 + (y-cy)**2 <= r**2:
            pixels[y][x] = acc[:]

# Letter W (simpel)
for y in range(180, 340):
    for x in range(140, 380):
        fy = (y-180)/160
        fx = (x-140)/240
        on = False
        if 0.05 < fx < 0.15 or 0.85 < fx < 0.95: on = True
        if 0.43 < fx < 0.57 and fy > 0.4: on = True
        lx = abs(fx - 0.3)
        rx = abs(fx - 0.7)
        if lx < 0.05 * (1 - fy) + 0.02: on = True
        if rx < 0.05 * (1 - fy) + 0.02: on = True
        if on:
            pixels[y][x] = [255, 255, 255]

iconset = os.path.expanduser("~/Desktop/WintripAI.app/Contents/Resources/AppIcon.iconset")
os.makedirs(iconset, exist_ok=True)
data = png(size, size, pixels)
for s in [16, 32, 64, 128, 256, 512]:
    open(f"{iconset}/icon_{s}x{s}.png", "wb").write(data)
    open(f"{iconset}/icon_{s}x{s}@2x.png", "wb").write(data)
PYEOF

# Converteer iconset naar .icns
iconset_path="$RESOURCES/AppIcon.iconset"
if [ -d "$iconset_path" ]; then
    iconutil -c icns "$iconset_path" -o "$RESOURCES/AppIcon.icns" 2>/dev/null
    rm -rf "$iconset_path"
fi

echo "✅  WintripAI.app staat op je bureaublad."
echo "   Sleep hem naar je Dock voor snelle toegang."
echo "   Dubbelklik om te starten — geen terminal nodig."