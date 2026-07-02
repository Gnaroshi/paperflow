#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

swift build -c release

APP_DIR="$SCRIPT_DIR/dist/PaperFlow.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
ENTITLEMENTS="$SCRIPT_DIR/PaperFlow.entitlements"
ZIP_PATH="$SCRIPT_DIR/dist/PaperFlow.zip"
DMG_STAGE="$SCRIPT_DIR/dist/dmg-stage"
DMG_PATH="$SCRIPT_DIR/dist/PaperFlow.dmg"

package_archives() {
  COPYFILE_DISABLE=1 ditto --norsrc --noextattr -c -k --keepParent "$APP_DIR" "$ZIP_PATH"
  echo "Packaged $ZIP_PATH"

  if command -v hdiutil >/dev/null 2>&1; then
    rm -rf "$DMG_STAGE" "$DMG_PATH"
    mkdir -p "$DMG_STAGE"
    COPYFILE_DISABLE=1 ditto --norsrc --noextattr "$APP_DIR" "$DMG_STAGE/PaperFlow.app"
    ln -s /Applications "$DMG_STAGE/Applications"
    hdiutil create -volname "PaperFlow" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG_PATH" >/dev/null
    rm -rf "$DMG_STAGE"
    echo "Packaged $DMG_PATH"
  else
    echo "hdiutil not found; skipped DMG packaging."
  fi
}

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR"

cp "$SCRIPT_DIR/.build/release/PaperFlowApp" "$MACOS_DIR/PaperFlow"
cp "$SCRIPT_DIR/Info.plist" "$CONTENTS_DIR/Info.plist"
chmod +x "$MACOS_DIR/PaperFlow"

if [[ -n "${DEVELOPER_ID_APPLICATION:-}" ]]; then
  if [[ "$DEVELOPER_ID_APPLICATION" != Developer\ ID\ Application:* ]]; then
    echo "DEVELOPER_ID_APPLICATION should be a Developer ID Application identity for public distribution." >&2
    echo "Current value: $DEVELOPER_ID_APPLICATION" >&2
    if [[ -n "${NOTARY_PROFILE:-}" ]]; then
      echo "Refusing notarization with a non-Developer-ID signing identity." >&2
      exit 2
    fi
  fi
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$DEVELOPER_ID_APPLICATION" "$APP_DIR"
  codesign --verify --deep --strict --verbose=2 "$APP_DIR"
  echo "Signed $APP_DIR with $DEVELOPER_ID_APPLICATION"
else
  codesign --force --sign - "$APP_DIR"
  echo "Ad-hoc signed $APP_DIR. Set DEVELOPER_ID_APPLICATION='Developer ID Application: ...' for distribution signing."
fi

package_archives

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  if [[ -z "${DEVELOPER_ID_APPLICATION:-}" ]]; then
    echo "NOTARY_PROFILE requires DEVELOPER_ID_APPLICATION='Developer ID Application: ...'." >&2
    exit 2
  fi
  xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$APP_DIR"
  package_archives
  if [[ -f "$DMG_PATH" ]]; then
    xcrun notarytool submit "$DMG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG_PATH"
  fi
  echo "Notarized and stapled $APP_DIR"
fi

echo "Built $APP_DIR"
