"""Shadow Cursor brain: local server for the control page and the overlay.

    .venv/bin/python -m brain.server   →  http://127.0.0.1:8765
"""

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

from aiohttp import WSMsgType, web
from dotenv import load_dotenv

load_dotenv()

from brain import billing, history
from brain.agent import Agent

STATIC = Path(__file__).parent / "static"
BASE_URL = "http://127.0.0.1:8765"
overlays: set[web.WebSocketResponse] = set()
uis: set[web.WebSocketResponse] = set()


async def _send(targets: set, msg: dict) -> None:
    for ws in list(targets):
        try:
            await ws.send_json(msg)
        except ConnectionError:
            targets.discard(ws)


agent = Agent(to_overlay=lambda m: _send(overlays, m), to_ui=lambda m: _send(uis, m))
agent.overlay_connected = lambda: bool(overlays)


async def index(_req: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC / "index.html")


async def overlay_ws(req: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    overlays.add(ws)
    await ws.send_json({"type": "theme", "color": history.color()})
    await agent.log("Overlay connected")
    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            continue
        data = json.loads(msg.data)
        kind = data.get("type")
        if kind == "hidden":
            agent.hidden.set()
        elif kind in ("hotkey", "mic"):
            asyncio.create_task(agent.on_hotkey())
        elif kind == "stop":
            asyncio.create_task(agent.on_stop())
        elif kind == "next":
            agent.push("next")
        elif kind == "mode":
            agent.set_mode(data.get("mode", "guide"))
        elif kind == "followup":
            asyncio.create_task(agent.followup(data.get("mode", "guide")))
    overlays.discard(ws)
    return ws


async def ui_ws(req: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    uis.add(ws)
    await ws.send_json({"type": "overlay", "connected": bool(overlays)})
    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            continue
        data = json.loads(msg.data)
        kind = data.get("type")
        if kind == "start" and data.get("task", "").strip():
            agent.start(data["task"].strip(), data.get("mode", "guide"))
        elif kind == "stop":
            await agent.on_stop()
        elif kind == "next":
            agent.push("next")
        elif kind == "mode":
            agent.set_mode(data.get("mode", "guide"))
    uis.discard(ws)
    return ws


async def billing_status(_req: web.Request) -> web.Response:
    return web.json_response({"pro": billing.is_pro(), "tasks_left": billing.tasks_left()})


async def billing_checkout(_req: web.Request) -> web.Response:
    try:
        url = await asyncio.to_thread(billing.create_checkout, BASE_URL)
    except billing.ERRORS as e:
        return web.json_response({"error": re.sub(r"sk_\w+", "sk_***", str(e))}, status=500)
    return web.json_response({"url": url})


async def billing_success(req: web.Request) -> web.Response:
    session_id = req.query.get("session_id", "")
    try:
        ok = bool(session_id) and await asyncio.to_thread(billing.verify, session_id)
    except billing.ERRORS:
        ok = False
    text = "Shadow Pro is active, you can close this tab" if ok else "Payment not confirmed yet"
    html = ("<!doctype html><meta charset=utf-8><title>Shadow Pro</title>"
            "<body style=\"margin:0;display:grid;place-items:center;height:100vh;"
            "font:17px -apple-system,BlinkMacSystemFont,sans-serif\">"
            f"<p><span style=\"color:#ff3ea5\">●</span> {text}</p>")
    return web.Response(text=html, content_type="text/html")


async def history_list(_req: web.Request) -> web.Response:
    items = await asyncio.to_thread(history.items, agent.memory.tasks)
    return web.json_response({"items": items})


async def theme_get(_req: web.Request) -> web.Response:
    return web.json_response({"color": history.color()})


async def theme_set(req: web.Request) -> web.Response:
    try:
        color = history.set_color((await req.json()).get("color", ""))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    await _send(overlays, {"type": "theme", "color": color})  # the pink cursor changes too
    return web.json_response({"color": color})


async def overlay_start(_req: web.Request) -> web.Response:
    """'Get your Shadow Cursor': start the pink cursor (Electron overlay) if it isn't running."""
    if overlays:
        return web.json_response({"running": True, "started": False})
    npm = shutil.which("npm") or "/opt/homebrew/bin/npm"
    await asyncio.create_subprocess_exec(npm, "start", cwd=Path(__file__).parent.parent / "overlay",
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         start_new_session=True)
    for _ in range(40):  # it connects back in ~2 s
        await asyncio.sleep(0.25)
        if overlays:
            return web.json_response({"running": True, "started": True})
    return web.json_response({"running": False, "started": True})


def main() -> None:
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws/overlay", overlay_ws), web.get("/ws/ui", ui_ws),
                    web.get("/billing", billing_status), web.post("/billing/checkout", billing_checkout),
                    web.get("/billing/success", billing_success), web.get("/history", history_list),
                    web.get("/theme", theme_get), web.post("/theme", theme_set),
                    web.post("/overlay/start", overlay_start)])
    web.run_app(app, host="127.0.0.1", port=8765, print=lambda *_: print("Shadow Cursor → http://127.0.0.1:8765"))


if __name__ == "__main__":
    main()
