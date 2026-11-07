# Overlay ⇄ brain protocol (v1)

The Python **brain** (`brain/`) runs one local server on `127.0.0.1:8765`:
- `http://127.0.0.1:8765/` — the control page (text box, mode, Go/Stop).
- `ws://127.0.0.1:8765/ws/overlay` — the Electron **overlay** (`overlay/`) connects here.

All coordinates are **global screen points** (macOS / Electron DIP), origin top-left of the
primary display. The brain does all pixel ↔ point conversion.

## Brain → overlay

| Message | Meaning |
|---|---|
| `{"type":"cursor","x":512,"y":300,"label":"Click File"}` | Show the pink cursor and glide it (≈400 ms ease) to (x, y). Show `label` in a small bubble next to it. |
| `{"type":"hide"}` | Hide everything immediately (used right before a screenshot). Reply `{"type":"hidden"}` once the window is actually hidden (next frame). |
| `{"type":"show"}` | Show the cursor again at its last position. |
| `{"type":"clear"}` | Task finished or stopped: hide cursor and bubble. |

## Overlay → brain

| Message | Meaning |
|---|---|
| `{"type":"hello"}` | Sent on connect. |
| `{"type":"hidden"}` | Ack for `hide`. |

The overlay reconnects every 1 s if the brain is not running. Without the overlay the
brain still works and shows the pink marker on the screenshot in the control page.
