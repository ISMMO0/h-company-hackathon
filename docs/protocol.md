# Overlay ⇄ brain protocol (v2)

The Python **brain** (`brain/`) runs one local server on `127.0.0.1:8765`:
- `http://127.0.0.1:8765/` — the control page (text box, mode, Go/Stop, step log).
- `ws://127.0.0.1:8765/ws/overlay` — the Electron **overlay** (`overlay/`) connects here.

All coordinates are **global screen points** (macOS / Electron DIP), origin top-left of the
primary display. The brain does all pixel ↔ point conversion.

## Brain → overlay

| Message | Meaning |
|---|---|
| `{"type":"cursor","x":512,"y":300,"label":"Click File"}` | Show the pink cursor and glide it (≈400 ms ease) to (x, y). `label` is a short hint shown in a small bubble next to it. |
| `{"type":"step","text":"Click the search box","mode":"guide","state":"waiting"}` | Update the **panel** (see below). `mode`: `"guide"` or `"do"`. `state`: `"thinking"` (Holo is working), `"waiting"` (the user's turn), `"acting"` (DO mode is clicking), `"done"` (task finished, `text` is the final message). |
| `{"type":"hide"}` | Hide everything immediately (used right before a screenshot). Reply `{"type":"hidden"}` once the window is actually hidden (next frame). |
| `{"type":"show"}` | Show the cursor and panel again. |
| `{"type":"clear"}` | Task finished or stopped: hide cursor, bubble and panel. |
| `{"type":"listening","on":true}` | Show a small pink pulsing dot with "Listening…" next to the user's real mouse position (read when the message arrives). `"on":false` hides it. |

## Overlay → brain

| Message | Meaning |
|---|---|
| `{"type":"hello"}` | Sent on connect. |
| `{"type":"hidden"}` | Ack for `hide`. |
| `{"type":"hotkey"}` | The user pressed the global hotkey (`Control+Alt+Space`). Brain: stop if a task runs, else listen. |
| `{"type":"next"}` | Panel **Next** button: "I did it / skip": the brain re-checks the screen now. |
| `{"type":"mode","mode":"do"}` | Panel mode toggle (**Guide** ⇄ **Do it**), takes effect on the next step. |
| `{"type":"mic"}` | Panel mic button: same as the hotkey. |
| `{"type":"stop"}` | Panel **×** button: stop the task. |

## The panel

A small card that sits next to the pink cursor and follows it, shown only while a task runs.
It holds the current instruction (`step.text`), a tiny state line, and four buttons:
**Next**, **Guide/Do it** toggle, **mic**, **×**. A chevron collapses it to just the pink cursor
and bubble. The overlay stays click-through everywhere except over the panel.

The overlay reconnects every 1 s if the brain is not running. Without the overlay the
brain still works and shows the pink marker on the screenshot in the control page.
