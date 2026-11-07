"""Shadow Cursor brain: local server for the control page and the overlay.

    .venv/bin/python -m brain.server   →  http://127.0.0.1:8765
"""

import asyncio
import base64
import io
import json
import subprocess
import time
from pathlib import Path

from aiohttp import WSMsgType, web
from dotenv import load_dotenv
from PIL import ImageDraw

load_dotenv()

from brain import holo, linkup, screen, voice

STATIC = Path(__file__).parent / "static"
MAX_STEPS = 15


class Brain:
    def __init__(self) -> None:
        self.overlays: set[web.WebSocketResponse] = set()
        self.uis: set[web.WebSocketResponse] = set()
        self.hidden = asyncio.Event()
        self.next_step = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.stopped = False
        self.say_proc: subprocess.Popen | None = None
        self.listening = False
        self.default_mode = "guide"  # follows the toggle on the control page

    # --- outputs -------------------------------------------------------------
    async def to_overlay(self, msg: dict) -> None:
        for ws in list(self.overlays):
            try:
                await ws.send_json(msg)
            except ConnectionError:
                self.overlays.discard(ws)

    async def to_ui(self, msg: dict) -> None:
        for ws in list(self.uis):
            try:
                await ws.send_json(msg)
            except ConnectionError:
                self.uis.discard(ws)

    async def log(self, text: str) -> None:
        print(text, flush=True)
        await self.to_ui({"type": "log", "text": text})

    def speak(self, text: str) -> None:
        self.hush()
        # Speak only the first sentence: long replies were picked up by the mic next time.
        first = text.split(". ")[0].strip()
        self.say_proc = subprocess.Popen(["say", "-r", "190", first[:160]])

    def hush(self) -> None:
        if self.say_proc and self.say_proc.poll() is None:
            self.say_proc.terminate()

    async def snapshot(self):
        """Screenshot without the pink cursor in it."""
        if self.overlays:
            self.hidden.clear()
            await self.to_overlay({"type": "hide"})
            try:
                await asyncio.wait_for(self.hidden.wait(), 0.5)
            except TimeoutError:
                pass
        img = await asyncio.to_thread(screen.capture)
        await self.to_overlay({"type": "show"})
        return img

    async def send_preview(self, img, point=None, label="") -> None:
        im = img.copy()
        if point:
            d = ImageDraw.Draw(im)
            x, y = point
            d.ellipse((x - 14, y - 14, x + 14, y + 14), outline="#ff3ea5", width=5)
            d.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#ff3ea5")
        im.thumbnail((900, 900))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=70)
        await self.to_ui({"type": "preview", "label": label,
                          "image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()})

    # --- the loop ------------------------------------------------------------
    async def run(self, task: str, mode: str, countdown: bool = True) -> None:
        self.stopped = False
        stop = lambda: self.stopped
        try:
            for n in (3, 2, 1) if countdown else ():
                await self.to_ui({"type": "status", "text": f"Switch to your app… {n}"})
                await asyncio.sleep(1)
            app = screen.frontmost_app()
            await self.to_ui({"type": "status", "text": f"Working in {app}"})
            await self.log(f"▶ {mode.upper()} in {app}: {task}")
            self.speak("On it.")

            hint = await asyncio.to_thread(linkup.how_to, task, app)
            if hint:
                await self.log(f"Linkup notes:\n{hint}")
            messages = holo.new_conversation(task, hint)
            w, h = screen.screen_size()

            for i in range(MAX_STEPS):
                if self.stopped:
                    break
                img = await self.snapshot()
                messages.append(holo.observation(img))
                t0 = time.perf_counter()
                name, args, call_id = await asyncio.to_thread(holo.step, messages)
                await self.log(f"Step {i + 1}: {name} {args}  ({time.perf_counter() - t0:.1f}s)")
                if not name:
                    continue
                if name == "answer":
                    text = args.get("content", "Done.")
                    await self.send_preview(img, label=text)
                    await self.log(f"✓ {text}")
                    self.speak(text)
                    break

                result = await self.act(mode, name, args, img, w, h, stop)
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
                await asyncio.sleep(0.8)  # let the UI react
            else:
                await self.log("Step budget reached.")
        except Exception as e:  # noqa: BLE001 - surface any failure in the UI
            await self.log(f"Error: {type(e).__name__}: {e}")
        finally:
            await self.to_overlay({"type": "clear"})
            await self.to_ui({"type": "status", "text": "Idle"})

    async def act(self, mode, name, args, img, w, h, stop) -> str:
        front = screen.frontmost_app()
        if mode == "do" and front in screen.SYSTEM_APPS:
            return await self.blocked(front)
        if name == "click":
            x, y = args["x"] / 1000 * w, args["y"] / 1000 * h
            owner = screen.window_owner_at(x, y)
            if mode == "do" and owner in screen.SYSTEM_APPS:
                return await self.blocked(owner)
            label = f"Click {args.get('element', '')}".strip()
            await self.to_overlay({"type": "cursor", "x": x, "y": y, "label": label})
            await self.send_preview(img, (x, y), label)
            self.speak(label)
            if mode == "do":
                await asyncio.sleep(0.9)
                await asyncio.to_thread(screen.click, x, y)
                return "Clicked."
            await self.to_ui({"type": "status", "text": "Your turn: click where the pink cursor points"})
            pos = await asyncio.to_thread(screen.wait_for_user_click, stop)
            return "The user clicked it." if pos else "No click."

        if name == "type":
            text = args.get("text", "")
            label = f'Type "{text}"'
            await self.send_preview(img, label=label)
            self.speak(label)
            if mode == "do":
                await asyncio.to_thread(screen.type_text, text)
                return "Typed."
            return await self.wait_next("The user typed it.")

        if name == "press":
            keys = args.get("keys", "")
            label = f"Press {keys}"
            await self.send_preview(img, label=label)
            self.speak(label)
            if mode == "do":
                await asyncio.to_thread(screen.press, keys)
                return "Pressed."
            return await self.wait_next("The user pressed it.")

        if name == "scroll":
            direction = args.get("direction", "down")
            if mode == "do":
                await asyncio.to_thread(screen.scroll, direction)
                return "Scrolled."
            self.speak(f"Scroll {direction}")
            return await self.wait_next("The user scrolled.")

        return f"Unknown action {name}."

    async def blocked(self, app: str) -> str:
        """A system/permission dialog is in the way: never act on it, hand control back."""
        text = f"A system dialog from {app} needs you. Please handle it yourself, then press Next."
        await self.log(f"⚠ {text}")
        self.speak("A system dialog needs you. Please handle it yourself.")
        return await self.wait_next(
            "The person handled the system dialog. Do not interact with system dialogs.")

    async def wait_next(self, done: str) -> str:
        self.next_step.clear()
        await self.to_ui({"type": "status", "text": "Your turn — press Next when done"})
        while not self.next_step.is_set() and not self.stopped:
            await asyncio.sleep(0.1)
        return done

    def start(self, task: str, mode: str, countdown: bool = True) -> None:
        self.stop()
        self.task = asyncio.create_task(self.run(task, mode, countdown))

    async def on_hotkey(self) -> None:
        """⌃⌥Space: stop if busy, otherwise listen once and start in the current app."""
        if self.listening:
            return
        if self.task and not self.task.done():
            self.stop()
            await self.to_overlay({"type": "clear"})
            await self.log("■ Stopped")
            self.speak("Stopped.")
            return
        self.listening = True
        self.hush()  # never transcribe our own voice
        await asyncio.sleep(0.15)
        await self.to_overlay({"type": "listening", "on": True})
        await self.to_ui({"type": "status", "text": "Listening…"})
        try:
            text = await voice.listen_once(
                on_partial=lambda t: asyncio.create_task(self.to_ui({"type": "status", "text": f"… {t}"})))
        except Exception as e:  # noqa: BLE001 - mic or network failure
            await self.log(f"Voice error: {type(e).__name__}: {e}")
            text = ""
        finally:
            self.listening = False
            await self.to_overlay({"type": "listening", "on": False})
        if not text:
            await self.to_ui({"type": "status", "text": "Didn't catch that"})
            return
        await self.log(f'🎙 "{text}"')
        await self.to_ui({"type": "heard", "text": text})
        self.start(text, mode_from(text, self.default_mode), countdown=False)

    def stop(self) -> None:
        self.stopped = True
        self.next_step.set()
        if self.task and not self.task.done():
            self.task.cancel()


DO_WORDS = ("do it", "do this", "for me", "fais-le", "fais le", "à ma place", "fais-moi", "fais moi")


def mode_from(text: str, default: str) -> str:
    """'…do it for me' / '…fais-le' switches to DO; 'show me' / 'montre-moi' to GUIDE."""
    t = text.lower()
    if any(w in t for w in DO_WORDS):
        return "do"
    if "show me" in t or "montre" in t or "guide" in t:
        return "guide"
    return default


brain = Brain()


async def index(_req: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC / "index.html")


async def overlay_ws(req: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    brain.overlays.add(ws)
    await brain.log("Overlay connected")
    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            continue
        kind = json.loads(msg.data).get("type")
        if kind == "hidden":
            brain.hidden.set()
        elif kind == "hotkey":
            asyncio.create_task(brain.on_hotkey())
    brain.overlays.discard(ws)
    return ws


async def ui_ws(req: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    brain.uis.add(ws)
    await ws.send_json({"type": "overlay", "connected": bool(brain.overlays)})
    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            continue
        data = json.loads(msg.data)
        if data.get("type") == "start" and data.get("task", "").strip():
            brain.start(data["task"].strip(), data.get("mode", "guide"))
        elif data.get("type") == "stop":
            brain.stop()
            await brain.to_overlay({"type": "clear"})
            await brain.log("■ Stopped")
        elif data.get("type") == "next":
            brain.next_step.set()
        elif data.get("type") == "mode":
            brain.default_mode = data.get("mode", "guide")
    brain.uis.discard(ws)
    return ws


def main() -> None:
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws/overlay", overlay_ws), web.get("/ws/ui", ui_ws)])
    web.run_app(app, host="127.0.0.1", port=8765, print=lambda *_: print("Shadow Cursor → http://127.0.0.1:8765"))


if __name__ == "__main__":
    main()
