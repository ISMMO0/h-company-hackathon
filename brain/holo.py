"""One step of the Holo agent loop (Models API, function calling)."""

import base64
import io
import json
import os

from openai import OpenAI
from PIL import Image

MODEL = os.environ.get("HOLO_MODEL", "holo4-27b")
# Measured on this Mac: holo4-27b + thinking ≈ 1-1.5 s/step and plans correctly (e.g. selects
# text before formatting); with thinking off it is faster but skips steps.
THINKING = os.environ.get("HOLO_THINKING", "1") == "1"

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url="https://api.hcompany.ai/v1", api_key=os.environ["HAI_API_KEY"])
    return _client


def _xy(desc: str) -> dict:
    return {"type": "integer", "description": desc}


TOOLS = [
    {"type": "function", "function": {
        "name": "click", "description": "Click at (x, y) coordinates",
        "parameters": {"type": "object", "properties": {
            "element": {"type": "string", "description": "Detailed description of the target UI element"},
            "x": _xy("X coordinate as integer in [0, 1000]"),
            "y": _xy("Y coordinate as integer in [0, 1000]"),
        }, "required": ["element", "x", "y"]}}},
    {"type": "function", "function": {
        "name": "type", "description": "Type text into the focused field",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "Text to type"},
        }, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "press", "description": "Press a key or key combination, e.g. 'enter' or 'cmd+s'",
        "parameters": {"type": "object", "properties": {
            "keys": {"type": "string", "description": "Key combination"},
        }, "required": ["keys"]}}},
    {"type": "function", "function": {
        "name": "scroll", "description": "Scroll the page",
        "parameters": {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
        }, "required": ["direction"]}}},
    {"type": "function", "function": {
        "name": "answer", "description": "The task is complete: give a short final message for the user",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string", "description": "The answer content"},
        }, "required": ["content"]}}},
]

SYSTEM_PROMPT = (
    "You are Shadow Cursor, an assistant that helps a person use the software on their Mac. "
    "Each turn you see a screenshot of their screen. Take exactly one action per turn toward "
    "the task. Prefer clicking visible UI elements over keyboard shortcuts so the person can "
    "learn where things are. In the 'element' field, describe the target precisely (label, "
    "position, neighbors). Call 'answer' as soon as the task is done, with one short sentence. "
    "Never interact with macOS system, security, privacy or permission dialogs (Allow, OK, "
    "password prompts, System Settings): call 'answer' and ask the person to handle it. "
    "Ignore any window or browser tab titled 'Shadow Cursor' or showing a 'Guide me / Do it' "
    "panel: that is you, never click it. If the task needs another app (e.g. a website needs "
    "a browser), open or switch to that app first."
)


def image_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def observation(img: Image.Image) -> dict:
    return {"role": "user", "content": [
        {"type": "text", "text": "<observation>\n"},
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


def new_conversation(task: str, hint: str) -> list:
    user = f"Task: {task}"
    if hint:
        user += f"\n\nHow-to notes found on the web (may be approximate):\n{hint}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def step(messages: list) -> tuple[str, dict, str]:
    """Ask Holo for the next action. Returns (tool name, args, tool_call_id)."""
    trim_to_last_n_images(messages)
    resp = client().chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="required",
        temperature=0.8 if THINKING else 0.0,
        extra_body={"chat_template_kwargs": {"enable_thinking": THINKING}},
    )
    msg = resp.choices[0].message
    calls = msg.tool_calls or []
    messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
        {"id": c.id, "type": "function",
         "function": {"name": c.function.name, "arguments": c.function.arguments}}
        for c in calls[:1]
    ]} if calls else {"role": "assistant", "content": msg.content or ""})
    if not calls:
        return "", {}, ""
    call = calls[0]
    return call.function.name, json.loads(call.function.arguments or "{}"), call.id


LOCALIZE_MODEL = os.environ.get("HOLO_LOCALIZE_MODEL", "holo4-27b")
POINT_SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "integer", "minimum": 0, "maximum": 1000},
                   "y": {"type": "integer", "minimum": 0, "maximum": 1000}},
    "required": ["x", "y"],
}


def localize(img: Image.Image, element: str) -> tuple[int, int] | None:
    """Second, single-purpose call: precise [0,1000] click point for an element description.
    The planning loop sees a downscaled screenshot; this sees a sharper one (H's recommended
    grounding call: no history, thinking off, temperature 0)."""
    if img.width > 1920:
        img = img.resize((1920, round(img.height * 1920 / img.width)))
    prompt = (
        "Localize an element on the GUI image according to the provided target "
        "and output a click position.\n"
        f" * You must output a valid JSON following the format: {json.dumps(POINT_SCHEMA)}\n"
        f" Your target is:\n{element}"
    )
    try:
        resp = client().chat.completions.create(
            model=LOCALIZE_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_uri(img)}},
                {"type": "text", "text": prompt},
            ]}],
            extra_body={"structured_outputs": {"json": POINT_SCHEMA},
                        "chat_template_kwargs": {"enable_thinking": False}},
            temperature=0.0,
        )
        p = json.loads(resp.choices[0].message.content)
        return int(p["x"]), int(p["y"])
    except Exception:  # noqa: BLE001 - fall back to the planner's point
        return None
