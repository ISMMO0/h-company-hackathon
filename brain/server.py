"""Shadow Cursor brain: local server for the control page and the overlay.

    .venv/bin/python -m brain.server   →  http://127.0.0.1:8765
"""

import asyncio
import base64
import io
import json
import re
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
        self.mode = "guide"  # mode of the running task; the panel toggle switches it live
        self.full = None  # last native-resolution screenshot, for precise pointing
        self.said: list[str] = []  # things the person said mid-task, not yet given to Holo
        self.done_steps: list[str] = []
        self.roadmap: list[str] = []

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
        self.full = await asyncio.to_thread(screen.capture_full)
        await self.to_overlay({"type": "show"})
        return self.full.resize(screen.screen_size())

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
    async def panel(self, text: str, state: str) -> None:
        await self.to_overlay({"type": "step", "text": text, "mode": self.mode, "state": state})
        await self.to_ui({"type": "status", "text": f"{state}: {text}" if text else state})

    async def plan(self, current: str = "") -> None:
        """Details view: what's done, what's happening, and the web how-to as a roadmap."""
        steps = [{"text": t, "status": "done"} for t in self.done_steps[-12:]]
        if current:
            steps.append({"text": current, "status": "current"})
        steps += [{"text": t, "status": "todo"} for t in self.roadmap]
        await self.to_overlay({"type": "plan", "steps": steps})

    async def chat(self, who: str, text: str) -> None:
        await self.to_overlay({"type": "chat", "who": who, "text": text})

    async def run(self, task: str, mode: str, countdown: bool = True) -> None:
        self.stopped = False
        self.mode = mode
        self.said, self.done_steps, self.roadmap = [], [], []
        try:
            for n in (3, 2, 1) if countdown else ():
                await self.to_ui({"type": "status", "text": f"Switch to your app… {n}"})
                await asyncio.sleep(1)
            app = screen.frontmost_app()
            await self.log(f"▶ {mode.upper()} in {app}: {task}")
            await self.panel(task, "thinking")
            await self.chat("you", task)
            self.speak("On it.")

            hint = await asyncio.to_thread(linkup.how_to, task, app)
            if hint:
                await self.log(f"Linkup notes:\n{hint}")
                self.roadmap = roadmap_from(hint)
                await self.plan()
            messages = holo.new_conversation(task, hint)
            w, h = screen.screen_size()
            last_label = ""

            for i in range(MAX_STEPS):
                if self.stopped:
                    break
                while self.said:
                    messages.append({"role": "user", "content":
                                     f"The person just said: \"{self.said.pop(0)}\". Take it into account."})
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
                    await self.panel(text, "done")
                    await self.chat("shadow", text)
                    self.roadmap = []
                    await self.plan()
                    self.speak(text)
                    await asyncio.sleep(6)
                    break

                result = await self.act(name, args, img, w, h, repeat=(label_of(name, args) == last_label))
                last_label = label_of(name, args)
                if not self.done_steps or self.done_steps[-1] != last_label:
                    self.done_steps.append(last_label)
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            else:
                await self.log("Step budget reached.")
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - surface any failure in the UI
            await self.log(f"Error: {type(e).__name__}: {e}")
        finally:
            await self.to_overlay({"type": "clear"})
            await self.to_ui({"type": "status", "text": "Idle"})

    async def act(self, name, args, img, w, h, repeat=False) -> str:
        """Show the step, then do it (DO) or watch the person do it (GUIDE)."""
        front = screen.frontmost_app()
        if self.mode == "do" and front in screen.SYSTEM_APPS:
            return await self.blocked(front)
        label = label_of(name, args)
        point = None
        if name == "click":
            nx, ny = args["x"], args["y"]
            if self.full is not None and args.get("element"):
                refined = await asyncio.to_thread(holo.localize, self.full, args["element"])
                if refined:
                    nx, ny = refined
            point = (nx / 1000 * w, ny / 1000 * h)
            if self.mode == "do" and screen.window_owner_at(*point) in screen.SYSTEM_APPS:
                return await self.blocked(screen.window_owner_at(*point))
            await self.to_overlay({"type": "cursor", "x": point[0], "y": point[1], "label": short(label)})
        await self.send_preview(img, point, label)
        await self.plan(label)
        if not repeat:
            await self.chat("shadow", label)
            self.speak(label)

        if self.mode == "do":
            await self.panel(label, "acting")
            await asyncio.sleep(0.9 if point else 0.4)
            if name == "click":
                await asyncio.to_thread(screen.click, *point)
            elif name == "type":
                await asyncio.to_thread(screen.type_text, args.get("text", ""))
            elif name == "press":
                await asyncio.to_thread(screen.press, args.get("keys", ""))
            elif name == "scroll":
                await asyncio.to_thread(screen.scroll, args.get("direction", "down"))
            await asyncio.sleep(0.8)  # let the app react
            return "Done."

        await self.panel(label, "waiting")
        why = await self.watch()
        if self.said:
            return "The person spoke instead (see their message). This step may not be done yet."
        if why == "next":
            return "The person pressed Next: they did this step or want to skip it."
        return ("The screen changed: the person acted. Look at the new screenshot. If this step "
                "is done, or they already moved ahead, give the next step from where they are now. "
                "Repeat the step only if it is clearly still needed.")

    async def watch(self) -> str:
        """GUIDE mode: return as soon as the person changes the screen (then it settles),
        clicks, or presses Next. Cheap pixel diffs, no model calls."""
        self.next_step.clear()
        await asyncio.sleep(0.6)  # let the pink cursor finish moving
        base = await asyncio.to_thread(screen.thumb)
        while not self.stopped:
            if self.next_step.is_set():
                return "next"
            clicked = screen.mouse_down()
            cur = await asyncio.to_thread(screen.thumb)
            if clicked or screen.changed(base, cur):
                prev, quiet_since = cur, time.time()
                while not self.stopped and time.time() - quiet_since < 0.8:
                    await asyncio.sleep(0.25)
                    nxt = await asyncio.to_thread(screen.thumb)
                    if screen.changed(prev, nxt):
                        quiet_since = time.time()
                    prev = nxt
                if clicked or screen.changed(base, prev):
                    return "changed"
            await asyncio.sleep(0.3)
        return "stopped"

    async def blocked(self, app: str) -> str:
        """A system/permission dialog is in the way: never act on it, hand control back."""
        text = f"A system dialog from {app} needs you. Handle it yourself, then press Next."
        await self.log(f"⚠ {text}")
        await self.panel(text, "waiting")
        self.speak("A system dialog needs you. Please handle it yourself.")
        await self.wait_next()
        return "The person handled the system dialog. Do not interact with system dialogs."

    async def wait_next(self) -> None:
        self.next_step.clear()
        while not self.next_step.is_set() and not self.stopped:
            await asyncio.sleep(0.1)

    def start(self, task: str, mode: str, countdown: bool = True) -> None:
        self.stop()
        self.task = asyncio.create_task(self.run(task, mode, countdown))

    async def on_hotkey(self) -> None:
        """⌃⌥Space: stop if busy, otherwise listen once and start in the current app."""
        if self.listening:
            return
        busy = bool(self.task and not self.task.done())
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
        if busy:
            await self.chat("you", text)
            if is_stop(text):
                self.stop()
                await self.to_overlay({"type": "clear"})
                await self.log("■ Stopped")
                self.speak("Stopped.")
                return
            self.mode = mode_from(text, self.mode)
            self.said.append(text)
            self.next_step.set()  # re-plan right away with what they said
            self.speak("Got it.")
            return
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


