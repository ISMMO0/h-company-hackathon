# Decisions log

Newest first. One line per decision, with the reason.

- **Sat 14:00** Controls that always work: a menu bar icon (pink dot: Talk, Stop, show/hide the
  idle pink cursor, step log, Quit) and a global stop shortcut **Control+Option+X**.
- **Sat 13:45** After the team lead's YouTube test:
  - Precise pointing: each click gets a second, dedicated Holo localization call on the
    full-resolution screenshot (no thinking, temp 0), replacing the planner's rough point.
  - Talk any time: the hotkey during a task no longer stops it; what you say is added to the
    task and Holo re-plans. Only a bare "stop" / "arrête" (or the × button) stops.
  - Mic waits for the whole sentence: Gladia endpointing 0.8 s, then finals are joined until
    1.5 s of quiet.
  - Details view (protocol v3): done / current / roadmap (numbered Linkup steps) + chat lines.
  - Idle follow: the pink cursor sits next to the mouse when no task runs (Devin, overlay).
- **Sat 13:15** GUIDE mode follows the user live: after showing a step it watches the screen
  (tiny screenshots every ~0.3 s, pixel diff, no model call) and re-plans as soon as the screen
  changes and settles or the user clicks; Next is only a fallback. Steps the user already did
  are skipped. A follow-along panel next to the pink cursor (Devin, protocol v2) replaces the
  control page during a task. Testing is done by the team lead, not by agents.
- **Sat 12:55** Fixes from live tests: the agent ignores its own control page; frontmost app is
  read from the live window list (NSWorkspace went stale); TTS is cut before listening and only
  the first sentence is spoken (the mic was transcribing our own voice).
- **Sat 12:50** Voice is live: **⌃⌥Space** (Control+Option+Space) → "Listening…" pill → Gladia
  (FR/EN) → task starts in the current app, no countdown. Press again to stop. Saying "do it /
  fais-le / à ma place" picks DO, "show me / montre-moi" picks GUIDE, otherwise the page toggle.
  ⌥Space was dropped: it collides with the ChatGPT launcher. Gladia `speech_threshold` 0.3.
- **Sat 12:40** First localhost demo works end to end (`./start.sh`): control page →
  Linkup hint → Holo loop → pink cursor (GUIDE) or real clicks/typing (DO). Tested in TextEdit.
- **Sat 12:40** Holo defaults: `holo4-27b`, thinking on (~1-1.5 s/step, plans correctly).
  `holo4-35b-a3b` without thinking is faster (0.5 s) but skips steps. Linkup `depth: fast` (~2 s).
- **Sat 12:40** Safety: DO mode never acts on macOS system/permission dialogs (frontmost app or
  window under the click in a blocklist); it pauses and asks the person. Added after a test
  where the agent clicked "Allow" on a system prompt by itself.
- **Sat 12:40** v1 trigger is a text box + 3 s countdown to switch apps; voice (Gladia) and a
  global hotkey come next.
- **Sat 12:30** UI rule: as simple and clean as possible; the team lead directs every iteration.
- **Sat 12:30** API keys for H, Gladia and Linkup are set up and verified (`smoke_test.py`).
  Keys live only in the local `.env`; agents never get them.
- **Sat 12:20** Gladia has no TTS: spoken replies use the built-in macOS voice.
- **Sat 12:20** Use our own Holo agent loop (Models API, function calling) rather than the
  managed desktop agent, so the pink cursor can show each action before it happens.
  `h/holo-desktop` stays as a fallback for DO mode.
- **Sat 12:10** Idea chosen: **Shadow Cursor** (see PLAN.md). Partners: H (core), Gladia (voice),
  Linkup (how-to lookup), Stripe (Pro paywall + Stripe Dashboard demo), Devin (builds).
- **Sat 11:50** Rule from kickoff: use at least 4 of the 5 partner technologies.
