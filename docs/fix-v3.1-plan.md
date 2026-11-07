# v3.1 fix plan: after the YouTube test

Status: **approved Sat 17:10, in progress.** Reviewed by Devin (Ask mode). Fallback tag `v3-demo`.

## What went wrong (from the log)
| # | Symptom | Cause |
|---|---|---|
| 1 | Dozens of "↻ re-planning (key/window)", then "Step budget reached" after 3–4 real instructions | Any key or window switch, **in any app**, dropped Holo's answer; each drop **used up a step** of the 30-step budget. `watch()` has the same flaw |
| 2 | "Go to YouTube" while already on YouTube; wanted to type `youtube.com/trending` | The Linkup playbook was generic (it didn't know the current page), and Holo followed it to the letter |
| 3 | "Ok, continue" became a new task (Chrome's "continue where you left off" setting!) | The router has no memory of the previous task |
| 4 | 2.2–5.1 s per step | Context keeps growing (playbook + notes + tool results) |

## Fixes
1. **No more re-plan storms**
   - Only input **in the task's app** counts (the task's app must be in front when the input is
     detected); other apps → quiet pause.
   - Stale re-plans **don't count** against the step budget (only real actions do).
   - Wait for input to go quiet **only if** there was recent input (no fixed delay otherwise).
   - Same rule in `watch()`. After a "type" step, typing = progress: keep watching until the
     pause, then re-plan **once**.
2. **"Where you already are"**
   - The front window title (e.g. "YouTube – Google Chrome") goes to Linkup ("starting from the
     YouTube home page, already open") and to Holo at every step.
   - Firm rule in the prompt: first tick off the playbook steps already done on screen; **never**
     send the person back to a site/app they're already on, never retype a URL; **teach the
     page's own navigation** (Explore → Trending).
   - No reading the URL via AppleScript (it would trigger a macOS permission prompt); the title
     plus Holo's own view of the address bar are enough.
3. **Speed**
   - Lean context: playbook + last 2 notes + last 3 screenshots; old tool results are trimmed.
   - **No fast/slow model split for now**: measured on the bench, `holo4-35b-a3b` without
     thinking (1.05 s) is no faster than `holo4-27b` "low" (1.0 s). We stay on 27B.
4. **Memory and "continue"**
   - "Continue / go on / reprends" while idle → **resume the unfinished task** (Memory already
     keeps it).
   - **Session brief**: a template summary updated instantly (task, app, last step, result),
     then **rewritten by GPT in the background** after each task (never blocking). Given to the
     router and to Holo. This is the first step of "GPT = unified memory".
5. **Voice**: every new instruction is spoken in short form; after an answer (`say`), it goes
   straight back to guiding.

## Risks (Devin)
- The model's step tracking can drift: Linkup's plan stays the reference, and step numbers are
  checked.
- Don't over-engineer "which app received the key": the front-window rule is enough.

Estimate: ~1 h 15. Fallback tag: `v3-demo` before starting.
