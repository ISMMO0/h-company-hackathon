# Shadow Cursor: plan

A pink "shadow" cursor that lives next to yours on macOS. Press a button, say what you want to
do, and it either **guides** you (moves to the next thing to click and tells you out loud) or
**does it** while you watch. It works in any app because it reads the screen like a human.

Deadline: **Sun Nov 8, 14:00** (submission). Pitches from 15:45.

## 1. Why this wins (jury grid)

| Criterion | Weight | How we score |
|---|---|---|
| Use of computer use | 25% | The product *is* computer use: Holo sees the screen and points or acts in any app |
| Technical execution & reliability | 25% | Guide mode = one grounding call per step (fast, robust). 3 rehearsed demo scenarios |
| Usefulness & impact | 20% | Learn any software, by voice, for anyone (onboarding, accessibility, seniors) |
| Originality | 15% | An agent that *teaches*, not just automates. Visible second cursor |
| UX & user control | 10% | Watch / Guide / Do modes, push-to-talk, "stop" takes control back instantly |
| Demo clarity & Q&A | 5% | Two cursors on the big screen; live voice |

Rule: use at least 4 of the 5 partners. We use **Gladia, Linkup, Stripe, Devin** (+ H, the host).

## 2. How each partner is used

| Partner | Role |
|---|---|
| **H Company (Holo)** | Models API `https://api.hcompany.ai/v1` (OpenAI-compatible). *Grounding*: screenshot + "the Export button" → `{x, y}` in [0,1000]. *Planning/acting*: function-calling agent loop (`click`, `type`, `scroll`, `answer` tools). Models: `holo4-35b-a3b` (fastest) for grounding, `holo4-27b` for planning if quality needs it |
| **Gladia** | Live streaming STT over WebSocket (partial transcripts + endpointing) for push-to-talk commands, FR + EN. Gladia has **no TTS**: spoken replies use macOS `say` / AVSpeechSynthesizer |
| **Linkup** | `/search` `depth:"fast"` (~1s) or `"flash"` (<200ms): fetch the real, current steps for "how to X in app Y" so the planner doesn't hallucinate menus |
| **Stripe** | (a) **Shadow Pro** paywall via Stripe Checkout (free = N questions/day). (b) **Demo target**: "Show me how to refund a customer in Stripe" in the Stripe Dashboard (test mode) |
| **Devin** | Builds most of the code via PRs (overlay app, audio pipeline, Stripe integration, UI). Visible in repo history for the "Best use of Devin" prize |

## 3. Architecture

```
┌──────────── macOS ────────────────────────────────────────────┐
│  Overlay app (transparent, click-through, always on top)      │
│   • pink cursor sprite + animation   • speech bubble          │
│   • floating mic button / hotkey     • mode toggle W/G/D      │
│                  ▲ local WebSocket (JSON events) ▼            │
│  Core (Python)                                                │
│   • capture: screenshot (downscaled, keep scale factor)       │
│   • voice: mic → Gladia live WS → final transcript            │
│   • brain: intent → Linkup lookup → Holo loop                 │
│   • act:   GUIDE → emit "point(x,y,say)" ; DO → click/type    │
│   • speak: macOS TTS                                          │
└───────────────────────────────────────────────────────────────┘
        │ Holo API        │ Gladia WS       │ Linkup     │ Stripe
```

Overlay tech (Electron vs Swift vs PyObjC) is decided by Devin's research
(`docs/research/desktop-stack.md`). Default if unsure: **Electron overlay + Python core**.

### Core loop (both modes)
1. User holds the button and speaks → Gladia final transcript → task.
2. Linkup `fast` search: "steps to <task> in <frontmost app>" → short hint text.
3. Holo step (system prompt + task + hint + last ≤3 screenshots in `<observation>` tags,
   `tool_choice="required"`, thinking on, temp 0.8) → one tool call.
4. **GUIDE**: overlay flies the pink cursor to (x, y), speaks the step ("Click File").
   Wait until the user clicks near the target (or says "next"), then new screenshot → step 3.
   **DO**: pink cursor flies there first (so you see it), short pause, then we click/type.
5. Stop on `answer` tool → speak the summary. "Stop" / Esc → abort immediately.

### Holo gotchas (from the docs, must follow)
- Coordinates are [0,1000] relative to **the exact image sent**. Scale back with that
  image's size, then convert pixels → screen points (Retina = 2x).
