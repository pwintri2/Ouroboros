#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

cargo build --release
mkdir -p dist/OuroborosProto1.app/Contents/MacOS
mkdir -p dist/OuroborosProto1.app/Contents/Resources
cp target/release/ouroboros_proto1 dist/OuroborosProto1.app/Contents/MacOS/OuroborosProto1
chmod +x dist/OuroborosProto1.app/Contents/MacOS/OuroborosProto1
cp packaging/macos/Info.plist dist/OuroborosProto1.app/Contents/Info.plist

ditto -c -k --sequesterRsrc --keepParent dist/OuroborosProto1.app dist/OuroborosProto1-macos.zip

echo "Built: dist/OuroborosProto1.app"
echo "Built: dist/OuroborosProto1-macos.zip"
