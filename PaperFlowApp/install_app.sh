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

if [[ -e "$APP_DST" ]]; then
  rm -rf "$APP_DST"
fi

ditto "$APP_SRC" "$APP_DST"
codesign --verify --deep --strict --verbose=2 "$APP_DST"

if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$APP_DST"
fi

echo "Installed $APP_DST"
echo "Spotlight: press Command-Space, type PaperFlow, press Return."
