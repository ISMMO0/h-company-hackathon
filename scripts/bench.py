"""Replay saved screenshots through the planner and pointer; report latency and hit rate.

    .venv/bin/python scripts/bench.py                 # all fixtures, real Holo calls
    .venv/bin/python scripts/bench.py --dry-run       # fake planner, no API keys needed
    .venv/bin/python scripts/bench.py --only youtube-search --repeat 5

Fixtures live in bench/fixtures/<name>/ (see bench/README.md).
"""

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "bench" / "fixtures"


# -- fake planner for --dry-run ---------------------------------------------------------------

def fake_plan_step(task: str, screenshot: Image.Image, hint: str = "") -> dict:
    t = time.perf_counter()
    time.sleep(0.01)
    return {"name": "click", "args": {"element": "fake target", "x": 500, "y": 500},
            "timings": {"plan": time.perf_counter() - t}}


def fake_point(full: Image.Image, element: str, rough: tuple[int, int] | None) -> tuple[int, int]:
    time.sleep(0.005)
    return rough or (500, 500)


# -- harness ----------------------------------------------------------------------------------

def load_fixtures(only: str | None) -> list[tuple[str, Path, dict]]:
    out = []
    for d in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
        if only and d.name != only:
            continue
        if not (d / "screen.png").exists() or not (d / "meta.json").exists():
            print(f"skip {d.name}: needs screen.png and meta.json")
            continue
        out.append((d.name, d / "screen.png", json.loads((d / "meta.json").read_text())))
    return out


def run_once(plan_step, point, full: Image.Image, meta: dict, scale: float) -> dict:
    small = full.resize((round(full.width / scale), round(full.height / scale)))
    t0 = time.perf_counter()
    res = plan_step(meta["task"], small, meta.get("hint", ""))
    t_plan = time.perf_counter() - t0
    name, args = res["name"], res.get("args", {})
    timings = dict(res.get("timings", {}))
    timings["plan_step"] = t_plan

    hit = None
    px = None
    if name == "click":
        rough = (args["x"], args["y"]) if "x" in args and "y" in args else None
        t1 = time.perf_counter()
        x, y = point(full, args.get("element", ""), rough)
        timings["point"] = time.perf_counter() - t1
        px = (x / 1000 * full.width, y / 1000 * full.height)
        bbox = (meta.get("expect") or {}).get("bbox")
        if bbox:
            hit = bbox[0] <= px[0] <= bbox[2] and bbox[1] <= px[1] <= bbox[3]
    timings["total"] = time.perf_counter() - t0
    return {"action": name, "hit": hit, "px": px, "timings": timings}


def pct(values: list[float], p: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, max(0, round(p / 100 * len(values) + 0.5) - 1))]


def ms(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds * 1000:.0f}"


def median(values: list[float]) -> float | None:
    return pct(values, 50) if values else None


def print_table(rows: list[list[str]]) -> None:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeat", type=int, default=1, help="runs per fixture (default 1)")
    ap.add_argument("--only", help="run a single fixture by directory name")
    ap.add_argument("--scale", type=float, default=2.0,
                    help="planner sees screen.png downscaled by this factor (default 2 = Retina)")
    ap.add_argument("--dry-run", action="store_true", help="fake planner/pointer, no API calls")
    args = ap.parse_args()

    if args.dry_run:
        plan_step, point = fake_plan_step, fake_point
    else:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        try:
            from brain.planner import plan_step, point
        except ImportError as e:
            sys.exit(f"cannot import brain.planner ({e}); try --dry-run")

    fixtures = load_fixtures(args.only)
    if not fixtures:
        sys.exit(f"no fixtures in {FIXTURES}" + (f" named {args.only!r}" if args.only else ""))
    print(f"{len(fixtures)} fixture(s), repeat {args.repeat}, scale {args.scale}"
          + (", DRY RUN (fake planner, numbers are meaningless)" if args.dry_run else ""))
    print()

    rows = [["fixture", "app", "action", "hit", "plan_step", "point", "total"]]
    all_timings: dict[str, list[float]] = {}
    hits = clicks = 0
    for name, png, meta in fixtures:
        full = Image.open(png).convert("RGB")
        runs = [run_once(plan_step, point, full, meta, args.scale) for _ in range(args.repeat)]
        for r in runs:
            for stage, s in r["timings"].items():
                all_timings.setdefault(stage, []).append(s)
        judged = [r for r in runs if r["hit"] is not None]
        hits += sum(r["hit"] for r in judged)
        clicks += len(judged)
        actions = sorted({r["action"] for r in runs})
        per = {k: [r["timings"][k] for r in runs if k in r["timings"]]
               for k in ("plan_step", "point", "total")}
        rows.append([name, meta.get("app", "-"), "/".join(actions),
                     f"{sum(r['hit'] for r in judged)}/{len(judged)}" if judged else "-",
                     ms(median(per["plan_step"])), ms(median(per["point"])),
                     ms(median(per["total"]))])
    print_table(rows)

    print()
    print(f"Latency per stage over all {args.repeat * len(fixtures)} runs (ms)")
    trows = [["stage", "p50", "p90", "n"]]
    for stage in sorted(all_timings, key=lambda k: (k == "total", k)):
        v = all_timings[stage]
        trows.append([stage, ms(pct(v, 50)), ms(pct(v, 90)), str(len(v))])
    print_table(trows)
    print()
    rate = f" ({hits / clicks:.0%})" if clicks else " (no click judged against expect.bbox)"
    print(f"Hit rate: {hits}/{clicks}{rate}")


if __name__ == "__main__":
    main()
