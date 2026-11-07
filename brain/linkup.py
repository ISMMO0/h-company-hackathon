"""Fetch short how-to notes from the web so Holo doesn't guess menus."""

import os

import requests


def how_to(task: str, app: str) -> str:
    try:
        r = requests.post(
            "https://api.linkup.so/v1/search",
            headers={"Authorization": f"Bearer {os.environ['LINKUP_API_KEY']}"},
            json={"q": f"On a Mac, step by step, which menus and buttons to click to: {task}. "
                       f"The user currently has {app} open; only use it if the task is about "
                       f"{app}. Answer in 3-6 short numbered steps.",
                  "depth": "fast", "outputType": "sourcedAnswer"},
            timeout=12,
        )
        r.raise_for_status()
        return (r.json().get("answer") or "").strip()[:1200]
    except Exception:  # noqa: BLE001 - hints are optional
        return ""
