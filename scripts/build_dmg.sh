#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${DEVELOPER_DIR:-}" ]] && [[ -d /Library/Developer/CommandLineTools ]]; then
  if ! xcodebuild -license check &>/dev/null; then
    export DEVELOPER_DIR=/Library/Developer/CommandLineTools
  fi
fi

VERSION="${VERSION:-1.0.0}"
ARCH="$(uname -m)"
OUT="$ROOT/dist"
STAGE="$OUT/stage"
VENV="$ROOT/.venv"
APP_NAME="Burning Tool.app"
VOL="USB Burning Tool $VERSION"
DMG="USB-Burning-Tool-${VERSION}-macos-${ARCH}.dmg"
RW="$OUT/_rw.dmg"
MOUNT="/Volumes/$VOL"

cleanup() {
  if [[ -d "$MOUNT" ]]; then
    diskutil eject "$MOUNT" >/dev/null 2>&1 || true
  fi
  rm -f "$RW"
}
trap cleanup EXIT

[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q -r requirements.txt 'pyinstaller>=6.6'
export PYTHONPATH="$ROOT"

rm -rf "$OUT/Burning Tool" "$OUT/Burning Tool.app" "$STAGE" "$ROOT/build" "$OUT/$DMG"
mkdir -p "$STAGE" "$OUT"
[[ -d "$MOUNT" ]] && diskutil eject "$MOUNT" >/dev/null 2>&1 || true

"$VENV/bin/pyinstaller" --noconfirm --clean \
  --name "Burning Tool" --windowed \
  --icon "$ROOT/assets/ubt.icns" \
  --osx-bundle-identifier com.vsevolodvasin.usb-burning-tool \
  --add-data "$ROOT/assets:assets" \
  --add-data "$ROOT/LICENSE:." \
  --add-data "$ROOT/THIRD_PARTY.md:." \
  --add-data "$ROOT/NOTICE:." \
  --paths "$ROOT" \
  "$ROOT/scripts/run.py"

PLIST="$OUT/Burning Tool.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :NSHumanReadableCopyright Copyright (c) 2026" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string Copyright (c) 2026" "$PLIST"

cp -R "$OUT/Burning Tool.app" "$STAGE/"
ln -sf /Applications "$STAGE/Applications"

hdiutil create -volname "$VOL" -srcfolder "$STAGE" -ov -fs HFS+ -format UDRW "$RW"
hdiutil attach -readwrite -noverify -noautoopen "$RW" >/dev/null
for _ in $(seq 1 30); do
  [[ -d "$MOUNT/$APP_NAME" ]] && break
  sleep 0.3
done
[[ -d "$MOUNT/$APP_NAME" ]] || { echo "mount failed: $MOUNT"; exit 1; }

osascript <<EOF
tell application "Finder"
  tell disk "$VOL"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set the bounds of container window to {200, 120, 740, 480}
    set opts to icon view options of container window
    set icon size of opts to 128
    set text size of opts to 12
    set arrangement of opts to not arranged
    set position of item "$APP_NAME" of container window to {140, 180}
    set position of item "Applications" of container window to {400, 180}
    update without registering applications
    delay 1
    close
    open
    delay 2
  end tell
end tell
EOF

sync
diskutil eject "$MOUNT" >/dev/null
trap - EXIT
rm -f "$OUT/$DMG"
hdiutil convert "$RW" -format UDZO -imagekey zlib-level=9 -o "$OUT/$DMG"
rm -f "$RW"
echo "OK: $OUT/$DMG"
