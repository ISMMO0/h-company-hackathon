"""The Shadow Cursor agent: one task at a time, driven by what happens on screen and what the
person says.

States: idle → listening → thinking → waiting (GUIDE: the person's turn) / acting (DO)
        → paused (model chose 'wait') → done.

Speed rules:
- Holo answers computed on a screen the person has since changed (click, key, window switch,
  or something they said) are dropped and re-planned from the new screen.
- While waiting for the person, no model calls: cheap input timers + pixel diffs.
"""

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import time
from pathlib import Path

from PIL import ImageDraw

from brain import linkup, planner, screen, voice

try:
    from brain.memory import Memory
except ImportError:  # memory.py lands with Devin's PR; keep the agent usable without it
    class Memory:  # type: ignore[no-redef]
        def __init__(self, *_a, **_k): pass
        def start_task(self, *_a): pass
        def add(self, *_a): pass
        def add_step(self, *_a): pass
        def finish_task(self, *_a): pass
        def context(self, *_a, **_k): return ""

MAX_STEPS = 30
SAVE_FIXTURES = os.environ.get("SHADOW_SAVE_FIXTURES") == "1"
FIXTURES = Path("data/fixtures")


class Agent:
    def __init__(self, to_overlay, to_ui) -> None:
        self.to_overlay = to_overlay  # async (dict) -> None
        self.to_ui = to_ui            # async (dict) -> None
        self.overlay_connected = lambda: False
        self.hidden = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.stopped = False
        self.mode = "guide"
        self.default_mode = "guide"
        self.events: list[tuple[str, str]] = []  # ("said" | "next" | "mode", text) for the running task
        self.poke = asyncio.Event()
        self.listener: voice.Listener | None = None
        self.say_proc: subprocess.Popen | None = None
        self.memory = Memory()
        self.full = None

    # --- small outputs --------------------------------------------------------------------
    async def log(self, text: str) -> None:
        print(text, flush=True)
        await self.to_ui({"type": "log", "text": text})

    async def panel(self, text: str, state: str) -> None:
        await self.to_overlay({"type": "step", "text": text, "mode": self.mode, "state": state})
        await self.to_ui({"type": "status", "text": f"{state}: {text}" if text else state})

    async def chat(self, who: str, text: str) -> None:
        self.memory.add(who, text)
        await self.to_overlay({"type": "chat", "who": who, "text": text})

    def speak(self, text: str) -> None:
        self.hush()
        first = text.split(". ")[0].strip()  # long replies get picked up by the mic
        self.say_proc = subprocess.Popen(["say", "-r", "190", first[:160]])

    def hush(self) -> None:
        if self.say_proc and self.say_proc.poll() is None:
            self.say_proc.terminate()

    async def snapshot(self):
        """Native-resolution screenshot without the pink cursor or panel in it."""
        if self.overlay_connected():
            self.hidden.clear()
            await self.to_overlay({"type": "hide"})
            try:
                await asyncio.wait_for(self.hidden.wait(), 0.5)
            except TimeoutError:
                pass
        self.full = await asyncio.to_thread(screen.capture_full)
        await self.to_overlay({"type": "show"})
        return self.full

    async def preview(self, img, point=None, label="") -> None:
        im = img.copy()
        if point:
            d = ImageDraw.Draw(im)
            x, y = point
            d.ellipse((x - 14, y - 14, x + 14, y + 14), outline="#ff3ea5", width=5)
        im.thumbnail((900, 900))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=70)
        await self.to_ui({"type": "preview", "label": label,
                          "image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()})

    async def send_plan(self, pl: planner.Planner, roadmap: list[str]) -> None:
        steps = pl.plan or roadmap
        cur = max(pl.step, 1)
        await self.to_overlay({"type": "plan", "steps": [
            {"text": s, "status": "done" if i + 1 < cur else "current" if i + 1 == cur else "todo"}
            for i, s in enumerate(steps)]})

    # --- voice ----------------------------------------------------------------------------
    async def on_hotkey(self) -> None:
        """⌃⌥Space: start listening, or send what was said."""
        if self.listener:
            lis, self.listener = self.listener, None
            text = await lis.finish()
            await self.to_overlay({"type": "listening", "on": False})
            if text:
                await self.heard(text)
            else:
                await self.to_ui({"type": "status", "text": "Didn't catch that"})
            return
        self.hush()  # never transcribe our own voice
        lis = voice.Listener(
            on_text=lambda t: asyncio.create_task(self._live(t)),
            on_auto_send=lambda: asyncio.create_task(self.on_hotkey()))
        self.listener = lis
        await self.to_overlay({"type": "listening", "on": True})
        await self.to_ui({"type": "status", "text": "Listening…"})
        try:
            await lis.start()
        except Exception as e:  # noqa: BLE001 - mic or network
            self.listener = None
            await self.to_overlay({"type": "listening", "on": False})
            await self.log(f"Voice error: {type(e).__name__}: {e}")

    async def _live(self, text: str) -> None:
        await self.to_overlay({"type": "transcript", "text": text})
        await self.to_ui({"type": "status", "text": f"… {text}"})

    async def on_stop(self) -> None:
        """⌃⌥X / × / menu Stop: cancel listening if listening, else stop the task."""
        if self.listener:
            lis, self.listener = self.listener, None
            await lis.cancel()
            await self.to_overlay({"type": "listening", "on": False})
            await self.log("✕ Cancelled")
            return
        if self.busy():
            self.stop()
            await self.to_overlay({"type": "clear"})
            await self.log("■ Stopped")
            self.speak("Stopped.")

    async def heard(self, text: str) -> None:
        await self.log(f'🎙 "{text}"')
        await self.to_ui({"type": "heard", "text": text})
        if not self.busy():
            self.start(text, mode_from(text, self.default_mode), countdown=False)
            return
        await self.chat("you", text)
        if is_stop(text):
            await self.on_stop()
            return
        new_mode = mode_from(text, self.mode)
        if new_mode != self.mode:
            self.set_mode(new_mode)
        self.push("said", text)

    # --- task control ---------------------------------------------------------------------
    def busy(self) -> bool:
        return bool(self.task and not self.task.done())

    def start(self, task: str, mode: str, countdown: bool = True) -> None:
        self.stop()
        self.stopped = False
        self.events.clear()
        self.task = asyncio.create_task(self.run(task, mode, countdown))

    def stop(self) -> None:
        self.stopped = True
        self.poke.set()
        if self.task and not self.task.done():
            self.task.cancel()

    def set_mode(self, mode: str) -> None:
        self.default_mode = mode
        if self.busy() and mode != self.mode:
            self.mode = mode
            self.push("mode", mode)

    def push(self, kind: str, text: str = "") -> None:
        self.events.append((kind, text))
        self.poke.set()

    def _drain(self, pl: planner.Planner) -> None:
        for kind, text in self.events:
            if kind == "said":
                pl.note(f'The person says: "{text}"')
            elif kind == "mode":
                pl.note(f"Mode is now {text.upper()}.")
        self.events.clear()

    # --- the loop -------------------------------------------------------------------------
    async def run(self, task: str, mode: str, countdown: bool) -> None:
        self.mode = mode
        try:
            for n in (3, 2, 1) if countdown else ():
                await self.to_ui({"type": "status", "text": f"Switch to your app… {n}"})
                await asyncio.sleep(1)
            app, _ = screen.front_window()
            await self.log(f"▶ {mode.upper()} in {app}: {task}")
            self.memory.start_task(task, mode)
            await self.chat("you", task)
            await self.panel(task, "thinking")
            self.speak("On it.")
            await self._loop(task, mode, app)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - surface any failure
            await self.log(f"Error: {type(e).__name__}: {e}")
        finally:
            await self.to_overlay({"type": "clear"})
            await self.to_ui({"type": "status", "text": "Idle"})

    async def _loop(self, task: str, mode: str, app: str) -> None:
        pl = planner.Planner(task, mode, self.memory.context())
        hint_job = asyncio.create_task(asyncio.to_thread(linkup.how_to, task, app))
        roadmap: list[str] = []
        w, h = screen.screen_size()
        last_key, repeats, pixels_ok = None, 0, True
        last_step = 0

        for i in range(MAX_STEPS):
            if self.stopped:
                return
            if hint_job and hint_job.done():
                hint = hint_job.result()
                hint_job = None
                if hint:
                    roadmap = roadmap_from(hint)
                    pl.note(f"How-to notes found on the web (may be approximate):\n{hint}")
                    await self.log(f"Linkup notes:\n{hint}")
                    await self.send_plan(pl, roadmap)
            self._drain(pl)

            t0 = time.perf_counter()
            full = await self.snapshot()
            small = full.resize((w, h))
            t_cap = time.perf_counter() - t0
            if SAVE_FIXTURES:
                save_fixture(full, task, app)
            mark = input_mark()
            job = asyncio.create_task(asyncio.to_thread(pl.next, small))
            stale = None
            while not job.done():
                await asyncio.sleep(0.12)
                stale = self.events and "spoke" or changed_since(mark)
                if stale or self.stopped:
                    break
            if self.stopped:
                return
            if stale:
                await self.log(f"↻ re-planning ({stale})")
                continue
            action = job.result()
            pl.accept(action)
            name, args = action["name"], action["args"]
            t_plan = action["timings"]["plan"]
            if not name:
                pl.result(action, "")
                continue

            if pl.step and pl.step != last_step:
                for s in (pl.plan or roadmap)[max(last_step - 1, 0):pl.step - 1]:
                    self.memory.add_step(s, "done")
                last_step = pl.step
            await self.send_plan(pl, roadmap)

            if name == "answer":
                text = args.get("content", "Done.")
                await self.log(f"✓ {text}")
                await self.panel(text, "done")
                await self.chat("shadow", text)
                self.memory.finish_task(text)
                self.speak(text)
                await asyncio.sleep(6)
                return

            key = (name, json.dumps({k: v for k, v in args.items() if k not in ("plan", "step", "x", "y")},
                                    sort_keys=True))
            repeat = key == last_key
            repeats = repeats + 1 if repeat else 0
            last_key = key
            if not repeat:
                pixels_ok = True

            t1 = time.perf_counter()
            if repeats >= 2 and name not in ("wait",):
                result = await self.stuck(pl, args)
                repeats = 0
            else:
                result, why = await self.act(pl, name, args, full, w, h, repeat, pixels_ok)
                if why == "pixels" and repeat:
                    pixels_ok = False  # something animates on screen: only react to real input
            t_point = getattr(self, "_t_point", 0.0)
            await self.log(f"Step {i + 1}: {name} {short_args(args)}  "
                           f"[capture {t_cap:.1f}s · plan {t_plan:.1f}s · point {t_point:.1f}s"
                           f" · then {time.perf_counter() - t1:.1f}s on the person]")
            pl.result(action, result)

        await self.log("Step budget reached.")

    async def act(self, pl, name, args, full, w, h, repeat, pixels_ok) -> tuple[str, str]:
        """Show the step, then do it (DO) or watch the person (GUIDE). Returns (tool result, why)."""
        self._t_point = 0.0
        if self.mode == "do" and screen.frontmost_app() in screen.SYSTEM_APPS:
            return await self.blocked(screen.frontmost_app()), "next"

        if name == "say":
            text = args.get("text", "")
            await self.panel(text, "waiting")
            await self.chat("shadow", text)
            self.speak(text)
            why = await self.watch(pixels_ok)
            return f"Said it. {result_text(why)}", why

        if name == "wait":
            reason = args.get("reason", "Waiting")
            await self.panel(f"Paused: {reason}. I'll pick up when you're back.", "paused")
            why = await self.watch(True)
            return f"Waited. {result_text(why)}", why

        label = label_of(name, args)
        point = None
        if name == "click":
            t = time.perf_counter()
            nx, ny = await asyncio.to_thread(planner.point, full, args.get("element", ""),
                                             (args.get("x", 500), args.get("y", 500)))
            self._t_point = time.perf_counter() - t
            point = (nx / 1000 * w, ny / 1000 * h)
            if self.mode == "do" and screen.window_owner_at(*point) in screen.SYSTEM_APPS:
                return await self.blocked(screen.window_owner_at(*point)), "next"
            await self.to_overlay({"type": "cursor", "x": point[0], "y": point[1], "label": short(label)})
        await self.preview(full.resize((w, h)), point, label)
        if not repeat:
            await self.chat("shadow", label)
            self.speak(label)

        if self.mode == "do":
            await self.panel(label, "acting")
            await asyncio.sleep(0.7 if point else 0.3)
            if name == "click":
                await asyncio.to_thread(screen.click, *point)
            elif name == "type":
                await asyncio.to_thread(screen.type_text, args.get("text", ""))
            elif name == "press":
                await asyncio.to_thread(screen.press, args.get("keys", ""))
            elif name == "scroll":
                await asyncio.to_thread(screen.scroll, args.get("direction", "down"))
            await asyncio.sleep(0.6)  # let the app react
            return "Done.", "did"

        await self.panel(label, "waiting")
        why = await self.watch(pixels_ok)
        return result_text(why), why

    async def stuck(self, pl, args) -> str:
        text = "I keep suggesting the same step. Can you tell me where you are, or do it your way?"
        await self.panel(text, "paused")
        await self.chat("shadow", text)
        self.speak(text)
        why = await self.watch(False)
        return f"You proposed the same action 3 times. {result_text(why)} Try a different approach."

    async def watch(self, pixels_ok: bool) -> str:
        """Wait for the person: returns 'next' | 'spoke' | 'mode' | 'click' | 'key' | 'window'
        | 'pixels' | 'stopped'. No model calls here."""
        self.poke.clear()
        await asyncio.sleep(0.5)  # let the pink cursor finish moving
        start = time.time()
        base = await asyncio.to_thread(screen.thumb)
        win0 = screen.front_window()
        while not self.stopped:
            if self.events:
                kind = self.events[0][0]
                if kind == "next":
                    self.events.pop(0)
                return {"said": "spoke"}.get(kind, kind)
            click_ago, key_ago = screen.seconds_since_input()
            now = time.time()
            if now - click_ago > start:
                await self.settle(base, quiet_keys=0.4)
                return "click"
            if now - key_ago > start:
                await self.settle(base, quiet_keys=0.9)
                return "key"
            if screen.front_window() != win0:
                await asyncio.sleep(0.5)
                return "window"
            if pixels_ok:
                cur = await asyncio.to_thread(screen.thumb)
                if screen.changed(base, cur):
                    await self.settle(cur)
                    return "pixels"
            try:
                await asyncio.wait_for(self.poke.wait(), 0.25)
            except TimeoutError:
                pass
            self.poke.clear()
        return "stopped"

    async def settle(self, base, quiet_keys: float = 0.0, cap: float = 2.5) -> None:
        """Wait until typing pauses and the screen stops changing (max `cap` seconds)."""
        end = time.time() + cap
        prev = base
        quiet_since = time.time()
        while time.time() < end and not self.stopped:
            await asyncio.sleep(0.2)
            _, key_ago = screen.seconds_since_input()
            cur = await asyncio.to_thread(screen.thumb)
            if screen.changed(prev, cur, 0.003) or key_ago < quiet_keys:
                quiet_since = time.time()
            prev = cur
            if time.time() - quiet_since > 0.5:
                return

    async def blocked(self, app: str) -> str:
        text = f"A system dialog from {app} needs you. Handle it yourself, then press Next."
        await self.log(f"⚠ {text}")
        await self.panel(text, "paused")
        self.speak("A system dialog needs you. Please handle it yourself.")
        while not self.stopped and not any(k == "next" for k, _ in self.events):
            await asyncio.sleep(0.2)
        self.events = [e for e in self.events if e[0] != "next"]
        return "The person handled the system dialog. Do not interact with system dialogs."


# --- helpers ---------------------------------------------------------------------------------

def input_mark() -> tuple[float, tuple[str, str]]:
    return time.time(), screen.front_window()


def changed_since(mark) -> str | None:
    """Did the person do something since `mark`? (click, key, or window switch)."""
    t, win = mark
    click_ago, key_ago = screen.seconds_since_input()
    now = time.time()
    if now - click_ago > t:
        return "click"
    if now - key_ago > t:
        return "key"
    if screen.front_window() != win:
        return "window"
    return None


def result_text(why: str) -> str:
    return {
        "next": "The person pressed Next: they say they did it or want to skip.",
        "spoke": "The person spoke instead; see their message. The step may not be done.",
        "mode": "The mode changed; see the message.",
        "stopped": "Stopped.",
    }.get(why, f"The person acted ({why}). Judge progress from the new screenshot and continue "
               "from where they are now; skip steps that are already done.")


DO_WORDS = ("do it", "do this", "for me", "fais-le", "fais le", "à ma place", "fais-moi", "fais moi")
STOP_PHRASES = {"stop", "stop it", "stop shadow", "arrête", "arrete", "arrête-toi", "cancel",
                "annule", "c'est bon stop"}


def mode_from(text: str, default: str) -> str:
    t = text.lower()
    if any(w in t for w in DO_WORDS):
        return "do"
    if "show me" in t or "montre" in t or "guide" in t:
        return "guide"
    return default


def is_stop(text: str) -> bool:
    """Only a bare 'stop' stops: 'stop the video at 2:00' is a task, not a command."""
    return text.lower().strip(" .!?,") in STOP_PHRASES


def roadmap_from(hint: str) -> list[str]:
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
    first = label.split(" - ")[0].split(", ")[0]
    return first if len(first) <= n else first[: n - 1] + "…"


def short_args(args: dict) -> str:
    return json.dumps({k: v for k, v in args.items() if k != "plan"}, ensure_ascii=False)[:160]


def save_fixture(full, task: str, app: str) -> None:
    d = FIXTURES / time.strftime("%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    full.save(d / "screen.png")
    (d / "meta.json").write_text(json.dumps({"task": task, "app": app}, ensure_ascii=False))
