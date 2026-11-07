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

from brain import billing, knowledge, linkup, planner, router, screen, voice

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

MAX_ACTIONS = 30  # real actions shown/done; re-plans don't count
MAX_TURNS = 200   # hard safety stop
SAVE_FIXTURES = os.environ.get("SHADOW_SAVE_FIXTURES") == "1"
FIXTURES = Path("data/fixtures")


class Agent:
    def __init__(self, to_overlay, to_ui) -> None:
        self._send_overlay = to_overlay  # async (dict) -> None
        self.cursor_at: tuple[float, float] | None = None  # where the pink cursor (and its bubble) is
        self.prev_action = ""  # last executed Do it action, e.g. "double_click"
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
        self.current_task = ""
        self.current_app = ""
        self.shown: dict[str, int] = {}  # Do it: rows/formulas already typed step by step this task
        self.partial = False
        self.task_apps: set[str] = set()  # apps this task happens in; input elsewhere is ignored
        self.brief = ""  # short session summary, rewritten by GPT in the background
        self.open_mic: voice.Listener | None = None  # open mic for the running task
        self._tts_seen = 0.0  # last time our own voice was playing (echo filter)
        self._guess = {"busy": False, "words": 0, "shot": None}  # fast path on partial words
        self.offer: str = ""  # task offered after an answer ("show it on screen")

    # --- small outputs --------------------------------------------------------------------
    async def log(self, text: str) -> None:
        print(text, flush=True)
        await self.to_ui({"type": "log", "text": text})

    async def panel(self, text: str, state: str, why: str = "") -> None:
        msg = {"type": "step", "text": text, "mode": self.mode, "state": state}
        if why:
            msg["why"] = why
        await self.to_overlay(msg)
        await self.to_ui({"type": "status", "text": f"{state}: {text}" if text else state})

    async def chat(self, who: str, text: str) -> None:
        self.memory.add(who, text)
        await self.to_overlay({"type": "chat", "who": who, "text": text})

    def speak(self, text: str, whole: bool = False) -> None:
        self.hush()
        # Long replies get picked up by the mic: first sentence only unless it's a short narration.
        said = text if whole else text.split(". ")[0]
        self.say_proc = subprocess.Popen(["say", "-r", "190", said.strip()[:200]])

    async def finish_speaking(self, cap: float = 8.0) -> None:
        """Do it mode: let the current sentence end before the next one (it used to be cut off)."""
        end = time.time() + cap
        while self.say_proc and self.say_proc.poll() is None and time.time() < end and not self.stopped:
            await asyncio.sleep(0.08)

    def hush(self) -> None:
        if self.say_proc and self.say_proc.poll() is None:
            self.say_proc.terminate()

    def speaking(self) -> bool:
        """True while our own voice plays, and 0.4 s after: what the mic hears then is us."""
        if self.say_proc and self.say_proc.poll() is None:
            self._tts_seen = time.time()
            return True
        return time.time() - self._tts_seen < 0.4

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
        """⌃⌥Space: idle → push-to-talk (again = send). During a task → open mic on/off."""
        if self.busy() and not self.listener:
            if self.open_mic:
                await self.close_open_mic()
            else:
                await self.start_open_mic()
            return
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
            on_auto_send=lambda: asyncio.create_task(self._auto_send(lis)),
            on_speech=lambda: asyncio.create_task(self.to_overlay({"type": "pulse"})))
        self.listener = lis
        self._guess = {"busy": False, "words": 0, "shot": None}
        asyncio.create_task(self._grab_guess_shot())
        await self.to_overlay({"type": "listening", "on": True})
        await self.to_ui({"type": "status", "text": "Listening…"})
        try:
            await lis.start()
        except Exception as e:  # noqa: BLE001 - mic or network
            self.listener = None
            await self.to_overlay({"type": "listening", "on": False})
            await self.log(f"Voice error: {type(e).__name__}: {e}")

    async def _auto_send(self, lis: voice.Listener) -> None:
        """Silence-triggered send: only if this push-to-talk is still the active one (a manual
        send may already have happened; toggling the task mic here closed it by mistake)."""
        if self.listener is lis:
            await self.on_hotkey()

    async def _live(self, text: str) -> None:
        await self.to_overlay({"type": "transcript", "text": text})
        await self.to_ui({"type": "status", "text": f"… {text}"})
        await self._maybe_guess(text)

    # --- fast path: move the cursor while the person is still talking -----------------------
    async def _grab_guess_shot(self) -> None:
        """One screenshot when push-to-talk opens: the screen doesn't change while they talk."""
        self._guess["shot"] = await asyncio.to_thread(screen.capture_full)

    async def _maybe_guess(self, text: str) -> None:
        g = self._guess
        words = len(text.split())
        if g["busy"] or g["shot"] is None or words < 3 or words - g["words"] < 2:
            return
        if not UI_REQUEST.search(text) or self.busy():
            return
        g["busy"], g["words"] = True, words
        try:
            target = f"the on-screen UI element the person needs for this request: {text}"
            p = await asyncio.to_thread(planner._localize, planner.shrink(g["shot"], 1920), target)
            if p and self.listener and not self.busy():  # still talking, no real step yet: show only
                w, h = screen.screen_size()
                await self.to_overlay({"type": "cursor", "x": p[0] / 1000 * w, "y": p[1] / 1000 * h,
                                       "label": "Looking…", "tentative": True})
        finally:
            g["busy"] = False

    # --- open mic during a task ------------------------------------------------------------
    async def start_open_mic(self) -> None:
        if self.open_mic:
            return
        lis = voice.Listener(
            continuous=True, muted=self.speaking,
            on_final=lambda t: asyncio.create_task(self.heard(t)),
            on_text=lambda t: asyncio.create_task(
                self.to_overlay({"type": "mic", "on": True, "heard": t})) if t else None,
            on_speech=lambda: asyncio.create_task(self.to_overlay({"type": "pulse"})))
        self.open_mic = lis
        try:
            await lis.start()
            await self.to_overlay({"type": "mic", "on": True})
            await self.log("🎙 Mic open (⌃⌥Space to mute)")
        except Exception as e:  # noqa: BLE001
            self.open_mic = None
            await self.log(f"Voice error: {type(e).__name__}: {e}")

    async def close_open_mic(self) -> None:
        lis, self.open_mic = self.open_mic, None
        if lis:
            await lis.cancel()
            await self.to_overlay({"type": "mic", "on": False})
            await self.log("🎙 Mic off")

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
        busy = self.busy()
        if busy and is_stop(text):  # no round trip for the obvious one
            await self.on_stop()
            return
        if busy and is_noise(text):  # "I", "Thank you." from the TV: never re-plan on it
            await self.log("→ ignore (too short)")
            return
        app = self.current_app if busy else screen.front_window()[0]
        unfinished, unfinished_mode = self.last_unfinished()
        if not busy:
            quick = router.route_keywords(text, False, unfinished)
            low = text.lower()
            has_guide = any(w in low for w in router.GUIDE_WORDS)
            has_do = any(w in low for w in router.DO_WORDS)
            # Fast start only when the intent is clear and the request short; long or mixed requests
            # wait ~1 s for GPT to turn them into a clean task (names fixed, goals kept).
            confident = (has_guide != has_do) and len(text.split()) <= 25
            if quick["intent"] in ("guide", "do") and confident:
                # Start now on keywords; GPT confirms in the background and corrects if needed.
                await self.log(f"→ {quick['intent']} (fast): {text}")
                self.start(text, quick["intent"], countdown=False)
                asyncio.create_task(self._confirm_route(text, quick["intent"], app, unfinished))
                return
        r = await asyncio.to_thread(router.route, text, busy, self.current_task, app,
                                    self.brief or self.memory.context(), unfinished)
        intent, task = r["intent"], r["task"]
        await self.log(f"→ {intent}: {task}")
        if busy:
            await self.to_overlay({"type": "mic", "on": bool(self.open_mic), "heard": text})
        if busy and intent == "ignore":
            return
        if not busy:
            if intent == "answer":
                await self.answer(task)
            elif intent == "unclear" or (intent == "resume" and not unfinished):
                self.speak(r.get("reply") or "What should we do?")
                await self.panel(r.get("reply") or "What should we do?", "done")
            elif intent == "resume" and unfinished:
                self.speak(r.get("reply") or "Let's pick up where we left off.")
                self.start(unfinished, unfinished_mode or self.default_mode, countdown=False)
            else:
                self.start(task, "do" if intent == "do" else "guide", countdown=False)
            return
        await self.chat("you", text)
        if r.get("reply"):
            self.speak(r["reply"])
        if intent == "stop":
            await self.on_stop()
        elif intent == "new_task":
            self.start(task, self.mode, countdown=False)
        elif intent in ("guide", "do"):
            self.set_mode(intent)
            self.push("said", text)
        elif intent == "ahead":
            self.push("said", f"{text} (they say they are ahead: re-check the screen and skip what is done)")
        elif intent == "wait":
            self.push("said", f"{text} (they ask you to wait: use 'wait')")
        elif intent == "question":
            self.push("said", f"{text} (a question: answer it with 'say', then continue)")
            asyncio.create_task(self._lookup_for(task, app))
        else:  # update
            self.current_task = task
            self.push("said", f"{text} (the task is now: {task})")

    async def _confirm_route(self, text: str, fast_intent: str, app: str, unfinished: str) -> None:
        """GPT's reading of what was said, after the task already started on keywords."""
        r = await asyncio.to_thread(router.route, text, False, "", app,
                                    self.brief or self.memory.context(), unfinished)
        if not router.enabled() or not self.busy():
            return
        intent, task = r["intent"], r["task"]
        if intent == "answer":
            await self.log(f"→ GPT: actually a question, answering: {task}")
            self.stop()
            await self.to_overlay({"type": "clear"})
            await self.answer(task)
        elif intent == "resume" and unfinished:
            await self.log(f"→ GPT: resume '{unfinished}'")
            self.start(unfinished, fast_intent, countdown=False)
        elif intent in ("guide", "do") and task and task != text:
            self.current_task = task
            self.push("said", f"(clarified task: {task})")
            if intent != fast_intent:
                self.set_mode(intent)

    async def paywall(self, hint: str) -> None:
        """Free quota used: offer Shadow Pro through Stripe Checkout (test mode)."""
        await self.log(f"💳 {hint}")
        self.speak("You've used your free tasks for today. Upgrade to Shadow Pro to keep going.", whole=True)
        try:
            url = await asyncio.to_thread(billing.create_checkout)
            sources = [{"title": "Upgrade to Shadow Pro (9 €/month)", "url": url}]
        except billing.ERRORS as e:
            await self.log(f"Stripe not ready ({e}); upgrade from http://127.0.0.1:8765")
            sources = [{"title": "Open Shadow Cursor to upgrade", "url": "http://127.0.0.1:8765"}]
        await self.to_overlay({"type": "answer", "text": "You've used today's free tasks. Shadow Pro "
                               "gives you unlimited guidance.", "sources": sources})

    def last_unfinished(self) -> tuple[str, str]:
        """(request, mode) of the task that was stopped before finishing, if any."""
        cur = getattr(self.memory, "current", None)
        if isinstance(cur, dict) and cur.get("request") and cur.get("mode") != "answer":
            return cur["request"], cur.get("mode", "")
        for t in reversed(getattr(self.memory, "tasks", []) or []):
            if t.get("result") == "(not finished)" and t.get("mode") != "answer":
                return t.get("request", ""), t.get("mode", "")
            break
        return "", ""

    def refresh_brief(self) -> None:
        """Rewrite the session brief with GPT in the background (never blocks a task)."""
        log = self.memory.context(max_tasks=8, max_chat=12)
        async def job() -> None:
            brief = await asyncio.to_thread(router.session_brief, log)
            if brief:
                self.brief = brief
                await self.log(f"🧠 Session brief updated:\n{brief}")
        asyncio.create_task(job())

    async def _lookup_for(self, question: str, app: str) -> None:
        """Web notes for a mid-task question, added when ready (never blocks the answer)."""
        info = await asyncio.to_thread(linkup.lookup, self.current_task, app, question, question)
        if info and self.busy():
            self.push("said", f"(web notes for their question '{question}': {info})")

    async def answer(self, question: str) -> None:
        """Pure information: answer it, with sources, and offer to show it on screen."""
        await self.panel(question, "thinking", why="Searching the web")
        a = await asyncio.to_thread(linkup.answer, question)
        if not a.get("text"):
            await self.panel("I couldn't find a good answer. Want me to search on screen?", "done")
            self.offer = question
            return
        self.offer = f"Show me on screen: {question}"
        await self.to_overlay({"type": "clear"})
        await self.to_overlay({"type": "answer", "text": a["text"], "sources": a["sources"],
                               "offer": "Want me to show it on screen?"})
        await self.chat("you", question)
        await self.chat("shadow", a["text"])
        await self.log(f"💬 {a['text']}")
        self.memory.start_task(question, "answer")
        self.memory.finish_task(a["text"][:120])
        self.speak(a["text"])

    async def followup(self, mode: str) -> None:
        """Answer card: Show me / Do it."""
        if self.offer:
            task, self.offer = self.offer, ""
            self.start(task, mode, countdown=False)

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
            allowed, hint = billing.allow_task()
            if not allowed:
                await self.paywall(hint)
                return
            app, title = screen.front_window()
            self.current_task, self.current_app = task, app
            self.shown, self.partial, self.prev_action = {}, False, ""
            self.task_apps = {app}
            self.current_title = title
            await self.log(f"▶ {mode.upper()} in {app}: {task}")
            self.memory.start_task(task, mode)
            await self.chat("you", task)
            await self.panel(task, "thinking", why="Looking at your screen…")
            self.speak("On it.")
            asyncio.create_task(self.start_open_mic())
            await self._loop(task, mode, app)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - surface any failure
            await self.log(f"Error: {type(e).__name__}: {e}")
        finally:
            await self.to_overlay({"type": "clear"})
            await self.to_ui({"type": "status", "text": "Idle"})
            await self.close_open_mic()
            self.refresh_brief()

    async def _loop(self, task: str, mode: str, app: str) -> None:
        pl = planner.Planner(task, mode, self.brief or self.memory.context())
        sheet = knowledge.cached(app)
        if sheet:
            pl.note(f"App cheat sheet for {app} (up to date; trust it over guesses):\n{sheet}")
            await self.log(f"📘 {app} cheat sheet loaded")
        else:
            asyncio.create_task(asyncio.to_thread(knowledge.build, app, getattr(self, "current_title", "")))
        roadmap: list[str] = []
        research = asyncio.create_task(self.research(pl, task, app))  # joins the plan when ready
        w, h = screen.screen_size()
        last_key, repeats, pixels_ok = None, 0, True
        last_step = 0
        actions = 0
        pixel_stales = 0  # at most one "screen still changing" re-plan per step (videos animate)
        same_step, last_scroll, prev_thumb = 0, "", None

        for _turn in range(MAX_TURNS):
            if self.stopped or actions >= MAX_ACTIONS:
                break
            if research and research.done():
                roadmap, research = research.result() or roadmap, None
            self._drain(pl)
            await self.quiet()

            t0 = time.perf_counter()
            full = await self.snapshot()
            small = full.resize((w, h))
            t_cap = time.perf_counter() - t0
            if SAVE_FIXTURES:
                save_fixture(full, task, app)
            app_now, title_now = screen.front_window()
            mark = input_mark()
            job = asyncio.create_task(asyncio.to_thread(pl.next, small, f"{app_now}: {title_now}"))
            job.add_done_callback(lambda t: t.cancelled() or t.exception())  # dropped stale plans: no log noise
            base_thumb = await asyncio.to_thread(screen.thumb) if pixel_stales < 1 else None
            stale = None
            waited, told = time.perf_counter(), False
            while not job.done():
                await asyncio.sleep(0.12)
                if not told and time.perf_counter() - waited > 3:
                    told = True  # never look frozen: say we're still on it
                    await self.panel("Still looking at your screen…", "thinking")
                stale = self.events and "spoke" or changed_since(mark, self.task_apps)
                moving = (not stale and base_thumb is not None and not job.done()
                          and screen.changed(base_thumb, await asyncio.to_thread(screen.thumb)))
                if moving:
                    stale, pixel_stales = "screen still changing", pixel_stales + 1
                if stale or self.stopped:
                    break
            if self.stopped:
                return
            if stale:
                await self.log(f"↻ re-planning ({stale})")
                continue
            try:
                action = job.result()
            except Exception as e:  # noqa: BLE001 - Holo timeout or API error: try again, say so
                await self.log(f"Holo error ({type(e).__name__}), retrying")
                await self.panel("H is slow right now, retrying…", "thinking")
                await asyncio.sleep(0.5)
                continue
            pl.accept(action)
            name, args = action["name"], action["args"]
            t_plan = action["timings"]["plan"]
            if not name:
                pl.result(action, "")
                continue

            moved = bool(pl.step and pl.step != last_step)
            if moved:
                for s in (pl.plan or roadmap)[max(last_step - 1, 0):pl.step - 1]:
                    self.memory.add_step(s, "done")
                last_step = pl.step
            await self.send_plan(pl, roadmap)

            if name == "answer":
                text = args.get("content", "Done.")
                await self.log(f"✓ {text}")
                if self.cursor_at:  # drop the last step's bubble ("Type 5 here")
                    await self.to_overlay({"type": "cursor", "x": self.cursor_at[0],
                                           "y": self.cursor_at[1], "label": ""})
                await self.panel(text, "done")
                await self.chat("shadow", text)
                self.memory.finish_task(text)
                await self.finish_speaking()
                self.speak(text)
                await asyncio.sleep(6)
                return

            key = (name, json.dumps({k: v for k, v in args.items() if k not in ("plan", "step", "x", "y", "why")},
                                    sort_keys=True))
            repeat = key == last_key
            repeats = repeats + 1 if repeat else 0
            last_key = key
            if not repeat:
                pixels_ok = True

            actions += 1
            pixel_stales = 0
            # No progress: 5 actions on the same plan step, or scrolling back and forth.
            thumb = full.convert("L").resize((240, 156))
            unchanged = prev_thumb is not None and not screen.changed(prev_thumb, thumb)
            prev_thumb = thumb
            same_step = same_step + 1 if unchanged and not moved and name not in ("say", "wait") else 0
            flip = name == "scroll" and last_scroll and args.get("direction") != last_scroll
            last_scroll = args.get("direction", "") if name == "scroll" else last_scroll
            t1 = time.perf_counter()
            if (repeats >= 2 or same_step >= 3 or flip) and name not in ("wait", "say"):
                same_step, last_scroll, prev_thumb = 0, "", None
                result = await self.stuck(pl, args)
                repeats = 0
            else:
                result, why = await self.act(pl, name, args, full, w, h, repeat, pixels_ok)
                if why == "pixels" and repeat:
                    pixels_ok = False  # something animates on screen: only react to real input
            t_point = getattr(self, "_t_point", 0.0)
            at = getattr(self, "_last_point", None)
            at_txt = f" @({at[0]:.0f},{at[1]:.0f})" if at else ""
            await self.log(f"Step {actions}: {name}{at_txt} {short_args(args)}  "
                           f"[capture {t_cap:.1f}s · plan {t_plan:.1f}s · point {t_point:.1f}s"
                           f" · then {time.perf_counter() - t1:.1f}s on the person]")
            pl.result(action, result)

        if not self.stopped:
            await self.log("Step budget reached.")

    async def to_overlay(self, msg: dict) -> None:
        if msg.get("type") == "cursor":
            self.cursor_at = (msg["x"], msg["y"])
        await self._send_overlay(msg)

    def teach_first(self, args: dict) -> None:
        """Do it is a lesson: the first time, type the header row, the first data row and the first
        formula one at a time (each one narrated), then let the rest go in one action."""
        text = args.get("text", "")
        if "\n" not in text.rstrip("\n") or FAST_WORDS.search(self.current_task or ""):
            return
        kind = "formula" if text.lstrip().startswith("=") else "row"
        if self.shown.get(kind, 0) >= (1 if kind == "formula" else 2):
            return
        self.shown[kind] = self.shown.get(kind, 0) + 1
        args["text"] = text.split("\n", 1)[0] + "\n"
        args["why"] = (args.get("why") or "") + (" Let's do the first one together." if kind == "formula"
                                                  else " One row at a time, so you can follow.")
        self.partial = True

    async def act(self, pl, name, args, full, w, h, repeat, pixels_ok) -> tuple[str, str]:
        """Show the step, then do it (DO) or watch the person (GUIDE). Returns (tool result, why)."""
        self._t_point = 0.0
        self._last_point = None
        if self.mode == "do" and screen.frontmost_app() in screen.SYSTEM_APPS:
            return await self.blocked(screen.frontmost_app()), "next"

        if name == "type" and self.mode == "do":
            self.teach_first(args)

        if name == "say":
            text = args.get("text", "")
            await self.panel(text, "waiting")
            await self.chat("shadow", text)
            if self.mode == "do":
                await self.finish_speaking()
            self.speak(text, whole=len(text) < 160)
            await asyncio.sleep(0.3)  # the voice plays on while we plan the next step
            return "Said it. Now continue guiding from the current screen.", "said"

        if name == "wait":
            reason = args.get("reason", "Waiting")
            await self.panel(f"Paused: {reason}. I'll pick up when you're back.", "paused")
            why = await self.watch(True)
            return f"Waited. {result_text(why)}", why

        label = label_of(name, args)
        why = str(args.get("why") or "")
        point = None
        if name == "type" and "x" in args and "y" in args:
            t = time.perf_counter()
            nx, ny = await asyncio.to_thread(planner.point, full, args.get("element") or "the text field",
                                             (args["x"], args["y"]))
            self._t_point = time.perf_counter() - t
            point = (nx / 1000 * w, ny / 1000 * h)
            self._last_point = point
            await self.to_overlay({"type": "cursor", "x": point[0], "y": point[1],
                                   "label": short(f'Type "{args.get("text", "")}" here')})
        if name == "scroll" and "x" in args and "y" in args:
            point = (args["x"] / 1000 * w, args["y"] / 1000 * h)
            self._last_point = point
            await self.to_overlay({"type": "cursor", "x": point[0], "y": point[1], "label": short(label)})
        drop = None
        if name == "drag":
            t = time.perf_counter()
            tx, ty = await asyncio.to_thread(planner.point, full, args.get("to_element", ""),
                                             (args.get("to_x", 500), args.get("to_y", 500)))
            drop = (tx / 1000 * w, ty / 1000 * h)
            self._t_point = time.perf_counter() - t
        if name in ("click", "right_click", "double_click", "drag"):
            t = time.perf_counter()
            nx, ny = await asyncio.to_thread(planner.point, full, args.get("element", ""),
                                             (args.get("x", 500), args.get("y", 500)))
            self._t_point = time.perf_counter() - t
            point = (nx / 1000 * w, ny / 1000 * h)
            self._last_point = point
            owner = screen.window_owner_at(*point)
            if self.mode == "do" and owner in screen.SYSTEM_APPS:
                return await self.blocked(owner), "next"
            if owner and owner not in screen.SYSTEM_APPS:
                self.task_apps.add(owner)  # the task continues in that app
            await self.to_overlay({"type": "cursor", "x": point[0], "y": point[1], "label": short(label)})
        await self.preview(full.resize((w, h)), point, label)
        if not repeat:
            await self.chat("shadow", f"{label} ({why})" if why else label)
            if self.mode == "do":
                await self.finish_speaking()
                self.speak(narrate(name, args, why), whole=True)
            else:
                self.speak(short(label, 70), whole=True)

        if self.mode == "do":
            await self.panel(label, "acting", why)
            await asyncio.sleep(0.45 if point else 0.15)
            if name == "click":
                await asyncio.to_thread(screen.click, *point)
            elif name == "double_click":
                await asyncio.to_thread(screen.click, *point, True)
            elif name == "right_click":
                await asyncio.to_thread(screen.right_click, *point)
            elif name == "drag" and drop:
                await asyncio.to_thread(screen.drag, *point, *drop)
            elif name == "type":
                if self.prev_action == "double_click":  # already editing: replace, don't insert at the caret
                    await asyncio.to_thread(screen.press, "cmd+a")
                elif point:  # focus the field first
                    await asyncio.to_thread(screen.click, *point)
                    await asyncio.sleep(0.2)
                await asyncio.to_thread(screen.type_text, args.get("text", ""))
            elif name == "press":
                await asyncio.to_thread(screen.press, args.get("keys", ""))
            elif name == "scroll":
                await asyncio.to_thread(screen.scroll, args.get("direction", "down"), 5, point)
            self.prev_action = name
            await asyncio.sleep(0.4)  # let the app react
            if self.partial:
                self.partial = False
                return ("Typed only the first line, so the person sees it step by step. "
                        "Type the remaining lines next (the cursor is on the next row)."), "did"
            return "Done.", "did"

        await self.panel(label, "waiting", why)
        at = f" @({point[0]:.0f},{point[1]:.0f})" if point else ""
        await self.log(f"show {name}{at} {short_args(args)}")
        reason = await self.watch(pixels_ok, timeout=6 if name == "scroll" else None)
        return result_text(reason), reason

    async def research(self, pl, task: str, app: str) -> list[str]:
        """Knowledge before the first click: Linkup playbook (≤5 s), cleaned by the router's
        LLM if available, seeded as Holo's plan. Falls back to Holo alone."""
        t = time.perf_counter()
        try:
            pb = await asyncio.wait_for(asyncio.to_thread(
                linkup.playbook, task, app, getattr(self, "current_title", "")), 6.0)
        except TimeoutError:
            pb = {}
        steps = pb.get("steps", [])
        if steps and router.enabled():
            try:
                steps = await asyncio.wait_for(
                    asyncio.to_thread(router.merge_playbook, task, app, steps, pb.get("note", "")), 3.0)
            except TimeoutError:
                pass
        if not steps:
            await self.log(f"(no playbook, Holo plans alone, {time.perf_counter() - t:.1f}s)")
            return []
        lines = [f"{i}. {s['action_hint']}: {s.get('target', '')} ({s.get('why', '')})"
                 for i, s in enumerate(steps, 1)]
        if pb.get("note"):
            lines.append(f"Tip: {pb['note']}")
        pl.note("Playbook from the web (the known path; follow it, adapt to the screen):\n" + "\n".join(lines))
        pl.plan = [s["action_hint"] for s in steps]
        await self.log(f"Playbook ({time.perf_counter() - t:.1f}s):\n" + "\n".join(lines))
        await self.send_plan(pl, pl.plan)
        return pl.plan

    async def stuck(self, pl, args) -> str:
        step = (pl.plan[pl.step - 1] if 0 < pl.step <= len(pl.plan) else "") or label_of("click", args)
        if getattr(self, "_looked_up", None) != step:
            self._looked_up = step
            await self.panel("Let me check how to do this step…", "thinking", why="Searching the web")
            info = await asyncio.to_thread(linkup.lookup, self.current_task, self.current_app, step)
            if info:
                await self.log(f"Linkup lookup for '{step}':\n{info}")
                return ("You proposed the same action 3 times. Web notes for this step: "
                        f"{info} Use them and try a different target.")
        text = "I keep suggesting the same step. Can you tell me where you are, or do it your way?"
        await self.panel(text, "paused")
        await self.chat("shadow", text)
        self.speak(text)
        why = await self.watch(False)
        return f"You proposed the same action 3 times. {result_text(why)} Try a different approach."

    async def watch(self, pixels_ok: bool, timeout: float | None = None) -> str:
        """Wait for the person: returns 'next' | 'spoke' | 'mode' | 'click' | 'key' | 'window'
        | 'pixels' | 'stopped'. No model calls here."""
        self.poke.clear()
        await asyncio.sleep(0.5)  # let the pink cursor finish moving
        start = time.time()
        base = await asyncio.to_thread(screen.thumb)
        win0 = screen.front_window()
        away_since = None
        while not self.stopped:
            if timeout and time.time() - start > timeout:
                return "timeout"  # e.g. a scroll that moved nothing: look again
            if self.events:
                kind = self.events[0][0]
                if kind == "next":
                    self.events.pop(0)
                return {"said": "spoke"}.get(kind, kind)
            front = screen.front_window()
            if front[0] not in self.task_apps:
                # Doing something else (another app): stay quiet. If they stay and keep working
                # there for a while, let the model decide whether the task moved to that app.
                away_since = away_since or time.time()
                if time.time() - away_since > 6:
                    self.task_apps.add(front[0])
                    return "window"
                await asyncio.sleep(0.3)
                continue
            away_since = None
            click_ago, key_ago = screen.seconds_since_input()
            now = time.time()
            if now - click_ago > start:
                await self.settle(base, quiet_keys=0.4, cap=0.8)  # plan early; stale check catches the rest
                return "click"
            if now - key_ago > start:
                await self.settle(base, quiet_keys=1.0)  # typing is progress: wait for the pause
                return "key"
            if front != win0:
                await asyncio.sleep(0.5)
                return "window"
            if pixels_ok:
                cur = await asyncio.to_thread(screen.thumb)
                if screen.changed(base, cur):
                    await self.settle(cur)  # page loads: wait for them (Devin: early plans there gain ~0)
                    return "pixels"
            try:
                await asyncio.wait_for(self.poke.wait(), 0.25)
            except TimeoutError:
                pass
            self.poke.clear()
        return "stopped"

    async def quiet(self, cap: float = 3.0) -> None:
        """Before a screenshot: if the person is mid-action in the task's app (just typed or
        clicked), wait for the pause. No delay at all when nothing happened recently."""
        end = time.time() + cap
        while time.time() < end and not self.stopped:
            click_ago, key_ago = screen.seconds_since_input()
            if (key_ago > 0.7 and click_ago > 0.4) or screen.front_window()[0] not in self.task_apps:
                return
            await asyncio.sleep(0.15)

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


