# Backend v2 plan: fast and smart

Status: **shipped Sat 15:00**, waiting for the team lead's live tests. Fallback for the pitch: tag `v1-demo`.

## Goals
1. **Fast**: under ~1.5 s from "screen changed" to "pink cursor on the next target".
2. **Smart**: follows where the user actually is, not where the script expected them to be.
   Skips steps they already did, notices when they do something else, never gets stuck.
3. **Conversational**: talk at any time without stopping it; see what you say live; validate
   with the hotkey.
4. **Context**: remembers the conversation and past tasks.

## A. Measure first
Log a timing line per step: `capture · encode · plan (Holo) · point (Holo) · total`, plus
Linkup and Gladia times per task. Shown in the step log. Every speed change below is checked
against these numbers, on saved screenshots (see G), not by guessing.

## B. Speed
| Change | Why |
|---|---|
| Planner sees a **smaller screenshot** (~1024 px wide, JPEG) | Enough to understand the page; less upload and fewer image tokens |
| Pointer sees a **crop around the planner's rough point** at native resolution (≈600×400 px) | The FDE's idea, applied where it helps: tiny upload, small icons get bigger, so faster and more precise. The planner still sees the whole screen, because the next target can be anywhere |
| Planner thinking **effort "low"** (holo4-27b supports low/medium/high) | Measure against "on"; keep whichever is fastest at the same accuracy |
| **Linkup in parallel** with the first Holo step | Today it adds ~2 s before anything happens |
| **Stable prompt prefix** (system + task + plan first, screenshots last) | Hits H's automatic prompt cache |
| **Cancel stale work**: if the screen changes while Holo is thinking, drop that answer and re-plan from the new screen | No more instructions for a screen that no longer exists |

## C. Smart: follow the user, not the script
1. **An explicit plan the model tracks.** At task start, one Holo call turns the request (+
   Linkup notes) into a short numbered plan. Every later step returns, with its action,
   **which plan step we are on** (`progress: 4`). Steps before it are marked done. So if
   the user jumps from step 1 to step 4, the next screenshot shows it and the model says
   "we're at 4", the Details view ticks 1–3, and the pink cursor goes to step 5.
2. **Re-plan on any meaningful change**, not just "did they click my target": screen
   settles after a change, app switches, URL/window-title change, or the user speaks.
3. **New tools for the model** besides click/type/press/scroll/answer:
   - `say(text)`: answer a question out loud without acting ("where is the export
     button?" / "what does this do?").
   - `wait(reason)`: the user is doing something else or the screen isn't ready, so pause
     quietly. The panel says "Paused, I'll pick up when you're back". It resumes on the next
     relevant change.
4. **Never loop**: if the same action is proposed 3 times with no progress, say so, show the
   full plan, and ask.

## D. Voice: push-to-talk you can see
- **⌃⌥Space opens the panel in "listening" mode** with your words appearing live (Gladia
  partials).
- **⌃⌥Space again = send now.** No waiting for silence. A long silence (~4 s) still sends,
  as a fallback. **Esc / ⌃⌥X = cancel** what you said.
- **During a task, talking never stops it.** What you say goes to the model, which decides:
  - "stop" → stop
  - "I already did that" / "I'm ahead" → re-check the screen and skip ahead
  - "wait, I'm doing something else" → `wait`
  - a question → `say`
  - "actually, do it for me" / "show me instead" → switch mode
  - new info ("Linus instead") → update the plan
- Note: the shortcut stays **Control+Option+Space** (⌃⌥Space). Control+Command+Space is
  the macOS emoji picker.

## E. Memory
- `data/session.json`: every utterance, every step (done or skipped), and each finished
  task as a one-line summary (request → result).
- A new task starts with the last few task summaries + recent conversation, so "do the
  same for Linus" works.
- The Details view shows the plan (with real progress) and the conversation.

## F. Backend structure (so it stays fast and debuggable)
Today `server.py` does everything in one loop. Split into:

| Module | Job |
|---|---|
| `agent.py` | One **event-driven state machine**: IDLE → LISTENING → PLANNING → WAITING_FOR_USER / ACTING → PAUSED → DONE. Events (screen changed, click, utterance, panel button, hotkey) go into one queue; a newer event cancels stale planning |
| `perception.py` | Captures, thumbnails, change detection, crops, app/window-title watcher |
| `planner.py` | Holo calls: make plan, next step (+progress), point (crop) |
| `voice.py` | Gladia stream with live partials, manual "send now", cancel |
| `memory.py` | Session log + summaries |
| `server.py` | Only the web/WebSocket plumbing |

## G. Testing without touching your Mac
- Save screenshots from your real runs (opt-in) as fixtures for the 3 demo scenarios.
- `scripts/bench.py` replays them through planner + pointer and reports **latency** and
  **hit rate** (was the point inside the right element?). Speed tweaks get decided on
  these numbers.
- You keep doing the live tests.

## Work split
| Who | What |
|---|---|
| **Claude** | A, B, C, F: the agent state machine, planner, perception (critical path) |
| **Devin** | D overlay side (live transcript in the panel, listening/send/cancel states, paused state), E memory module, G bench harness |

## Order and time (Paris time)
1. A + G (measure, bench), ~45 min
2. F + C (state machine, plan with progress, new tools), ~1 h 30
3. B (speed changes driven by the numbers), ~45 min
4. D + E (voice UX, memory), in parallel with Devin, ~1 h
5. Your test round, fixes

Target: v2 ready to test around **18:00–18:30**, which leaves the evening for the Stripe
scenario and rehearsals.

## Risks
- Re-planning on every change costs Holo calls: fine on cost (~$0.001/step), and stale-work
  cancellation keeps it from piling up.
- The `progress` field depends on the model tracking the plan well, so it's checked on the
  bench first. Fallback: ask "which steps are done?" in a separate small call.
- A big refactor late in the hackathon: done behind the same protocol, and the current
  version stays on a tag (`v1-demo`) as a fallback for the pitch.
