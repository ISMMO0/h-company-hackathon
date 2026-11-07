# Test report: Google Sheets formulas, Do it mode (Sat ~22:30)

**Task (Do it):** "Create an order table with headers Item, Quantity, Price, Total. Rows: Pizza 10 10,
Burger 3 8, Soda 5 2. Total must be a formula, Quantity times Price. Then change the Pizza quantity to 5
and check the total becomes 50. Explain what you're doing." on a new blank sheet. Claude only watched.

## Earlier runs
- Run 1 (`0111ccb`): ❌ Order table rows spilled onto one line: `10⇥⏎` (Return on an empty cell opens it
  in Sheets). Holo API timeouts (14–17 s to point).
- Run 2 (`63113a5`, fixes: no Tab before Return, formulas typed in the row, 5 s pointing cap): reached
  quantity 5 but lost 40 s to "Thank you." (TV) being routed as "wait", and once typed formulas from A2.

## Run 3 (`4cf7bf4`, "Do it teaches"): ✅ correct in ~80 s
| Step | What | Time |
|---|---|---|
| 1 | Whole table typed in one action (headers + 3 rows) | plan 13.2 s (mic noise re-plans) |
| 2 | Click D2, explains the first formula | ~9 s |
| 3 | Types `=B2*C2`, `=B3*C3`, `=B4*C4` | ~13 s |
| 4–5 | Click B2, type 5 ("the moment of truth") | ~26 s |
| ✓ | Total D2 = 50, D3 = 24, D4 = 10 (checked on screen) | 89.7 s from start |

## Still to fix
- **Teaching:** it explained the formula step, but still typed the whole data table and all three
  formulas in one action each. The "first time: small steps" rule is only partly followed.
- **Mic noise:** "I" was routed as a question and "Thank you." as "ahead", costing ~15 s of re-plans.
  Very short, task-unrelated phrases should be ignored.
- The last GUIDE-style label ("Type "5" here") stays on screen after the task is done.

## Fixes (`47cac0d`, `3b2b679`)
- First header row, first data row and first formula are typed one at a time (enforced in code, not only
  asked in the prompt), each one narrated; after that, the rest may go in one action.
- 1–2 word phrases with no command in them ("I", "Thank you.") are ignored during a task.
- Changing a cell = select it and type (a double-click then type gave "510"); after a double-click the
  text is replaced (⌘A) instead of inserted.
- The last bubble ("Type "5" here") is cleared when the task ends, even if the last action was a key press.

## Run 4 (`47cac0d`): ✅ teaching works; found the "510" bug (fixed in `3b2b679`)
Header alone → "Pizza 10 10 =B2*C2" alone → Burger and Soda together. No noise picked up. 132 s.

## Run 5 (`3b2b679`): ✅ correct, taught step by step, bubble cleared: 163 s
Headers → Pizza → Burger → Soda (one row each) → click D2 → type `=B2*C2` with an explanation → Return →
accepts Sheets' own "auto-fill" suggestion (⌘Return) to copy the formula down → B2 = 5 → **D2 = 50**,
D3 = 24, D4 = 10, checked on screen. No noise re-plans.
- Slower than needed: Holo now does every row on its own even after the pattern was shown.
- Once, an unexpected Sheets dialog (Tab key) got in the way; Holo closed it and typed the 5 again.
