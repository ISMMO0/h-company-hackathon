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


BROWSERS = ("google chrome", "safari", "arc", "firefox", "microsoft edge", "brave browser")

LEARN = """You read the log of an assistant that just operated {site} on a Mac for a person.
Write up to 3 short lessons (max 20 words each) about {site}'s interface that would make the NEXT run
faster or more correct: exact places, what worked, what failed and the fix. Only facts about {site}
itself, nothing about this person or this specific data. If nothing useful, return an empty list.
Reply with JSON {{"lessons": ["...", "..."]}}."""


def site_of(app: str, title: str) -> str:
    """The real "app" behind a browser tab: 'Untitled spreadsheet - Google Sheets' → 'Google Sheets'."""
    if app.lower() in BROWSERS and title:
        last = re.split(r" [-–—|] ", title)[-1].strip()
        if 2 <= len(last) <= 40:
            return last
    return app


def learn(site: str, task: str, lines: list[str]) -> None:
    """After a task (background): add what this run taught about the site to its cheat sheet."""
    if not router.enabled() or not lines or site.lower() in ("", "finder", "electron", "claude"):
        return
    try:
        new = router._ask(LEARN.format(site=site), f"Task: {task}\nLog:\n" + "\n".join(lines)[:6000])
        lessons = [str(x)[:200] for x in new.get("lessons", []) if str(x).strip()][:3]
    except Exception:  # noqa: BLE001 - learning is best-effort
        return
    if not lessons:
        return
    f = DIR / f"{_slug(site)}.json"
    data = {}
    try:
        data = json.loads(f.read_text())
    except (OSError, ValueError):
        data = {"app": site, "sheet": "", "built": time.time()}
    old = data.get("lessons", [])
    data["lessons"] = (old + [x for x in lessons if x not in old])[-15:]
    DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def _slug(app: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", app.lower()).strip("-") or "app"


def cached(app: str) -> str:
    """The cheat sheet if we have a fresh one, else ''. Instant."""
    f = DIR / f"{_slug(app)}.json"
    try:
        data = json.loads(f.read_text())
        sheet = data.get("sheet", "") if time.time() - data.get("built", 0) < TTL else ""
        lessons = data.get("lessons", [])
        if lessons:  # what earlier runs taught: never expires
            sheet += "\nLessons from earlier runs:\n" + "\n".join(f"- {x}" for x in lessons)
        return sheet.strip()
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
        f = DIR / f"{_slug(app)}.json"
        try:
            lessons = json.loads(f.read_text()).get("lessons", [])
        except (OSError, ValueError):
            lessons = []
        f.write_text(json.dumps({"app": app, "sheet": sheet, "built": time.time(), "lessons": lessons},
                                ensure_ascii=False, indent=1))
    return sheet


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    for name in sys.argv[1:]:
        t = time.perf_counter()
        print(f"== {name} ({time.perf_counter() - t:.1f}s)\n{build(name)}", flush=True)