- Single grounding calls: thinking **off**, temperature 0. Agent loop: thinking **on**, 0.8.
- Keep only the last 3 screenshots; replace older ones with "[screenshot evicted]".
- Register an `answer` tool; never stop on an empty tool call.
- Tool results go back as `role: "tool"` with the matching `tool_call_id`.
- Fallback for DO mode: H's managed desktop agent (`pip install "hai-agents[cli,desktop]"`,
  `h/holo-desktop`), which already drives a local Mac.

## 4. Demo scenarios (rehearse each 10×)

1. **Stripe Dashboard** (GUIDE): "How do I refund a customer?" → 3–4 pointed steps.
2. **Google Sheets / Docs** (DO): "Make the header row bold and freeze it" → it does it.
3. **Switch mid-task**: "Actually, you do it" → GUIDE becomes DO; "stop" → user takes over.
4. Paywall moment: free quota hit → Stripe Checkout (test card) → Pro unlocked.

## 5. Work split

| Track | Owner | Notes |
|---|---|---|
| T0 Spike: Holo grounding latency + accuracy on this Mac | Claude | Needs `HAI_API_KEY`. Go/no-go for the whole idea |
| T1 Overlay app (pink cursor, bubble, mic button, WS client) | Devin | Biggest UI chunk |
| T2 Core: capture + coords + Holo loop (GUIDE/DO) | Claude + Devin | Claude owns the loop logic; Devin helpers + tests |
| T3 Voice: mic + Gladia live STT + TTS | Devin | |
| T4 Linkup hint step | Devin | Small |
| T5 Stripe Checkout + Pro flag | Devin | Small, test mode |
| T6 Integration, demo hardening, scenario tuning | Claude + you | Critical path |
| T7 Pitch deck, video backup, README, social posts | You + Claude | LinkedIn/X prizes (€500 each) |

## 6. Timeline (Paris time)

| When | Milestone |
|---|---|
| Sat 12:30–14:00 | Keys in `.env` · T0 spike passes · Devin research merged · stack locked |
| Sat 14:00–19:00 | T1, T3, T4, T5 by Devin in parallel · Claude builds T2 GUIDE mode |
| Sat 19:00–21:00 | First end-to-end GUIDE run on scenario 1 |
| Sat 21:00 → night | DO mode · mode switching · stop/takeover |
| Sun 08:00–11:00 | Scenarios 2–4 · reliability fixes · Stripe paywall |
| Sun 11:00–13:00 | **Feature freeze 11:00** · rehearse · record backup video · deck |
| Sun 13:30 | Submit on BuilderBase (project name, GitHub repo, H showcase, demo URL) |

## 7. Risks

| Risk | Mitigation |
|---|---|
| Holo latency too high for live feel | Downscale screenshots (~1280 px wide), fastest model for grounding, animate the cursor while waiting |
| Planner picks wrong steps | Linkup hint + rehearsed scenarios + GUIDE lets the user correct |
| macOS permissions (Screen Recording, Accessibility, Mic) block on stage | Grant all on the demo Mac before Sunday; never switch machines |
| Venue Wi-Fi | Phone hotspot backup + recorded backup video |
| Devin PRs add AI co-author trailers | Squash-merge with a clean message |

## 8. Open questions

- Does Devin count toward "4 of 5 partners"? Ask the organizers / Discord.
- Submission needs "H Showcase Platform" entry: find where.

## 9. Final stretch (team lead, Sat night): keep in mind, not started
1. **Landing page**: one simple page, "Click here to activate your Shadow Cursor", nothing more.
   Hosted on **Vercel**. Note: Vercel can only host the page (and the Stripe checkout / download
   link); the product itself (Python brain + Electron overlay) runs on the Mac, so the live demo is local.
2. **Deploy**: landing page on Vercel = the "demo URL" for BuilderBase.
3. To settle before moving on:
   - The 4-of-5 partner rule: Gladia, Linkup, Devin, Stripe; confirm with the organizers that Devin
     counts and that Stripe in the product is enough.
   - The demo script: 1 Guide + 1 Do it scenario, rehearsed, plus a recorded backup video
     (Holo API latency varies a lot).
   - Submission content (BuilderBase: name, GitHub repo, H showcase entry, demo URL) before 14:00 Sunday.
   - Demo Mac ready: permissions granted, caches warmed (app cheat sheets, voice), hotspot backup.
   - Feature freeze Sunday 11:00.
