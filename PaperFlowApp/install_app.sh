#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_SRC="$SCRIPT_DIR/dist/PaperFlow.app"
INSTALL_DIR="${INSTALL_DIR:-/Applications}"
APP_DST="$INSTALL_DIR/PaperFlow.app"
APP_STAGE="$INSTALL_DIR/.PaperFlow.app.install.$$"
APP_BACKUP="$INSTALL_DIR/.PaperFlow.app.backup"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  "$SCRIPT_DIR/build_app.sh"
elif [[ ! -d "$APP_SRC" ]]; then
  echo "SKIP_BUILD=1 requires an existing bundle at $APP_SRC" >&2
  exit 2
fi

mkdir -p "$INSTALL_DIR"

case "$APP_DST" in
  */PaperFlow.app) ;;
  *)
    echo "Refusing to install to unexpected path: $APP_DST" >&2
    exit 2
    ;;
esac

if pgrep -f "^$APP_DST/Contents/MacOS/PaperFlow$" >/dev/null 2>&1; then
  echo "PaperFlow is still running from $APP_DST" >&2
  echo "Finish any active operation, quit PaperFlow normally, and run this installer again." >&2
  exit 3
fi

SOURCE_PROVENANCE="$APP_SRC/Contents/Resources/build-provenance.json"
if [[ ! -f "$SOURCE_PROVENANCE" ]]; then
  echo "Refusing to install a bundle without build-provenance.json" >&2
  exit 2
fi

SOURCE_COMMIT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$SOURCE_PROVENANCE")"
SOURCE_DIRTY="$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["dirty"]).lower())' "$SOURCE_PROVENANCE")"
CURRENT_COMMIT="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
if [[ "$SOURCE_COMMIT" != "$CURRENT_COMMIT" ]]; then
  echo "Refusing to install a stale bundle: source commit $SOURCE_COMMIT, checkout $CURRENT_COMMIT" >&2
  exit 2
fi
if [[ "$SOURCE_DIRTY" != "false" ]]; then
  echo "Refusing to install a dirty-provenance bundle. Commit the validated source first." >&2
  exit 2
fi

codesign --verify --deep --strict --verbose=2 "$APP_SRC"
SOURCE_ID="$(codesign -dv --verbose=4 "$APP_SRC" 2>&1 | sed -n 's/^Identifier=//p')"
SOURCE_TEAM="$(codesign -dv --verbose=4 "$APP_SRC" 2>&1 | sed -n 's/^TeamIdentifier=//p')"
SOURCE_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_SRC/Contents/Info.plist")"
SOURCE_BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_SRC/Contents/Info.plist")"
SOURCE_HASH="$(shasum -a 256 "$APP_SRC/Contents/MacOS/PaperFlow" | awk '{print $1}')"
if [[ "$SOURCE_ID" != "com.paperflow.app" || -z "$SOURCE_TEAM" ]]; then
  echo "Refusing unexpected app identity: id=$SOURCE_ID team=$SOURCE_TEAM" >&2
  exit 2
fi

rm -rf "$APP_STAGE"
COPYFILE_DISABLE=1 ditto --norsrc --noextattr "$APP_SRC" "$APP_STAGE"
codesign --verify --deep --strict --verbose=2 "$APP_STAGE"

restore_previous_install() {
  rm -rf "$APP_STAGE"
  if [[ -e "$APP_BACKUP" ]]; then
    rm -rf "$APP_DST"
    mv "$APP_BACKUP" "$APP_DST"
  elif [[ -e "$APP_DST" ]]; then
    rm -rf "$APP_DST"
  fi
}
trap restore_previous_install ERR INT TERM

rm -rf "$APP_BACKUP"
if [[ -e "$APP_DST" ]]; then
  mv "$APP_DST" "$APP_BACKUP"
fi
mv "$APP_STAGE" "$APP_DST"
codesign --verify --deep --strict --verbose=2 "$APP_DST"

INSTALLED_ID="$(codesign -dv --verbose=4 "$APP_DST" 2>&1 | sed -n 's/^Identifier=//p')"
INSTALLED_TEAM="$(codesign -dv --verbose=4 "$APP_DST" 2>&1 | sed -n 's/^TeamIdentifier=//p')"
INSTALLED_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_DST/Contents/Info.plist")"
INSTALLED_BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_DST/Contents/Info.plist")"
INSTALLED_HASH="$(shasum -a 256 "$APP_DST/Contents/MacOS/PaperFlow" | awk '{print $1}')"
INSTALLED_COMMIT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$APP_DST/Contents/Resources/build-provenance.json")"
if [[ "$INSTALLED_ID" != "$SOURCE_ID" || "$INSTALLED_TEAM" != "$SOURCE_TEAM" || \
      "$INSTALLED_VERSION" != "$SOURCE_VERSION" || "$INSTALLED_BUILD" != "$SOURCE_BUILD" || \
      "$INSTALLED_HASH" != "$SOURCE_HASH" || "$INSTALLED_COMMIT" != "$SOURCE_COMMIT" ]]; then
  echo "Installed bundle verification failed; restoring the previous app." >&2
  rm -rf "$APP_DST"
  if [[ -e "$APP_BACKUP" ]]; then
    mv "$APP_BACKUP" "$APP_DST"
  fi
  exit 2
fi

if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -u "$APP_SRC" >/dev/null 2>&1 || true
  "$LSREGISTER" -f "$APP_DST"
fi

if command -v mdimport >/dev/null 2>&1; then
  mdimport "$APP_DST" || true
fi

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  spotlight_match="$(mdfind 'kMDItemCFBundleIdentifier == "com.paperflow.app"cd' | grep -F -x "$APP_DST" || true)"
  if [[ "$spotlight_match" == "$APP_DST" ]]; then
    break
  fi
  sleep 1
done

if [[ "$(mdfind 'kMDItemCFBundleIdentifier == "com.paperflow.app"cd' | grep -F -x "$APP_DST" || true)" != "$APP_DST" ]]; then
  echo "Installed app was not found at the exact Spotlight path: $APP_DST" >&2
  exit 2
fi

rm -rf "$APP_BACKUP"
trap - ERR INT TERM

mdls -name kMDItemDisplayName -name kMDItemKind -name kMDItemCFBundleIdentifier -name kMDItemVersion "$APP_DST"

echo "Installed $APP_DST"
echo "Version $INSTALLED_VERSION ($INSTALLED_BUILD), commit $INSTALLED_COMMIT"
echo "Identity $INSTALLED_ID, team $INSTALLED_TEAM, binary SHA-256 $INSTALLED_HASH"
echo "Spotlight: press Command-Space, type PaperFlow, press Return."