def changed_since(mark, task_apps: set[str]) -> str | None:
    """Did the person do something in the task's app(s) since `mark`? Input in other apps
    (e.g. typing a message elsewhere) doesn't count."""
    t, win = mark
    if screen.front_window()[0] not in task_apps:
        return None
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
        "timeout": "Nothing changed on screen for a while. Look again: maybe the step can't be done "
                   "this way (wrong area, feature moved or removed).",
    }.get(why, f"The person acted ({why}). Judge progress from the new screenshot and continue "
               "from where they are now; skip steps that are already done.")


UI_REQUEST = re.compile(r"\b(show|where|click|open|find|how do|how to|go to|montre|où|ou est|clique|ouvre|"
                        r"trouve|comment|va sur)\b", re.IGNORECASE)
STOP_PHRASES = {"stop", "stop it", "stop shadow", "arrête", "arrete", "arrête-toi", "cancel",
                "annule", "c'est bon stop"}



def is_stop(text: str) -> bool:
    """Only a bare 'stop' stops: 'stop the video at 2:00' is a task, not a command."""
    return text.lower().strip(" .!?,") in STOP_PHRASES



FAST_WORDS = re.compile(r"\b(fast|quick(ly)?|vite|rapide(ment)?|hurry|no need to explain)\b", re.IGNORECASE)
CONTROL_WORDS = {"stop", "wait", "attends", "pause", "next", "suivant", "continue", "go", "no", "non", "yes",
                 "oui", "faster", "vite", "slower", "doucement", "why", "pourquoi", "help", "aide", "arrête",
                 "arrete", "back", "retour", "skip", "again", "encore", "explain", "explique"}


