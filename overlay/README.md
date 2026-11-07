# Shadow Cursor overlay

Electron window that draws the pink cursor and the follow-along panel. View only: no API keys, no screen capture, no input
simulation. One transparent, click-through, always-on-top window per display; it connects to the
brain at `ws://127.0.0.1:8765/ws/overlay` and speaks [docs/protocol.md](../docs/protocol.md).

## Run

```sh
cd overlay
npm install
npm start
```

While no task runs the pink cursor sits next to the real mouse (+16, +16) and follows it at ~60 fps
(`screen.getCursorScreenPoint()` polled in `main.js`, no easing). During a task the panel (instruction,
state line, Next / Guide–Do it / mic / Details / × buttons, collapse chevron) follows the pink cursor;
the window is click-through everywhere except over the panel, which sends `next` / `mode` / `mic` /
`stop` to the brain. **Details** opens a second card under the panel with the `plan` steps and the
last `chat` lines. While a task runs, `listening` shows the pulsing dot on the panel's state line
instead of the floating pill. The overlay has no Dock icon and never takes focus. `Control+Alt+Space` (global hotkey) sends `{"type":"hotkey"}` to the brain. It reconnects every second while the brain is
down. Quit with `Ctrl+C` in the terminal.

## Test without the brain

In a second terminal:

```sh
npm run test-server          # fake brain, moves the cursor every 2 s within 1440x900
npm run test-server 2560 1440   # optional: width height in screen points
```

`test-server.js` listens on port 8765, logs everything the overlay sends (`hello`, `next`, `mode`, `mic`,
`stop`), and replays a 5-step task every 2 s: a `cursor` message with a random position and label, a
`step` for the panel, the full `plan`, a `chat` line now and then and `listening` on/off during step 2;
then `clear` and a 6 s idle pause where the pink cursor follows the mouse.

## Files

- `main.js` — windows (one per display), WebSocket client, routes messages to the right display.
- `preload.js` — exposes `overlay.onMessage` / `overlay.hidden` / `overlay.send` / `overlay.interactive` to the page.
- `index.html` — pink arrow + label bubble + panel + details card, 400 ms ease-out glide.
- `test-server.js` — fake brain for manual testing.
