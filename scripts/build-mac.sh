#!/bin/bash
# Build Shadow Cursor.dmg for the jury: frozen brain + Electron overlay + the keys from .env.
#   scripts/build-mac.sh   →  build/Shadow Cursor.dmg  (Apple Silicon, ad-hoc signed)
# The keys ship inside the app: rotate them after the hackathon.
set -euo pipefail
cd "$(dirname "$0")/.."
B=build
mkdir -p $B

# 1. Brain → one folder binary (Python 3.12: safest for PyInstaller + pyobjc)
[ -x $B/venv312/bin/pyinstaller ] || { uv venv -q -p 3.12 $B/venv312; VIRTUAL_ENV=$B/venv312 uv pip install -q -r requirements.txt pyinstaller; }
$B/venv312/bin/pyinstaller --noconfirm --log-level WARN --onedir --name shadow-brain \
  --distpath $B --workpath $B/pyi --specpath $B/pyi \
  --add-data "$PWD/brain/static:brain/static" --collect-submodules brain --paths "$PWD" brain/app.py

# 2. Only the keys the app needs (no database or Stripe secrets), and the per-site lessons
grep -E '^(HAI_API_KEY|OPENAI_API_KEY|GLADIA_API_KEY|LINKUP_API_KEY|HOLO_[A-Z_]+|OPENAI_MODEL|SHADOW_VOICE|SHADOW_FREE_TASKS)=' .env > $B/app.env
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
