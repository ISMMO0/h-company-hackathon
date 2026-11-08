"""Holo calls: plan the next action (with a numbered plan and progress) and point precisely.

Two kinds of calls per step:
- plan: the whole screen, downscaled (the next target can be anywhere);
- point: a native-resolution crop around the planner's rough point (small upload, sharper
  icons), falling back to the whole screen if the crop looks wrong.
"""

import base64
import concurrent.futures as cf
import io
import json
import os
import time

from openai import APITimeoutError, OpenAI
from PIL import Image

from brain import cloud

MODEL = os.environ.get("HOLO_MODEL", "holo4-27b")
POINT_MODEL = os.environ.get("HOLO_POINT_MODEL", "holo4-27b")
EFFORT = os.environ.get("HOLO_EFFORT", "low")  # holo4-27b: low | medium | xhigh | none
PLAN_WIDTH = int(os.environ.get("HOLO_PLAN_WIDTH", "1024"))
CROP_PTS = (400, 260)  # pointing crop, in screen points (doubled on Retina)

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        # Never wait forever on one request: a stuck call froze a whole task in testing.
        _client = OpenAI(base_url=cloud.base("holo", "https://api.hcompany.ai/v1"), api_key=cloud.key("HAI_API_KEY"),
                         timeout=8, max_retries=0)
    return _client


def image_uri(img: Image.Image, quality: int = 80) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def shrink(img: Image.Image, width: int = PLAN_WIDTH) -> Image.Image:
    if img.width <= width:
        return img
    return img.resize((width, round(img.height * width / img.width)))


# --- tools -------------------------------------------------------------------------------

_STEP = {"type": "integer", "description": "Number of the plan step this action belongs to (1-based)"}
_PLAN = {"type": "array", "items": {"type": "string"},
         "description": "Short numbered plan for the whole task (3-8 steps, a few words each). "
                        "Fill it on your first action and whenever it changes; omit otherwise."}


