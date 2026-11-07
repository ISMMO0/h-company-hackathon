# Decisions log

Newest first. One line per decision, with the reason.

- **Sat 16:30** Backend v3 brain shipped (overlay v5 card pending from Devin). Measured: Linkup
  playbook 3.4-4.5 s (Codex: finds `$skill-creator`, the real path), sourced answer 3.6 s,
  plan p50 1.0 s + point 0.4 s per step. Router: keywords 10/10 on test phrases; OpenAI used
  automatically once OPENAI_API_KEY is in .env (model from OPENAI_MODEL or newest gpt-*-mini).
- **Sat 15:40** Backend v3 approved (docs/backend-v3-plan.md), fallback tag `v2-demo`:
  knowledge before the first click (Linkup structured playbook, ≤3.5 s, seeds Holo's plan;
  targeted lookup when stuck); an ANSWER path for pure questions (answer card + "show me /
  do it"); a `why` on every action, spoken in Do it mode. OpenAI only routes utterances and
  merges the playbook, never in the step loop; optional (keyword fallback without the key).
  Protocol v5: step.why, answer card, followup.
- **Sat 15:00** Backend v2 shipped (brain/agent.py, planner.py, voice.py; memory.py + bench by
  Devin; overlay v4 by Devin). Bench on a real screenshot: plan p50 0.8 s, point 0.43 s
  (crop), total ~1.3 s/step, 3/3 hits (was 2.4-2.8 s). Planner: holo4-27b, thinking effort
  "low", 1024 px shot; pointer: 400x260 pt native crop, full-screen fallback. Stale answers
  are dropped on click / key / window switch / speech. Watching uses system input timers
  (catches quick clicks and typing) + pixel diffs (switched off when something animates).
  Set SHADOW_SAVE_FIXTURES=1 to save screenshots for the bench (kept local, gitignored).
- **Sat 14:15** Backend v2 approved (docs/backend-v2-plan.md), fallback tag `v1-demo`:
  measure per stage; planner on a small full-screen shot, pointer on a native-res crop around
  the rough point; the model keeps a numbered plan and reports progress so users can skip
  ahead; new `say`/`wait` tools; stale answers dropped when the screen changes; push-to-talk
  with live text (⌃⌥Space start/send, ⌃⌥X cancel), talking never stops a task; session
  memory. Overlay side follows protocol v4.
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
