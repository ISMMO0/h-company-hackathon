# Test report: runs after the UI + voice changes (Sat ~23:50)

Cursor started from the new Home button, OpenAI "sage" voice, Do it mode. Claude only watched.

| Run | Task | Result | Time |
|---|---|---|---|
| 1 | Sheets: order table, Total = Quantity × Price formulas, Pizza quantity → 5 | ✅ D2 = 50, D3 = 24, D4 = 10 | **71 s** (was 163 s) |
| 2 | Wikipedia: find the Eiffel Tower article and its height | ✅ "330 metres (1,083 feet)", answer card shown | **31 s** |

Both appear in History with smart titles ("Create order table with formulas" in Spreadsheets,
"Check Eiffel Tower height" in Web & search) and a real time.

## Where the time goes (per step)
- Holo planning 1.2–4.7 s, pointing 0.4 s (once 5.0 s: the cap kicked in, as designed).
- **Most of the time is the voice:** 6–15 s per step, because Do it now finishes each explanation
  before the next action (what we asked for: teach, don't race). The first explanations are long
  (2 sentences).
- Teaching order worked: header row alone, then Pizza row with its formula, then the other rows together.

## To improve
- Linkup playbook went off-target on run 1 (it described **Apple Pages** instead of Google Sheets):
  the research query should use the page title (Google Sheets), not just "Google Chrome". Holo
  ignored it and followed the screen, so no harm this time.
- Shorter explanations after the first one (1 sentence), to cut the waits without losing the lesson.
- Pre-generate the next sentence's voice while the action runs (saves ~1.5 s per step).
