#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

swift build -c release

APP_DIR="$SCRIPT_DIR/dist/PaperFlow.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
ENTITLEMENTS="$SCRIPT_DIR/PaperFlow.entitlements"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR"

cp "$SCRIPT_DIR/.build/release/PaperFlowApp" "$MACOS_DIR/PaperFlow"
cp "$SCRIPT_DIR/Info.plist" "$CONTENTS_DIR/Info.plist"
chmod +x "$MACOS_DIR/PaperFlow"

if [[ -n "${DEVELOPER_ID_APPLICATION:-}" ]]; then
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$DEVELOPER_ID_APPLICATION" "$APP_DIR"
  codesign --verify --deep --strict --verbose=2 "$APP_DIR"
  echo "Signed $APP_DIR with $DEVELOPER_ID_APPLICATION"
else
  codesign --force --sign - "$APP_DIR"
  echo "Ad-hoc signed $APP_DIR. Set DEVELOPER_ID_APPLICATION='Developer ID Application: ...' for distribution signing."
fi

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  ditto -c -k --keepParent "$APP_DIR" "$SCRIPT_DIR/dist/PaperFlow.zip"
  xcrun notarytool submit "$SCRIPT_DIR/dist/PaperFlow.zip" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$APP_DIR"
  echo "Notarized and stapled $APP_DIR"
fi

echo "Built $APP_DIR"
