"""History page data: past tasks with a short smart title and a category, plus the UI color.

Titles come from GPT once per task (cached in data/history-titles.json); without GPT, the
request itself is shortened."""

import hashlib
import json
import re
from pathlib import Path

from brain import router

DATA = Path("data")
TITLES = DATA / "history-titles.json"
THEME = DATA / "theme.json"
DEFAULT_COLOR = "#ff3ea5"

TITLE_PROMPT = """You label a person's past computer tasks for a History page. For each numbered request,
give a short title (2-6 words, like "Order table with formulas", "Sync BPM in Rekordbox") and one
category among: Spreadsheets, Music & DJ, Video, Web & search, Writing, Settings, Other.
Reply with JSON {"items": [{"n": 1, "title": "...", "category": "..."}, ...]}."""


def _key(request: str) -> str:
    return hashlib.sha1(request.encode()).hexdigest()[:12]


def _fallback(request: str) -> dict:
    words = re.sub(r"\s+", " ", request).strip().split(" ")
    title = " ".join(words[:6]) + ("…" if len(words) > 6 else "")
    return {"title": title[:1].upper() + title[1:], "category": "Other"}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def items(tasks: list[dict]) -> list[dict]:
    """Newest first: {title, category, mode, request, result, at}."""
    cache = _load(TITLES, {})
    todo = [t["request"] for t in tasks if t.get("request") and _key(t["request"]) not in cache]
    if todo and router.enabled():
        try:
            listing = "\n".join(f"{i + 1}. {r[:300]}" for i, r in enumerate(todo))
            for it in router._ask(TITLE_PROMPT, listing).get("items", []):
                req = todo[int(it["n"]) - 1]
                cache[_key(req)] = {"title": str(it["title"])[:60], "category": str(it["category"])[:30]}
            DATA.mkdir(exist_ok=True)
            TITLES.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        except Exception:  # noqa: BLE001, S110 - titles are cosmetic: fall back below
            pass
    out = []
    for t in reversed(tasks):
        if not t.get("request"):
            continue
        label = cache.get(_key(t["request"])) or _fallback(t["request"])
        out.append({**label, "mode": t.get("mode", ""), "request": t["request"],
                    "result": t.get("result", ""), "at": t.get("at")})
    return out


def color() -> str:
    c = _load(THEME, {}).get("color", DEFAULT_COLOR)
    return c if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else DEFAULT_COLOR


def set_color(c: str) -> str:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", c or ""):
        raise ValueError("color must look like #ff3ea5")
    DATA.mkdir(exist_ok=True)
    THEME.write_text(json.dumps({"color": c}))
    return c
