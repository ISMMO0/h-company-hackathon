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