STOP_PHRASES = {"stop", "stop it", "stop shadow", "arrête", "arrete", "arrête-toi", "cancel",
                "annule", "c'est bon stop"}


def is_stop(text: str) -> bool:
    """Only a bare 'stop' stops: 'stop the video at 2:00' is a task, not a command."""
    return text.lower().strip(" .!?,") in STOP_PHRASES


def roadmap_from(hint: str) -> list[str]:
    """Numbered steps from the Linkup notes, without markdown."""
    steps = []
    for line in hint.splitlines():
        m = re.match(r"\s*\d+[.)]\s+(.*)", line)
        if m:
            steps.append(m.group(1).replace("**", "").strip())
    return steps[:8]


def label_of(name: str, args: dict) -> str:
    if name == "click":
        return f"Click {args.get('element', '')}".strip()
    if name == "type":
        return f'Type "{args.get("text", "")}"'
    if name == "press":
        return f"Press {args.get('keys', '')}"
    if name == "scroll":
        return f"Scroll {args.get('direction', 'down')}"
    return name


def short(label: str, n: int = 42) -> str:
    """Bubble text next to the pink cursor: first clause, trimmed."""
    first = label.split(" - ")[0].split(", ")[0]
    return first if len(first) <= n else first[: n - 1] + "…"


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
        elif kind in ("hotkey", "mic"):
            asyncio.create_task(brain.on_hotkey())
        elif kind == "next":
            brain.next_step.set()
        elif kind == "mode":
            brain.mode = brain.default_mode = json.loads(msg.data).get("mode", "guide")
            brain.next_step.set()  # re-plan now in the new mode
        elif kind == "stop":
            brain.stop()
            await brain.to_overlay({"type": "clear"})
            await brain.log("■ Stopped")
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
            brain.mode = brain.default_mode = data.get("mode", "guide")
    brain.uis.discard(ws)
    return ws


def main() -> None:
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws/overlay", overlay_ws), web.get("/ws/ui", ui_ws)])
    web.run_app(app, host="127.0.0.1", port=8765, print=lambda *_: print("Shadow Cursor → http://127.0.0.1:8765"))


if __name__ == "__main__":
    main()
