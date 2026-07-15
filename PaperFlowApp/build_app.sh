#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -z "${DEVELOPER_DIR:-}" && -d /Applications/Xcode.app/Contents/Developer ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi

export CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-$SCRIPT_DIR/.build/module-cache/clang}"
export SWIFTPM_MODULECACHE_OVERRIDE="${SWIFTPM_MODULECACHE_OVERRIDE:-$SCRIPT_DIR/.build/module-cache/swiftpm}"
mkdir -p "$CLANG_MODULE_CACHE_PATH" "$SWIFTPM_MODULECACHE_OVERRIDE"

swift build -c release

APP_DIR="$SCRIPT_DIR/dist/PaperFlow.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
ENTITLEMENTS="$SCRIPT_DIR/PaperFlow.entitlements"
ZIP_PATH="$SCRIPT_DIR/dist/PaperFlow.zip"
DMG_STAGE="$SCRIPT_DIR/dist/dmg-stage"
DMG_PATH="$SCRIPT_DIR/dist/PaperFlow.dmg"

find_signing_identity() {
  local identities identity
  identities="$(security find-identity -v -p codesigning 2>/dev/null || true)"
  identity="$(
    printf '%s\n' "$identities" \
      | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' \
      | head -n 1
  )"
  if [[ -n "$identity" ]]; then
    printf '%s\n' "$identity"
    return
  fi
  printf '%s\n' "$identities" \
    | sed -n 's/.*"\(Apple Development:[^"]*\)".*/\1/p' \
    | head -n 1
}

SIGNING_IDENTITY="${PAPERFLOW_SIGNING_IDENTITY:-${DEVELOPER_ID_APPLICATION:-}}"
if [[ -z "$SIGNING_IDENTITY" ]]; then
  SIGNING_IDENTITY="$(find_signing_identity)"
fi

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

if [[ -n "$SIGNING_IDENTITY" ]]; then
  if [[ "$SIGNING_IDENTITY" != Developer\ ID\ Application:* ]]; then
    echo "Using $SIGNING_IDENTITY for stable local signing." >&2
    echo "Public distribution still requires a Developer ID Application identity." >&2
    if [[ -n "${NOTARY_PROFILE:-}" ]]; then
      echo "Refusing notarization with a non-Developer-ID signing identity." >&2
      exit 2
    fi
  fi
  if [[ "$SIGNING_IDENTITY" == Developer\ ID\ Application:* ]]; then
    codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$SIGNING_IDENTITY" "$APP_DIR"
  else
    codesign --force --timestamp=none --options runtime --entitlements "$ENTITLEMENTS" --sign "$SIGNING_IDENTITY" "$APP_DIR"
  fi
  codesign --verify --deep --strict --verbose=2 "$APP_DIR"
  echo "Signed $APP_DIR with $SIGNING_IDENTITY"
else
  codesign --force --sign - "$APP_DIR"
  echo "WARNING: ad-hoc signing changes identity after every rebuild." >&2
  echo "Keychain and Desktop access prompts can repeat until an Apple signing certificate is installed." >&2
  echo "Set PAPERFLOW_SIGNING_IDENTITY or install an Apple Development/Developer ID certificate in Xcode." >&2
fi

package_archives

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  if [[ "$SIGNING_IDENTITY" != Developer\ ID\ Application:* ]]; then
    echo "NOTARY_PROFILE requires a Developer ID Application signing identity." >&2
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
