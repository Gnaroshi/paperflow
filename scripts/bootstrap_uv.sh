#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="$PROJECT_ROOT/.paperflow/bin/uv"
SOURCE="${1:-${PAPERFLOW_SYSTEM_UV:-}}"

if [[ -z "$SOURCE" ]] && command -v uv >/dev/null 2>&1; then
  SOURCE="$(command -v uv)"
fi
if [[ -z "$SOURCE" && -x /opt/homebrew/bin/uv ]]; then
  SOURCE="/opt/homebrew/bin/uv"
fi
if [[ -z "$SOURCE" || ! -x "$SOURCE" ]]; then
  echo "No executable uv binary was found." >&2
  exit 127
fi

mkdir -p "$(dirname "$TARGET")"
cp "$SOURCE" "$TARGET"
chmod +x "$TARGET"
"$PROJECT_ROOT/bin/paperflow-uv" --version
echo "PaperFlow uv installed at $TARGET"