def _tool(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


_WHY = {"type": "string", "description": "Why this action, in a few words a beginner understands "
                                        "(e.g. 'that's where skills live'). Spoken to the person. In DO mode, "
                                        "the first time: one or two short sentences that teach the idea; "
                                        "after that, at most 10 words."}


def _action(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return _tool(name, desc, {**props, "step": _STEP, "why": _WHY, "plan": _PLAN}, [*required, "step"])


TOOLS = [
    _action("click", "Click at (x, y) coordinates", {
        "element": {"type": "string", "description": "Detailed description of the target UI element"},
        "x": {"type": "integer", "description": "X coordinate as integer in [0, 1000]"},
        "y": {"type": "integer", "description": "Y coordinate as integer in [0, 1000]"},
    }, ["element", "x", "y"]),
    _action("right_click", "Right-click at (x, y) to open a context menu", {
        "element": {"type": "string", "description": "Detailed description of the target UI element"},
        "x": {"type": "integer", "description": "X coordinate as integer in [0, 1000]"},
        "y": {"type": "integer", "description": "Y coordinate as integer in [0, 1000]"},
    }, ["element", "x", "y"]),
    _action("double_click", "Double-click at (x, y) (open an item, edit a value)", {
        "element": {"type": "string", "description": "Detailed description of the target UI element"},
        "x": {"type": "integer", "description": "X coordinate as integer in [0, 1000]"},
        "y": {"type": "integer", "description": "Y coordinate as integer in [0, 1000]"},
    }, ["element", "x", "y"]),
    _action("drag", "Drag from one element to another (e.g. a track onto a deck)", {
        "element": {"type": "string", "description": "What to drag"},
        "x": {"type": "integer", "description": "Start X in [0, 1000]"},
        "y": {"type": "integer", "description": "Start Y in [0, 1000]"},
        "to_element": {"type": "string", "description": "Where to drop it"},
        "to_x": {"type": "integer", "description": "Drop X in [0, 1000]"},
        "to_y": {"type": "integer", "description": "Drop Y in [0, 1000]"},
    }, ["element", "x", "y", "to_element", "to_x", "to_y"]),
    _action("type", "Type text into a field or cell (it is clicked first if needed). '\t' moves to the "
                    "next cell/field, '\n' presses Return, so a row can be one action (e.g. 'Pizza\t4\t12\n') "
                    "once the person has seen the first one typed step by step. Never leave an empty cell before '\n': type formulas in the "
                    "row itself (e.g. 'Pizza\t10\t=E2*B2\n').", {
        "text": {"type": "string", "description": "Text to type; \t = Tab, \n = Return"},
        "element": {"type": "string", "description": "The field or cell to type into, e.g. 'cell A1'"},
        "x": {"type": "integer", "description": "X in [0, 1000] of that field"},
        "y": {"type": "integer", "description": "Y in [0, 1000] of that field"},
    }, ["text", "element", "x", "y"]),
    _action("press", "Press a key or key combination, e.g. 'enter' or 'cmd+s'",
            {"keys": {"type": "string", "description": "Key combination"}}, ["keys"]),
    _action("scroll", "Scroll the page or panel under (x, y)",
            {"direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
             "x": {"type": "integer", "description": "X in [0, 1000] of the area to scroll"},
             "y": {"type": "integer", "description": "Y in [0, 1000] of the area to scroll"}},
            ["direction", "x", "y"]),
    _action("say", "Tell the person something out loud without acting: answer their question, "
                   "or explain something. One or two short sentences.",
            {"text": {"type": "string", "description": "What to say"}}, ["text"]),
    _action("wait", "Pause: the person is doing something unrelated, or the screen is loading. "
                    "You will get a new screenshot when something changes.",
            {"reason": {"type": "string", "description": "Short reason shown to the person"}}, ["reason"]),
    _tool("answer", "The task is complete: give a short final message for the person",
          {"content": {"type": "string", "description": "The answer content"}}, ["content"]),
]

SYSTEM_PROMPT = """You are Shadow Cursor, a pink second cursor that helps a person use the software on their Mac.
Each turn you see a screenshot of their screen and take exactly one action.

Mode GUIDE: you only show the action (the pink cursor points, a voice says it) and the person does it.
Mode DO: your action is executed for real while the person watches. DO mode is a lesson, not a race:
the goal is that the person learns how to do it. The FIRST time you do something (a header row, a first
data row, a first formula, a menu path), do it in small visible steps, one idea per action, and use 'why'
to teach the idea (e.g. "a formula always starts with =, and E2*B2 multiplies the quantity by the price").
Once the person has seen a pattern, repeat it faster (type the remaining rows in one action, fill a
formula down) and say so in 'why' ("same thing for the other rows"). Go fast from the start only if the
person asks for speed or the context shows they have already done this kind of task.

Keep a short numbered plan for the task. Fill 'plan' on your first action and again whenever it changes.
Every action has 'step' = the plan step it belongs to, and 'why' = a few words explaining it like a tutor.
Explaining goes in 'why', which is spoken with the action: never spend a turn on 'say' to announce or
explain the plan. Use 'say' only to answer a question the person asked, or when you are blocked.
If a playbook from the web is given, follow it: it is the known path. Adapt only to what the screen
shows (different layout, a step already done). Do not explore when the playbook names the target.

The person may skip ahead, go back, or do things their own way. Always judge where they are from the
CURRENT screenshot, never from what you asked before. If a later step is already reached, continue from
there. If the person seems to do something unrelated, use 'wait'.

Start from where the person already is. Each observation tells you the front window. Before acting, tick
off every playbook step that the screen shows is already done. NEVER send them back to a site or app they
are already on (no "open youtube.com" when YouTube is on screen), and never retype a URL or use a URL
shortcut: teach the page's own navigation (menus, sidebar, buttons), e.g. YouTube sidebar Explore > Trending.

When the person speaks, their words appear as a message. Obey them: if they say they are ahead, re-check
the screen and continue; if they ask a question, use 'say'; if they ask you to wait, use 'wait'; if they
change the goal, update the plan.

Prefer clicking visible UI elements over keyboard shortcuts so the person learns where things are.
Names in the task come from speech recognition and are often misheard, especially song titles, artists,
files and non-English words ("Chia Kola" may be "Tiakola", "OG tea" may be "OG feat."). Match them to the
closest names visible on screen and use the on-screen spelling; if unsure between several, use 'say' to ask.
Never ask to click something that is already selected or focused (e.g. a cell that already has the blue
border): go straight to the next action, e.g. 'type' into it.
To change a spreadsheet cell's value, just 'type' into the cell: typing replaces its content. Do not
double-click it first (that edits inside the old value, e.g. 5 + 10 gives 510).
Never ask to click an empty area "to focus" something. Never type in the browser's address bar and never
open new tabs: use the page's own fields and buttons. If you are stuck, use 'say' to ask the person.
When text came out wrong in a field, select it all (cmd+a) and retype it, instead of clicking around in it.
In GUIDE mode, typing something and confirming it is ONE step: put '\n' at the end of the text
("type 4 and press Return"); never make Return its own step.
Keys for 'press': use names like home, end, delete, return, tab, escape, up, down, left, right, cmd+a.
If something the plan expects isn't on screen after one look (or one scroll), it may have been removed or
renamed: check the app cheat sheet and web notes, use 'say' to tell the person, and use the replacement.
In 'element', describe the target precisely (label, position, neighbours).
Never interact with macOS system, security, privacy or permission dialogs: use 'say' to ask the person.
Ignore any window or tab titled 'Shadow Cursor' or showing a 'Guide me / Do it' panel: that is you.
If the task needs another app (e.g. a website needs a browser), open or switch to it first.
Call 'answer' as soon as the task is done, with one short sentence."""


def observation(img: Image.Image, where: str = "") -> dict:
    head = f"<observation>\nFront window: {where}\n" if where else "<observation>\n"
    return {"role": "user", "content": [
        {"type": "text", "text": head},
        {"type": "image_url", "image_url": {"url": image_uri(img)}},
        {"type": "text", "text": "\n</observation>"},
    ]}


def trim_to_last_n_images(messages: list, n: int = 3) -> None:
    seen = 0
    for msg in reversed(messages):
        if msg["role"] != "user" or not isinstance(msg["content"], list):
            continue
        for chunk in msg["content"]:
            if chunk.get("type") != "image_url":
                continue
            seen += 1
            if seen > n:
                chunk["type"] = "text"
                chunk["text"] = "[screenshot evicted]"
                chunk.pop("image_url", None)


POINT_TIMEOUT = 5.0
HEDGE_AFTER = float(os.environ.get("HOLO_HEDGE_AFTER", "3.0"))
_pool = cf.ThreadPoolExecutor(max_workers=6)


def _create_hedged(messages: list, tools: list):
    """The planning call, hedged: if the normal call (thinking 'low') isn't back after
    HEDGE_AFTER s, fire a fast one (no thinking) in parallel, and a second fast one after
    another HEDGE_AFTER s; take whichever answers first. Holo sometimes hangs on one request;
    this keeps steps around 1-4 s and a stuck call never costs more than ~8 s."""
    calls = [_pool.submit(_create, messages, tools)]
    for _ in range(2):
        done, _ = cf.wait(calls, timeout=HEDGE_AFTER, return_when=cf.FIRST_COMPLETED)
        for f in done:
            if f.exception() is None:
                return f.result()
        calls = [f for f in calls if f not in done]  # drop the ones that failed fast
        calls.append(_pool.submit(_create, messages, tools, effort="none"))
    error = None
    for f in cf.as_completed(calls):
        if f.exception() is None:
            return f.result()
        error = f.exception()
    raise error


def _create(messages: list, tools: list | None = None, effort: str | None = None, **kw):
    effort = effort or EFFORT
    params = {"model": MODEL, "messages": messages, "temperature": 0.8 if effort != "none" else 0.0}
    if tools:
        params.update(tools=tools, tool_choice="required")
    if effort == "none":
        params["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    else:
        params["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
        params["reasoning_effort"] = effort
    params.update(kw)
    return client().chat.completions.create(**params)


class Planner:
    """The conversation with Holo for one task. `next()` is pure: nothing is added to the
    history until `accept()`, so an answer computed on a stale screen can be dropped."""

    def __init__(self, task: str, mode: str, context: str = "") -> None:
        user = f"Task: {task}\nMode: {mode.upper()}"
        if context:
            user += f"\n\nEarlier in this session:\n{context}"
        self.messages: list = [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": user}]
        self.plan: list[str] = []
        self.step = 0

    def note(self, text: str) -> None:
        """Add a text message from the person or the app (hint, mode change, speech)."""
        self.messages.append({"role": "user", "content": text})

    def next(self, img: Image.Image, where: str = "") -> dict:
        """Ask for the next action on `img` (screen-point sized). Returns an action dict."""
        obs = observation(shrink(img), where)
        msgs = [*self.lean(), obs]
        trim_to_last_n_images(msgs)
        t0 = time.perf_counter()
        resp = _create_hedged(msgs, TOOLS)
        dt = time.perf_counter() - t0
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        if not calls:
            return {"name": "", "args": {}, "id": "", "obs": obs, "content": msg.content or "",
                    "timings": {"plan": dt}}
        c = calls[0]
        try:
            args = json.loads(c.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        return {"name": c.function.name, "args": args, "id": c.id, "obs": obs,
                "content": msg.content, "raw_args": c.function.arguments, "timings": {"plan": dt}}

    def lean(self, keep: int = 12) -> list:
        """System + task + playbook, then only the recent turns: a growing history made each
        step slower. Never start the tail on a tool result (it needs its tool call)."""
        head = self.messages[:2]
        playbook = [m for m in self.messages[2:] if m["role"] == "user"
                    and isinstance(m["content"], str) and m["content"].startswith("Playbook")]
        tail = self.messages[2:][-keep:]
        while tail and tail[0]["role"] == "tool":
            tail = tail[1:]
        return head + [m for m in playbook if m not in tail] + tail

    def accept(self, action: dict) -> None:
        """Commit an action computed by next() to the history."""
        self.messages.append(action["obs"])
        if not action["name"]:
            self.messages.append({"role": "assistant", "content": action.get("content") or ""})
            return
        self.messages.append({"role": "assistant", "content": action.get("content"), "tool_calls": [
            {"id": action["id"], "type": "function",
             "function": {"name": action["name"], "arguments": action["raw_args"] or "{}"}}]})
        args = action["args"]
        if isinstance(args.get("plan"), list) and args["plan"]:
            self.plan = [str(s) for s in args["plan"]][:10]
        if isinstance(args.get("step"), int):
            self.step = args["step"]

    def result(self, action: dict, text: str) -> None:
        if action["name"]:
            self.messages.append({"role": "tool", "tool_call_id": action["id"], "content": text})


# --- pointing ----------------------------------------------------------------------------

POINT_SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "integer", "minimum": 0, "maximum": 1000},
                   "y": {"type": "integer", "minimum": 0, "maximum": 1000}},
    "required": ["x", "y"],
}


class SlowPoint(Exception):
    """The pointing call timed out: use the planner's rough point instead of waiting again."""


def _localize(img: Image.Image, element: str) -> tuple[int, int] | None:
    prompt = (
        "Localize an element on the GUI image according to the provided target "
        "and output a click position.\n"
        f" * You must output a valid JSON following the format: {json.dumps(POINT_SCHEMA)}\n"
        f" Your target is:\n{element}"
    )
    try:
        resp = client().with_options(timeout=POINT_TIMEOUT).chat.completions.create(
            model=POINT_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_uri(img, 85)}},
                {"type": "text", "text": prompt},
            ]}],
            extra_body={"structured_outputs": {"json": POINT_SCHEMA},
                        "chat_template_kwargs": {"enable_thinking": False}},
            temperature=0.0,
        )
        p = json.loads(resp.choices[0].message.content)
        return int(p["x"]), int(p["y"])
    except APITimeoutError as e:
        raise SlowPoint from e
    except Exception:  # noqa: BLE001 - caller falls back
        return None


