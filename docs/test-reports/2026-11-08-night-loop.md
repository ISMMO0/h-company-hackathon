# Night test loop (Sat 23:50 → Sun ~02:30)

7 scenarios, run end to end by a harness: Do it scenarios are done by Shadow Cursor; for Guide
scenarios the harness plays the person (clicks/types where the pink cursor points). Rounds 2 and 5
are left out: round 2 was interrupted (the Claude app came to the front), round 5 hit an H API outage
and then the 20-tasks/day free quota.

| Scenario | Mode | R1 | R3 | R4 | R6 |
|---|---|---|---|---|---|
| Wikipedia: Eiffel Tower height | Do it | ✅ 51 s | ✅ 27 s | ✅ 27 s | ✅ **22 s** |
| Wikipedia: Louvre opening year | Guide | ✅ 54 s | ✅ 21 s | ✅ 22 s | ✅ **22 s** |
| Sheets: 3 numbers + SUM | Guide | ✅ 54 s | ✅ 33 s | ✅ 22 s | ✅ **23 s** |
| Docs: title + bulleted list | Do it | ❌ | ✅* 208 s | ✅ **82 s** | ❌ (test tabs) |
| Maps: transit time | Do it | ❌ | ❌ | ✅ **67 s** | ❌ |
| Sheets: order table + formulas | Do it | ✅ 91 s | ❌ (Claude in front) | ❌ (my bug, fixed) | ❌ (bad point) |
| YouTube: speed 0.75 | Guide | ❌ | ❌ | ❌ | ❌ |

\* done in Apple Pages instead of Google Docs (see safety below).

**The stable core (Wikipedia, Sheets in Guide) went from ~53 s to ~22 s** and passes every time.

## What changed tonight (all pushed)
- **Typing:** no stray click that moves the caret into existing text ("BreadEggs", "Votre pGare de
  Lyonosition"); the click is only skipped right after a Return in the same field.
- **Keys:** Home / End / Page Up / Page Down exist; an unknown key name is never typed as letters.
- **Guide:** "type 4 and press Return" is one step (was two); bubbles read `Type "4" and press Return`.
- **Safety in Do it** (tests in `tests/test_site_and_guard.py`):
  - never acts in Claude, terminals, editors or the control page (asks you to switch app);
  - stays in the task's app: no other app's windows, no ⌘Tab / ⌘Space / Dock / Applications;
  - never ⌘Q / ⌘W, never "Delete" / "Don't Save" unless the task asks to delete;
  - never types in the browser address bar (Chrome autocomplete opened a site from history).
- **Knowledge:**
  - real window titles via the Accessibility API (macOS was hiding them);
  - one cheat sheet per website (Google Sheets, Google Docs, YouTube…), not per browser;
  - after every task, GPT adds up to 3 lessons to that site's sheet, in the background;
  - the web playbook names the website ("In the Google Sheets website…"), never "On a Mac", which
    had sent Holo to Apple Pages.

## Still failing, and why
- **YouTube speed (Guide):** the new speed menu is a slider with −/+ (0.05 per click). Holo clicks
  the track and overshoots. Lessons were added; it still needs a run to confirm.
- **Sheets formulas (Do it):** the last failure was Holo pointing at the column header "A" instead of
  cell A1 (whole column selected, headers went down). Pointing variance, not logic.
- **Maps / Docs in round 6:** the test harness had opened dozens of tabs in your Chrome window; the
  tab bar overflowed and Holo looked for "the lost tab". A test artifact, not a product bug.

## Things for you to check (my side effects)
1. **A macOS prompt is on screen: "claude wants access to control Google Chrome".** My AppleScript
   test triggered it. I did not touch it: click **Don't Allow** (nothing needs it).
2. **TextEdit:** in round 3 (before the safety fix) the cursor clicked **Delete** in a TextEdit save
   dialog. If you had an unsaved TextEdit document, it may be gone. Sorry.
3. **Leftovers:** an "Untitled" Apple Pages document, a closed rekordbox update dialog, many test tabs
   in Chrome, and blank test Sheets/Docs in your Google Drive ("Feuille de calcul sans titre",
   "Document sans titre").
4. **`.env`:** `SHADOW_FREE_TASKS=1000` (the free quota blocked the tests; you said no Stripe).
