#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

swift build -c release

APP_DIR="$SCRIPT_DIR/dist/PaperFlow.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
ENTITLEMENTS="$SCRIPT_DIR/PaperFlow.entitlements"
ZIP_PATH="$SCRIPT_DIR/dist/PaperFlow.zip"
DMG_STAGE="$SCRIPT_DIR/dist/dmg-stage"
DMG_PATH="$SCRIPT_DIR/dist/PaperFlow.dmg"
APP_VERSION="$(python3 -c 'import pathlib,tomllib; print(tomllib.loads(pathlib.Path("../pyproject.toml").read_text())["project"]["version"])')"
BUILD_NUMBER="$(git -C "$SCRIPT_DIR/.." rev-list --count HEAD)"
GIT_COMMIT="$(git -C "$SCRIPT_DIR/.." rev-parse HEAD)"
GIT_DIRTY=false
if [[ -n "$(git -C "$SCRIPT_DIR/.." status --porcelain)" ]]; then
  GIT_DIRTY=true
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
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

cp "$SCRIPT_DIR/.build/release/PaperFlowApp" "$MACOS_DIR/PaperFlow"
cp "$SCRIPT_DIR/Info.plist" "$CONTENTS_DIR/Info.plist"
cp "$SCRIPT_DIR/../identity/app-icon/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
cp "$SCRIPT_DIR/../gnaroshi.app.json" "$RESOURCES_DIR/gnaroshi.app.json"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$CONTENTS_DIR/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$CONTENTS_DIR/Info.plist"
python3 - "$RESOURCES_DIR/build-provenance.json" "$APP_VERSION" "$BUILD_NUMBER" "$GIT_COMMIT" "$GIT_DIRTY" <<'PY'
import json
import pathlib
import sys

path, version, number, commit, dirty = sys.argv[1:]
pathlib.Path(path).write_text(
    json.dumps(
        {
            "schemaVersion": 1,
            "version": version,
            "buildNumber": int(number),
            "commit": commit,
            "dirty": dirty == "true",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY
chmod +x "$MACOS_DIR/PaperFlow"

SIGNING_MODE="${SIGNING_MODE:-development}"
if [[ "$SIGNING_MODE" == "release" && "$GIT_DIRTY" == "true" ]]; then
  echo "Release packaging requires a clean Git checkout." >&2
  exit 2
fi
if [[ "$SIGNING_MODE" == "release" ]]; then
  if [[ -z "${DEVELOPER_ID_APPLICATION:-}" ]]; then
    DEVELOPER_ID_APPLICATION="$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -1)"
  fi
  if [[ -z "$DEVELOPER_ID_APPLICATION" ]]; then
    echo "A Developer ID Application identity is required for release builds." >&2
    exit 2
  fi
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
  LOCAL_SIGNING_IDENTITY="${LOCAL_SIGNING_IDENTITY:-$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -1)}"
  if [[ -z "$LOCAL_SIGNING_IDENTITY" ]]; then
    LOCAL_SIGNING_IDENTITY="${APPLE_DEVELOPMENT_IDENTITY:-$(security find-identity -v -p codesigning | sed -n 's/.*"\(Apple Development:[^"]*\)".*/\1/p' | head -1)}"
  fi
  if [[ -z "$LOCAL_SIGNING_IDENTITY" ]]; then
    if [[ "${ALLOW_AD_HOC_SIGNING:-0}" != "1" ]]; then
      echo "An Apple Development identity is required for a permission-stable local app." >&2
      echo "Set ALLOW_AD_HOC_SIGNING=1 only for isolated packaging tests." >&2
      exit 2
    fi
    codesign --force --sign - "$APP_DIR"
    echo "Ad-hoc signed $APP_DIR for an explicitly allowed packaging test."
  else
    codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$LOCAL_SIGNING_IDENTITY" "$APP_DIR"
    codesign --verify --deep --strict --verbose=2 "$APP_DIR"
    echo "Signed $APP_DIR with $LOCAL_SIGNING_IDENTITY"
  fi
fi

package_archives

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  if [[ "$SIGNING_MODE" != "release" ]]; then
    echo "NOTARY_PROFILE requires SIGNING_MODE=release." >&2
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
echo "Version $APP_VERSION ($BUILD_NUMBER), commit $GIT_COMMIT, dirty $GIT_DIRTY"
