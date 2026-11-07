# Test report: Google Sheets, Do it mode (Sat ~20:45)

**Task (Do it):** "Create a small budget table: headers Item, Quantity, Price in row 1, then three rows:
Pizza 4 12, Drinks 10 2, Stickers 50 0.5. Explain what you're doing." on a new blank Google Sheet.
Started from the control page; Claude only watched (log + screenshots).

## Run 1 (`7800bbe`): ❌ 1 row of 3 in 4 minutes
| | |
|---|---|
| What it did | Headers + "Pizza 4 12", one cell per action (type, Tab, type, Tab…), all correctly pointed |
| Speed | ~3.5 s per action, ~35 s per row |
| Blocked | 149 s: the "no progress" detector fired (a table row is ONE plan step but ~5 actions), then it paused and waited for the person |
| Noise | The open mic picked up "There's a block of a gas station" (TV/music) and GPT added it to the task |

## Fixes (`535ca37`)
- **Whole rows in one action:** `type` accepts `\t` (Tab) and `\n` (Return); Holo is told to type a full
  row or form at once in Do it mode.
- **"No progress" = the screen didn't change** for 3 actions (not "same plan step").
- **Noise never changes the task:** unrelated words (TV, lyrics, other people) → ignore.
- Snappier Do it delays (show 0.45 s before a click, 0.4 s after).

## Run 2 (`535ca37`): ✅ done in ~10 s
| Moment | Time |
|---|---|
| Task start (after the 3 s countdown) | 0 s |
| Linkup playbook (in the background) | 4.3 s |
| Holo plans the whole table as ONE `type` action | plan 2.5 s + point 0.9 s |
| Typing 4 rows (with Tab/Return) | 3.9 s |
| Holo checks the screen and says it's done | ~2.8 s |
| **Total** | **~9.7 s** |

Result in the sheet: Item/Quantity/Price, Pizza 4 12, Drinks 10 2, Stickers 50 0.5. All correct.

## Still to improve
- **Locale:** "0.5" stays text in a French-locale sheet (it expects "0,5"); Holo could check the sheet's
  number format (left-aligned number = text) and fix it.
- The final message contains a Markdown table: fine in the panel, but only the first sentence is spoken.
- Explanations: with one action for the whole table, there's one narration ("Typing the whole table…"),
  less of a step-by-step lesson. For teaching, Guide mode is the better fit.
