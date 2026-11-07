# Decisions log

Newest first. One line per decision, with the reason.

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
