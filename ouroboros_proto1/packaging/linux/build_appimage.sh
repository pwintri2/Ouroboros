#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

cargo build --release
mkdir -p dist
rm -rf AppDir
mkdir -p AppDir/usr/bin
cp target/release/ouroboros_proto1 AppDir/usr/bin/ouroboros_proto1
chmod +x AppDir/usr/bin/ouroboros_proto1
cp packaging/linux/ouroboros_proto1.desktop AppDir/ouroboros_proto1.desktop
cp packaging/linux/ouroboros_proto1.svg AppDir/ouroboros_proto1.svg
cp packaging/linux/ouroboros_proto1.svg AppDir/.DirIcon

cat > AppDir/AppRun << 'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/ouroboros_proto1" "$@"
EOF
chmod +x AppDir/AppRun

wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 ./appimagetool-x86_64.AppImage AppDir dist/OuroborosProto1-x86_64.AppImage

mkdir -p dist/linux_desktop_package
cp target/release/ouroboros_proto1 dist/linux_desktop_package/
cp packaging/linux/ouroboros_proto1.desktop dist/linux_desktop_package/
cp packaging/linux/ouroboros_proto1.svg dist/linux_desktop_package/
tar -czf dist/OuroborosProto1-linux-desktop.tar.gz -C dist linux_desktop_package

echo "Built: dist/OuroborosProto1-x86_64.AppImage"
echo "Built: dist/OuroborosProto1-linux-desktop.tar.gz"