def is_noise(text: str) -> bool:
    """One or two words with no command in them: TV, music or someone else, not the person."""
    words = re.findall(r"[\w']+", text.lower())
    return len(words) <= 2 and not any(w in CONTROL_WORDS for w in words)


def narrate(name: str, args: dict, why: str) -> str:
    """What Do it mode says out loud while acting, like a tutor."""
    what = {"click": f"Clicking {short(args.get('element', ''), 50)}",
            "right_click": f"Right-clicking {short(args.get('element', ''), 50)}",
            "double_click": f"Double-clicking {short(args.get('element', ''), 50)}",
            "drag": f"Dragging {short(args.get('element', ''), 30)} onto {short(args.get('to_element', ''), 30)}",
            "type": f"Typing {spoken_text(args.get('text', ''))}",
            "press": f"Pressing {args.get('keys', '')}",
            "scroll": "Scrolling"}.get(name, name)
    return f"{what}, {why}" if why else what


def spoken_text(text: str) -> str:
    """Typed text as it should be read aloud: no Tab/Return characters, short."""
    text = text.replace("\t", ", ").replace("\n", ". ").strip(" .,")
    return short(text, 60)


def label_of(name: str, args: dict) -> str:
    if name == "click":
        return f"Click {args.get('element', '')}".strip()
    if name == "right_click":
        return f"Right-click {args.get('element', '')}".strip()
    if name == "double_click":
        return f"Double-click {args.get('element', '')}".strip()
    if name == "drag":
        return f"Drag {args.get('element', '')} onto {args.get('to_element', '')}".strip()
    if name == "type":
        where = f" in {args['element']}" if args.get("element") else ""
        return f'Type "{args.get("text", "")}"{where}'
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
