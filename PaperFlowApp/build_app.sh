#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

swift build -c release

APP_DIR="$SCRIPT_DIR/dist/PaperFlow.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR"

cp "$SCRIPT_DIR/.build/release/PaperFlowApp" "$MACOS_DIR/PaperFlow"
cp "$SCRIPT_DIR/Info.plist" "$CONTENTS_DIR/Info.plist"
chmod +x "$MACOS_DIR/PaperFlow"

echo "Built $APP_DIR"