def point(full: Image.Image, element: str, rough: tuple[int, int] | None) -> tuple[int, int]:
    """Precise [0,1000] point (normalized to `full`) for `element`. Crops around `rough`
    first; if the answer hugs the crop edge (target probably outside), retries on the
    whole screen."""
    if rough:
        scale = full.width / 1470 if full.width > 2000 else 1.0  # Retina: 2 px per point
        cw, ch = int(CROP_PTS[0] * scale), int(CROP_PTS[1] * scale)
        cx, cy = rough[0] / 1000 * full.width, rough[1] / 1000 * full.height
        x0 = int(min(max(cx - cw / 2, 0), full.width - cw))
        y0 = int(min(max(cy - ch / 2, 0), full.height - ch))
        try:
            p = _localize(full.crop((x0, y0, x0 + cw, y0 + ch)), element)
        except SlowPoint:
            return rough  # Holo is slow: the planner's point beats another 5 s wait
        if p and 30 < p[0] < 970 and 30 < p[1] < 970:
            return (round((x0 + p[0] / 1000 * cw) / full.width * 1000),
                    round((y0 + p[1] / 1000 * ch) / full.height * 1000))
    try:
        p = _localize(shrink(full, 1920), element)
    except SlowPoint:
        p = None
    return p if p else (rough or (500, 500))


# --- one-shot helpers for scripts/bench.py -------------------------------------------------

def plan_step(task: str, screenshot: Image.Image, hint: str = "") -> dict:
    pl = Planner(task, "guide")
    if hint:
        pl.note(f"How-to notes found on the web (may be approximate):\n{hint}")
    a = pl.next(screenshot)
    return {"name": a["name"], "args": a["args"], "timings": a["timings"]}
