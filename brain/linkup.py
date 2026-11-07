"""Knowledge from the web, fetched before acting so Holo follows known steps instead of
exploring.

- playbook(): structured how-to steps for a task, before the first click
- answer():   a sourced answer for a pure question ("best Italian restaurant near Opéra")
- lookup():   a targeted how-to when the agent is stuck on one step
"""

import html
import json
import os

import requests

URL = "https://api.linkup.so/v1/search"

PLAYBOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "action_hint": {"type": "string", "description": "What to do, e.g. 'Open Settings'"},
            "target": {"type": "string", "description": "The exact UI element: label and where it usually is"},
            "why": {"type": "string", "description": "Why this step, in a few words, for a beginner"},
        }}},
        "note": {"type": "string", "description": "A shortcut or alternative worth knowing, or empty"},
    },
}


def _post(body: dict, timeout: float) -> dict:
    r = requests.post(URL, headers={"Authorization": f"Bearer {os.environ['LINKUP_API_KEY']}"},
                      json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def playbook(task: str, app: str, where: str = "", timeout: float = 6) -> dict:
    """{'steps': [{action_hint, target, why}], 'note': str}, or {} on failure.
    `where` is the front window title, so the steps start from the page the user is on."""
    here = f"The user is already on '{where}' in {app}: start from there, skip opening it. " if where \
        else f"The user currently has {app} open; only use {app} if the task is about it. "
    try:
        data = _post({
            "q": f"On a Mac, the exact UI path to: {task}. {here}"
                 "Use the app's or website's own navigation (menus, sidebar, buttons), not URL "
                 "shortcuts. Give 3 to 8 concrete steps with the exact menu, button or field names.",
            "depth": "fast", "outputType": "structured",
            "structuredOutputSchema": json.dumps(PLAYBOOK_SCHEMA),
        }, timeout)
        steps = [s for s in data.get("steps", []) if isinstance(s, dict) and s.get("action_hint")]
        return {"steps": steps[:8], "note": str(data.get("note") or "")}
    except Exception:  # noqa: BLE001 - knowledge is optional, the agent falls back to Holo alone
        return {}


def answer(question: str, timeout: float = 12) -> dict:
    """{'text': str, 'sources': [{'title', 'url'}]}, or {} on failure."""
    try:
        data = _post({"q": question + " Answer in 2-4 short sentences.",
                      "depth": "standard", "outputType": "sourcedAnswer"}, timeout)
        sources = [{"title": html.unescape(s.get("name", ""))[:80], "url": s.get("url", "")}
                   for s in data.get("sources", [])[:3] if s.get("url")]
        return {"text": plain(data.get("answer") or ""), "sources": sources}
    except Exception:  # noqa: BLE001
        return {}


def lookup(task: str, app: str, step: str, question: str = "", timeout: float = 6) -> str:
    """A targeted how-to for the step the agent is stuck on."""
    q = question or f"how to {step}"
    try:
        data = _post({"q": f"In {app} on a Mac, while trying to {task}: {q}. Exact menu, button "
                           "or field names and where they are on screen, in 1-3 short steps.",
                      "depth": "fast", "outputType": "sourcedAnswer"}, timeout)
        return plain(data.get("answer") or "")[:800]
    except Exception:  # noqa: BLE001
        return ""


def how_to(task: str, app: str) -> str:
    """Plain-text notes (kept for the old control-page path and scripts)."""
    pb = playbook(task, app)
    return "\n".join(f"{i}. {s['action_hint']} ({s.get('target', '')})"
                     for i, s in enumerate(pb.get("steps", []), 1))


def plain(text: str) -> str:
    """Drop markdown emphasis: the text is spoken and shown in a small panel."""
    return text.replace("**", "").replace("__", "").strip()
