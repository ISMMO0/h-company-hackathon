#!/bin/bash
# Start Shadow Cursor: brain (Python) + overlay (Electron).
# Control page and step log: http://127.0.0.1:8765 (keep it off-screen while using the hotkey).
cd "$(dirname "$0")"
trap 'kill 0' EXIT
.venv/bin/python -m brain.server &
(cd overlay && npm start >/dev/null 2>&1) &
wait
