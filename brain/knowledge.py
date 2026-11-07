"""App knowledge packs: a short, up-to-date cheat sheet per app, built once from the web and
cached, so Holo knows the app's layout before the first click and nothing waits on it later.

    python -m brain.knowledge rekordbox        # prewarm before a demo
"""

import json
import re
import sys
import time
from pathlib import Path

from brain import linkup, router

DIR = Path("data/knowledge")
TTL = 7 * 24 * 3600

SCHEMA = {
    "type": "object",
    "properties": {
        "version_note": {"type": "string", "description": "Current version and anything renamed or removed recently"},
        "areas": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "where": {"type": "string", "description": "Where on screen"},
            "what": {"type": "string"}}}},
        "common_tasks": {"type": "array", "items": {"type": "object", "properties": {
            "task": {"type": "string"}, "path": {"type": "string", "description": "Exact menus/buttons"}}}},
    },
}

CONDENSE = """Condense this app guide into a cheat sheet another model reads before guiding a person on screen.
Max 22 short lines: first the version / recent changes, then the main screen areas (name: where, what), then
common tasks as exact click paths. Only what the notes support. Reply with JSON {"sheet": "..."}."""


def _slug(app: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", app.lower()).strip("-") or "app"


def cached(app: str) -> str:
    """The cheat sheet if we have a fresh one, else ''. Instant."""
    f = DIR / f"{_slug(app)}.json"
    try:
        data = json.loads(f.read_text())
        if time.time() - data.get("built", 0) < TTL:
            return data.get("sheet", "")
    except (OSError, ValueError):
        pass
    return ""


def build(app: str, where: str = "") -> str:
    """Research the app (Linkup), condense it (GPT if available), cache it. ~5-10 s."""
    if app.lower() in ("", "finder", "electron", "claude"):
        return ""
    site = f" (currently on {where})" if where and app.lower() in ("google chrome", "safari", "arc", "firefox") else ""
    try:
        data = linkup._post({
            "q": f"Up-to-date guide to the {app}{site} interface on Mac, as of today: current version and "
                 "anything renamed or removed recently, the main screen areas and where they are, and the "
                 "exact click paths for the 8 most common tasks.",
            "depth": "standard", "outputType": "structured", "structuredOutputSchema": json.dumps(SCHEMA),
        }, 25)
    except Exception:  # noqa: BLE001
        return ""
    raw = json.dumps(data, ensure_ascii=False)
    sheet = ""
    if router.enabled():
        try:
            sheet = str(router._ask(CONDENSE, raw).get("sheet", ""))
        except Exception:  # noqa: BLE001
            sheet = ""
    if not sheet:
        lines = [data.get("version_note", "")]
        lines += [f"{a.get('name')}: {a.get('where')} ({a.get('what')})" for a in data.get("areas", [])[:8]]
        lines += [f"{t.get('task')}: {t.get('path')}" for t in data.get("common_tasks", [])[:8]]
        sheet = "\n".join(x for x in lines if x)
    sheet = sheet[:2500]
    if sheet:
        DIR.mkdir(parents=True, exist_ok=True)
        (DIR / f"{_slug(app)}.json").write_text(json.dumps(
            {"app": app, "sheet": sheet, "built": time.time()}, ensure_ascii=False, indent=1))
    return sheet


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    for name in sys.argv[1:]:
        t = time.perf_counter()
        print(f"== {name} ({time.perf_counter() - t:.1f}s)\n{build(name)}", flush=True)
