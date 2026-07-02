#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_SRC="$SCRIPT_DIR/dist/PaperFlow.app"
INSTALL_DIR="${INSTALL_DIR:-/Applications}"
APP_DST="$INSTALL_DIR/PaperFlow.app"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

if [[ ! -d "$APP_SRC" ]]; then
  "$SCRIPT_DIR/build_app.sh"
fi

mkdir -p "$INSTALL_DIR"

case "$APP_DST" in
  */PaperFlow.app) ;;
  *)
    echo "Refusing to install to unexpected path: $APP_DST" >&2
    exit 2
    ;;
esac

if [[ -e "$APP_DST" ]]; then
  rm -rf "$APP_DST"
fi

COPYFILE_DISABLE=1 ditto --norsrc --noextattr "$APP_SRC" "$APP_DST"
codesign --verify --deep --strict --verbose=2 "$APP_DST"

if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$APP_DST"
fi

if command -v mdimport >/dev/null 2>&1; then
  mdimport "$APP_DST" || true
fi

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  display_name="$(mdls -raw -name kMDItemDisplayName "$APP_DST" 2>/dev/null || true)"
  kind="$(mdls -raw -name kMDItemKind "$APP_DST" 2>/dev/null || true)"
  if [[ "$display_name" != "(null)" && "$kind" != "(null)" ]]; then
    break
  fi
  sleep 1
done

mdls -name kMDItemDisplayName -name kMDItemKind "$APP_DST" || true

echo "Installed $APP_DST"
echo "Spotlight: press Command-Space, type PaperFlow, press Return."
