# Bench: replay screenshots through planner + pointer

`scripts/bench.py` runs saved screenshots through `brain.planner.plan_step` (on a downscaled
copy) and, for clicks, `brain.planner.point` (on the full image), then reports latency per
stage and whether the point landed inside the expected element. Speed and prompt changes are
decided on these numbers, not by guessing (backend v2 plan, sections A and G).

```
.venv/bin/python scripts/bench.py                  # all fixtures, real Holo calls (needs .env)
.venv/bin/python scripts/bench.py --repeat 5       # 5 runs per fixture, medians in the table
.venv/bin/python scripts/bench.py --only youtube-search
.venv/bin/python scripts/bench.py --scale 1        # screenshots that are not Retina (1 px = 1 pt)
.venv/bin/python scripts/bench.py --dry-run        # fake planner, no API keys, checks the harness
```

## Adding a fixture

One directory per screen under `bench/fixtures/<name>/`:

```
bench/fixtures/youtube-search/
  screen.png   full native-resolution screenshot (Retina: 2x the point size)
  meta.json
```

`meta.json`:

```json
{
  "task": "search for lo-fi beats on YouTube",
  "app": "Safari",
  "hint": "Click the search box at the top, type the query, press Enter.",
  "expect": {"bbox": [1120, 90, 2240, 170]}
}
```

- `task`: what the user asked (what the planner receives).
- `app`: frontmost app, shown in the table.
- `hint` (optional): the Linkup how-to text the planner would have had.
- `expect` (optional): `bbox` = `[x0, y0, x1, y1]` of the element the next click should hit,
  in `screen.png` pixels. A run is a hit when the pointer's point is inside it. Without
  `expect` the fixture only measures latency. Get the box from Preview (Tools > Show Inspector)
  or any image editor.

Take `screen.png` with `screencapture -x screen.png` on the Mac at the moment the next step
should happen. Use short names (`<app>-<step>`), one step per fixture. `example/` is a tiny
synthetic fixture so `--dry-run` has something to run; replace it with real ones.
