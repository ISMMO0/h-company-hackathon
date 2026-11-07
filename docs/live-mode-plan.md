# Live mode plan: always listening, always fast

Status: **approved Sat 18:20 by the team lead**, reviewed by Devin. Fallback tag `v3.1-demo`.

Goal: it should feel live, as if it watched the screen like a stream. As soon as you speak, the
cursor reacts; the heavy work (GPT, web) runs in the background and never makes you wait.

## Today (measured)
From the end of your sentence to the first cursor move: ~5–7 s, all in series (Gladia 0.8 s,
GPT 1 s, Linkup playbook ~4 s, Holo ~1.5 s). After an action: settle 0.5–2.5 s + plan 1–3 s.

## Changes
### 1. Open mic for the whole task
- ⌃⌥Space starts as today (push-to-talk, live text, ⌃⌥Space or 4 s of silence to send).
- Once a task runs, **the mic stays open**: every sentence (Gladia final, 0.8 s endpointing)
  is routed and applied without stopping the task.
- During a task, **⌃⌥Space / the 🎤 button = mic on/off**. ⌃⌥X still stops the task. The mic
  closes when the task ends.
- **Echo filter**: whatever the mic hears while Shadow is speaking (+0.4 s) is dropped.
- **"ignore" intent**: thinking out loud / small talk ("hmm", "ah da da") gets no reaction.

### 2. Fast path: the cursor moves on partial words
- While you speak, once the partial text is a UI request ("show me / where is / click / how do
  I…", ≥3 words), Holo **points** at the likely target on the latest screen (crop-free
  localization, ~0.5 s); the pink cursor glides there as **tentative** (semi-transparent,
  pulsing). It only shows, never clicks. Debounced to one call per ~0.5 s of new words.
- Speech start → a pulse on the cursor right away ("I hear you").

### 3. Non-blocking start
- The task starts **at once** with keyword routing; GPT routing runs in parallel and corrects
  (e.g. switches to the answer card if it was a pure question, or rewrites the task).
- The first Holo step runs **in parallel** with the Linkup playbook; the playbook joins the plan
  when it lands (never blocks). The first obvious move comes in ~1.5–2 s instead of ~6 s.

### 4. Plan on the first change
- After you act, planning starts at the **first** detected change (click/key/pixels) instead of
  after the screen settles; settling runs in parallel; if the screen keeps changing, that answer
  is dropped and re-planned on the settled screen (same rule as clicks/keys today).

## Expected
| Moment | Today | Live mode |
|---|---|---|
| End of sentence → cursor moves | ~5–7 s | **~0.5–1 s** (often while you speak) |
| Your action → next instruction | ~1.5–3 s | **~1–2 s** |
| You speak mid-task | push-to-talk + ~2 s | **open mic, ~1–2 s** |

## Not doing (yet)
- A true video stream: Holo works on images. Continuous background captures would flash the
  pink cursor (it must be hidden for each capture), so we keep cheap thumbnails + on-demand
  captures.
- Look-ahead on a predicted screen: not reliable; planning on the first change gets most of it.

## Split
- **Claude (brain)**: continuous listener + echo filter, ignore intent, fast path on partials,
  parallel start, plan-on-first-change.
- **Devin (overlay, protocol v6)**: open-mic indicator + last words in the panel, mic toggle state,
  tentative cursor (semi-transparent + pulse), speech-start pulse.
