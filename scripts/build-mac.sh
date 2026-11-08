#!/bin/bash
# Build Shadow Cursor.dmg for the jury: frozen brain + Electron overlay, pointed at our cloud.
#   scripts/build-mac.sh   →  build/Shadow Cursor.dmg  (Apple Silicon, ad-hoc signed)
set -euo pipefail
cd "$(dirname "$0")/.."
B=build
mkdir -p $B

# 1. Brain → one folder binary (Python 3.12: safest for PyInstaller + pyobjc)
[ -x $B/venv312/bin/pyinstaller ] || { uv venv -q -p 3.12 $B/venv312; VIRTUAL_ENV=$B/venv312 uv pip install -q -r requirements.txt pyinstaller; }
$B/venv312/bin/pyinstaller --noconfirm --log-level WARN --onedir --name shadow-brain \
  --distpath $B --workpath $B/pyi --specpath $B/pyi \
  --add-data "$PWD/brain/static:brain/static" --collect-submodules brain --paths "$PWD" brain/app.py

# 2. No API keys in the app: it calls our cloud (server/proxy.py on Aiven), which holds them
CLOUD=https://01a1ba29-1725-7969-bc8e-a4b8b4e2de94-8080.eur-1.aiven.app
printf 'SHADOW_API=%s/api\nSHADOW_SITE=%s\nSHADOW_FREE_TASKS=1000\n' "$CLOUD" "${CLOUD//./\\.}" > $B/app.env
rm -rf $B/knowledge && cp -R data/knowledge $B/knowledge

# 3. Electron app, ad-hoc signed (unsigned apps show "damaged" on recent macOS)
(cd overlay && npx electron-builder --mac dir --arm64 --publish never)
APP="$B/app/mac-arm64/Shadow Cursor.app"
codesign --force --deep -s - "$APP"

# 4. DMG with a drag-to-Applications link
rm -rf $B/dmg "$B/Shadow Cursor.dmg" && mkdir $B/dmg
cp -R "$APP" $B/dmg/ && ln -s /Applications $B/dmg/Applications
hdiutil create -quiet -volname "Shadow Cursor" -srcfolder $B/dmg -format UDZO "$B/Shadow Cursor.dmg"
ls -lh "$B/Shadow Cursor.dmg"
