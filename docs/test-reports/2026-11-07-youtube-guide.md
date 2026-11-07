# Test report: YouTube, Guide mode (Sat 18:05)

**Task:** "Show me how to find the most trending music videos on YouTube, open one of them, and comment on it"
**Setup:** v3.1 (`f140df2` + step logging). Claude played the user with a script: it waited 1.2 s
like a person, then did exactly what the pink cursor showed. Nothing was typed or posted;
the script stops before writing a comment.
**Result:** ❌ never got past step 1 of the plan (reaching "Explore"). Stopped after 5 min, 18 actions.

## What happened
| Time | What |
|---|---|
| 0–9 s | Task start, Linkup playbook in **5.5 s**: Explore → Music → Trending music videos → video → comments |
| 9–94 s | Holo hunts for "Explorer" in the sidebar: scroll down ×2, scroll up ×3, "More" ×1, hamburger menu ×4, "click an empty area to focus" (landed on a channel by accident), YouTube logo ×2 |
| 95–211 s | 117 s with no reaction: the last scroll changed nothing on screen, so nothing triggered the next step |
| 234 s | Gives up and points at the address bar to type a URL (despite the "no URL" rule), after a **9.1 s** plan |

## Why
1. **Outdated knowledge.** YouTube **retired the Trending page in July 2025**; trending music now lives in
   **YouTube Charts → Music Videos**. Linkup's playbook still described the old path, and nothing checked it.
   (Confirmed by a Linkup answer, sources: documentarytube.com, async.com.)
2. **The "stuck" detector never fired.** It compares actions including the `why` text, which changes on
   every step, so "click the hamburger menu" ×4 never counted as a repeat. Scroll up/down oscillation isn't
   detected at all.
3. **No progress check.** 18 actions, still on plan step 1: nothing notices "no progress".
4. **Scroll has no position.** The pink cursor can't show *where* to scroll; a scroll that changes nothing
   leaves the agent waiting.
5. **Bad actions.** "Click an empty area to focus the sidebar", and the URL shortcut as a last resort.

## What was good
- **Reactivity:** after each action, the next instruction comes in **1.1–2.8 s** in most steps (capture
  0.2 s, Holo plan 1.1–2.8 s, pointing 0.4 s).
- **Precise pointing:** every click landed on what Holo described (hamburger, "More", logo).
- **No more re-planning storms:** 1 single "re-planning (key)" in 5 minutes (it was dozens before).
- **Starts from the current page:** no "go to youtube.com" at the start.

## Timings
| Stage | Typical | Worst |
|---|---|---|
| Linkup playbook (once) | 5.5 s | 6.5 s |
| Holo planning per step | 1.1–2.8 s | **9.1 s** (5 steps above 4 s) |
| Pointing (crop) | 0.4 s | 0.4 s |

## Proposed fixes
1. **Fresh knowledge:** the playbook asks Linkup for the path **as of today** ("if the feature was removed or
   renamed, say so and give the replacement"). Here that gives YouTube Charts → Music Videos.
2. **Stuck detection that works:** compare actions without `why`; count oscillations (scroll up/down,
   same click) and **"no progress": 5 actions without moving to the next plan step** → targeted Linkup
   lookup (with the screen title), then if that's not enough, say so and suggest the alternative.
3. **Scroll with a position:** `scroll` gets x,y; the pink cursor shows where to scroll. If nothing moves
   after 4 s, the agent re-checks on its own.
4. **Rules:** never "click an empty area"; the URL is only a last resort and is announced as such.
5. **Plan spikes:** if Holo takes more than 4 s, start a fast call in parallel (no thinking) and keep
   whichever answers first.
