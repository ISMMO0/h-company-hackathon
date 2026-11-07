# Shadow Cursor overlay

Electron window that draws the pink cursor. View only: no API keys, no screen capture, no input
simulation. One transparent, click-through, always-on-top window per display; it connects to the
brain at `ws://127.0.0.1:8765/ws/overlay` and speaks [docs/protocol.md](../docs/protocol.md).

## Run

```sh
cd overlay
npm install
npm start
```

The overlay has no Dock icon and never takes focus. `Alt+Space` (global hotkey) sends `{"type":"hotkey"}` to the brain. It reconnects every second while the brain is
down. Quit with `Ctrl+C` in the terminal.

## Test without the brain

In a second terminal:

```sh
npm run test-server          # fake brain, moves the cursor every 2 s within 1440x900
npm run test-server 2560 1440   # optional: width height in screen points
```

`test-server.js` listens on port 8765, logs `{"type":"hello"}` when the overlay connects, and sends a
`cursor` message with a random position and label every 2 s.

## Files

- `main.js` — windows (one per display), WebSocket client, routes messages to the right display.
- `preload.js` — exposes `overlay.onMessage` / `overlay.hidden` to the page.
- `index.html` — pink arrow + label bubble, 400 ms ease-out glide.
- `test-server.js` — fake brain for manual testing.
