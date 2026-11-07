"""Shadow Cursor brain: local server for the control page and the overlay.

    .venv/bin/python -m brain.server   →  http://127.0.0.1:8765
"""

import asyncio
import json
from pathlib import Path

from aiohttp import WSMsgType, web
from dotenv import load_dotenv

load_dotenv()

from brain.agent import Agent

STATIC = Path(__file__).parent / "static"
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


def main() -> None:
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws/overlay", overlay_ws), web.get("/ws/ui", ui_ws)])
    web.run_app(app, host="127.0.0.1", port=8765, print=lambda *_: print("Shadow Cursor → http://127.0.0.1:8765"))


if __name__ == "__main__":
    main()
