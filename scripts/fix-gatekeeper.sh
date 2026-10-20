#!/bin/bash
# Снять карантин Gatekeeper с .app (после скачивания с GitHub / из браузера).
set -euo pipefail

XATTR=/usr/bin/xattr
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
  if [[ -d "/Applications/Burning Tool.app" ]]; then
    TARGET="/Applications/Burning Tool.app"
  elif [[ -d "$(dirname "$0")/../dist/Burning Tool.app" ]]; then
    TARGET="$(cd "$(dirname "$0")/.." && pwd)/dist/Burning Tool.app"
  else
    echo "Usage: $0 \"/path/to/Burning Tool.app\""
    exit 1
  fi
fi

[[ -d "$TARGET" ]] || { echo "Not an app bundle: $TARGET"; exit 1; }

"$XATTR" -cr "$TARGET" 2>/dev/null || {
  find "$TARGET" \( -type f -o -type d \) -exec "$XATTR" -d com.apple.quarantine {} \; 2>/dev/null || true
  "$XATTR" -c "$TARGET" 2>/dev/null || true
}

echo "OK: quarantine cleared — $TARGET"
echo "Open the app again (or right-click → Open once)."
