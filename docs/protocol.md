# Overlay ⇄ brain protocol (v5)

The Python **brain** (`brain/`) runs one local server on `127.0.0.1:8765`:
- `http://127.0.0.1:8765/` — the control page (text box, mode, Go/Stop, step log).
- `ws://127.0.0.1:8765/ws/overlay` — the Electron **overlay** (`overlay/`) connects here.

All coordinates are **global screen points** (macOS / Electron DIP), origin top-left of the
primary display. The brain does all pixel ↔ point conversion.

## Brain → overlay

| Message | Meaning |
|---|---|
| `{"type":"cursor","x":512,"y":300,"label":"Click File"}` | Show the pink cursor and glide it (≈400 ms ease) to (x, y). `label` is a short hint shown in a small bubble next to it. |
| `{"type":"step","text":"Click the search box","mode":"guide","state":"waiting"}` | Update the **panel** (see below). `mode`: `"guide"` or `"do"`. `state`: `"thinking"` (Holo is working), `"waiting"` (the user's turn), `"acting"` (DO mode is clicking), `"paused"` (the user is doing something else; `text` says why), `"done"` (task finished, `text` is the final message). |
| `{"type":"hide"}` | Hide everything immediately (used right before a screenshot). Reply `{"type":"hidden"}` once the window is actually hidden (next frame). |
| `{"type":"show"}` | Show the cursor and panel again. |
| `{"type":"clear"}` | Task finished or stopped: hide cursor, bubble and panel. |
| `{"type":"listening","on":true}` | **Push-to-talk opened.** Open the panel (at the user's mouse if no task runs, else where it is) in *listening* mode: pulsing pink dot, "Listening… ⌃⌥Space to send · ⌃⌥X to cancel", and an empty live-text area. `"on":false` closes listening mode (back to the step, or closes the panel if no task runs). |
| `{"type":"step",…,"why":"Settings is where skills live"}` | Optional `why` on any step: show it under the instruction in a muted line (e.g. "Clicking Settings" / "that's where skills live"). |
| `{"type":"answer","text":"Pink Mamma is the most-cited…","sources":[{"title":"Le Fooding","url":"https://…"}],"offer":"Want me to show it on Maps?"}` | **Answer card** for pure questions (no task running): the text (up to ~6 lines, scrolls), up to 3 source titles (small, muted, clickable → open URL in the browser), and if `offer` is set, the offer line with two buttons **Show me** and **Do it**. Closes on ×, after 30 s, or when a new task starts. |
| `{"type":"transcript","text":"show me how to"}` | Live words while listening (replace the live-text area; partials and finals already joined by the brain). |
| `{"type":"plan","steps":[{"text":"Click the search bar","status":"done"}, …]}` | Full step list for the **details** view. `status`: `"done"` (✓), `"current"` (highlighted), `"todo"` (muted). Sent whenever it changes; always the whole list. |
| `{"type":"chat","who":"you","text":"Actually search for MKBHD"}` | One line of conversation for the details view (`who`: `"you"` or `"shadow"`). Append; `clear` empties it. |

## Overlay → brain

| Message | Meaning |
|---|---|
| `{"type":"hello"}` | Sent on connect. |
| `{"type":"hidden"}` | Ack for `hide`. |
| `{"type":"hotkey"}` | ⌃⌥Space. **Toggle**: if not listening → start listening; if listening → **send now** what was said. Talking during a task never stops it; the model decides what the words mean (stop, I'm ahead, wait, question, switch mode, new info). |
| `{"type":"next"}` | Panel **Next** button: "I did it / skip": the brain re-checks the screen now. |
| `{"type":"mode","mode":"do"}` | Panel mode toggle (**Guide** ⇄ **Do it**), takes effect on the next step. |
| `{"type":"mic"}` | Panel mic button: same as the hotkey. |
| `{"type":"followup","mode":"guide"}` | Answer card **Show me** (`"guide"`) or **Do it** (`"do"`): the brain turns the offer into a task. |
| `{"type":"stop"}` | Panel **×**, menu bar Stop or ⌃⌥X. If listening: **cancel** the utterance only. Otherwise stop the task. |

## The panel

A small card that sits next to the pink cursor and follows it, shown only while a task runs.
It holds the current instruction (`step.text`), a tiny state line, and four buttons:
**Next**, **Guide/Do it** toggle, **mic**, **×**. A chevron collapses it to just the pink cursor
and bubble. The overlay stays click-through everywhere except over the panel.

### Listening and paused
While listening, the panel shows the live text (wraps, grows up to ~5 lines) and replaces the
buttons row with two: **Send** (= hotkey) and **Cancel** (= stop). In `paused` state the
state line reads "Paused" and the panel is dimmed; it un-dims on the next step.

### Details view
A small **Details** button on the panel opens a taller card under it: the `plan` list (✓ done,
current step highlighted, todo muted) and below it the last few `chat` lines. Click again to
close. Same style as the panel; scrolls if long.

## Idle follow
When no task runs (initially, and after `clear`), the pink cursor sits just next to the user's
real mouse (offset ≈ +16, +16 pt) and follows it in real time (poll the mouse position at
~60 fps, no easing), on whichever display the mouse is on. No bubble, no panel. On `cursor`
it leaves the mouse and glides to the target; after `clear` it glides back and resumes
following. `hide` hides it too (screenshots must never contain it).

The overlay reconnects every 1 s if the brain is not running. Without the overlay the
brain still works and shows the pink marker on the screenshot in the control page.
