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
last `chat` lines. `listening` switches the card to listening mode (pulsing dot, hint line, live
`transcript` text, **Send** = `hotkey` / **Cancel** = `stop`), opened at the mouse when no task runs;
a `paused` step dims the panel until the next step. A step's optional `why` shows as a muted line under
the instruction. An `answer` message opens an answer card (text, up to 3 source titles that open in the
default browser, and if `offer` is set the offer line with **Show me** / **Do it** = `followup`
guide / do); it closes on ×, after 30 s, or when a step or listening starts. A `cursor` with
`tentative: true` (a guess while the person is still talking) draws the cursor at 55% opacity with a
soft pulse and an italic label; the next plain `cursor` makes it solid. `pulse` (speech start) draws
one quick ring around the pink cursor wherever it is, idle follow included. `mic` (open mic during a
task) shows a live pink dot on the mic button when `on` and a muted slashed icon when off; its
optional `heard` text is one muted line at the bottom of the panel that fades after 6 s. The mic
button keeps sending `{"type":"mic"}`. The overlay has no Dock
icon and never takes focus. `Control+Alt+Space` (global hotkey, also the menu bar "Talk / Send")
sends `{"type":"hotkey"}` and `Control+Alt+X` ("Stop / Cancel") sends `{"type":"stop"}` to the brain.
It reconnects every second while the brain is down. Quit with `Ctrl+C` in the terminal.

## Test without the brain

In a second terminal:

```sh
npm run test-server          # fake brain, moves the cursor every 2 s within 1440x900
npm run test-server 2560 1440   # optional: width height in screen points
```

`test-server.js` listens on port 8765, logs everything the overlay sends (`hello`, `hotkey`, `next`,
`mode`, `mic`, `stop`, `followup`), and loops: 3 s idle (the pink cursor follows the mouse), a `pulse`,
a question answered with an `answer` card (sources + offer), a listening session with a growing
`transcript`, two task steps (`cursor` with a random position and label, `step` with a `why`, `plan`,
a `chat` line) with the mic on, an open-mic utterance (`pulse`, two tentative cursor moves, a `heard`
line), a `paused` step, mic off then on again with another utterance, the last steps, then `clear`.

## Files

- `main.js` — windows (one per display), WebSocket client, routes messages to the right display.
- `preload.js` — exposes `overlay.onMessage` / `overlay.hidden` / `overlay.send` / `overlay.interactive` / `overlay.open` to the page.
- `index.html` — pink arrow + label bubble + panel + details card, 400 ms ease-out glide.
- `test-server.js` — fake brain for manual testing.
