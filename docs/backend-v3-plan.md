# Backend v3 plan: know before acting

Status: **approved Sat 15:40 (with OpenAI), in progress.** Reviewed by Devin (Ask mode). Fallback tag `v2-demo`.

## What the live tests showed
1. **It discovers the app with you** ("click here… no, here…"). Cause: Linkup runs in the
   background and its notes arrive *after* Holo has already started guessing.
2. **"Find the best restaurant in Paris" → it typed in Google Maps** instead of answering.
   Cause: every request is treated as "operate the screen"; there's no "just answer" path.
3. **In Do it mode it acts silently.** It should narrate like a tutor.

## Evidence
Asked Linkup (structured output) "how to add a skill in the Codex app": it returned the real
methods (`$skill-installer` in the chat, or Plugins → Record a skill) in **3.4–4.1 s**,
exactly what Holo was guessing at. Knowledge first works; it just has to come *before* the
first click.

## The plan

### 1. Knowledge before the first click (fixes 1)
- At task start, Linkup builds a **playbook** with structured output:
  `steps: [{action_hint, target, why}]`. Dumb on purpose: no coordinates, because Holo
  re-grounds every target on screen anyway.
- The agent **waits for it, max ~3.5 s** ("Researching…" in the panel), then **seeds Holo's
  plan with it**. Holo follows known steps and points at known targets instead of exploring.
- On timeout or bad output: today's behaviour (Holo plans alone). The demo never stalls.
- **On trouble** (same step 3 times, `wait`, or a "how" question mid-task): one targeted
  Linkup lookup with the app + current step + what's on screen, and the plan is updated.
- Cache by (app, task), not app alone.

### 2. An "answer" path (fixes 2)
- Every utterance is routed to **ANSWER**, **GUIDE** or **DO**.
- **ANSWER** (pure information: "what's the best Italian restaurant near Opéra?") → Linkup
  `sourcedAnswer` → the panel shows the top answers with sources, the voice says the first
  one, and it offers **"Want me to show it on Maps?"** (→ GUIDE/DO).
- "Find the best restaurant **and book it**" stays DO. When in doubt: GUIDE/DO (today).

### 3. A tutor that narrates (fixes 3)
- Every Holo action gets a **`why`** field ("Settings is where skills live"). It's spoken in
  Do it mode and shown in the panel: "Clicking **Settings**: that's where skills live."
  No extra call, about the same speed.

### 4. OpenAI: yes, but only where it pays off
Devin's point, which I agree with: **don't put a second model in the step loop.** The loop
already re-plans on every change and drops stale answers. An external "monitor" would
duplicate that and could argue with Holo mid-task.

Use an OpenAI model at **two moments only**, both off the per-step path:
- **Routing** each utterance (ANSWER / GUIDE / DO / stop / "I'm ahead" / question): a few
  hundred ms, far more robust than keywords on real speech ("find the best restaurant" is
  ambiguous on purpose).
- **Merging** Linkup's results into one clean playbook for this exact task.

It stays **optional**: without `OPENAI_API_KEY`, the router falls back to keywords and the
playbook comes from Linkup alone. Holo remains the eyes and hands, Linkup the knowledge. In
the pitch: "H sees and acts, Linkup knows, a small LLM routes."

### Latency budget
| Moment | Today | v3 |
|---|---|---|
| Start of a task | first step ~1.5 s, but blind | **~3.5–4.5 s** ("Researching…"), then **known** steps |
| Each step | ~1.3 s | ~1.3 s (unchanged) |
| A question | goes through the screen loop | **~2–4 s**, a direct answer |

## Order (about 2 h 30)
1. `why` + narration, ~30 min (Devin can do the panel side)
2. Playbook before the first click + targeted lookup when stuck, ~1 h
3. ANSWER path + router (keywords first, OpenAI if a key is added), ~1 h
4. Bench + your test round

Pitch fallback: tag `v2-demo` before starting.

## Risks (from Devin's review)
- 2–3 network calls before the first action → hard 3.5 s budget plus fallback.
- Mis-routing to ANSWER → only for purely informational requests, default to acting.
- Don't touch the per-step path.
