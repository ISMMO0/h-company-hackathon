#!/bin/bash
# Start Shadow Cursor: brain (Python) + overlay (Electron), then open the control page.
cd "$(dirname "$0")"
trap 'kill 0' EXIT
.venv/bin/python -m brain.server &
(cd overlay && npm start >/dev/null 2>&1) &
sleep 2 && open http://127.0.0.1:8765
wait
