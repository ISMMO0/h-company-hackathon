# Decisions log

Newest first. One line per decision, with the reason.

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
