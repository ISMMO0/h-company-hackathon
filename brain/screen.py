"""Screen capture and mouse/keyboard control on macOS (main display only for now).

Screenshots are resized to the display size in points, so a pixel in the image sent to
Holo is exactly one screen point: no Retina conversion needed anywhere else.
"""

import subprocess
import tempfile
import time

import Quartz
from AppKit import NSScreen
from PIL import Image, ImageChops


def screen_size() -> tuple[int, int]:
    f = NSScreen.mainScreen().frame()
    return int(f.size.width), int(f.size.height)


def capture_full() -> Image.Image:
    """Main display at native (Retina) resolution."""
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        subprocess.run(["screencapture", "-x", "-m", "-t", "png", f.name], check=True)
        return Image.open(f.name).convert("RGB")


def capture() -> Image.Image:
    return capture_full().resize(screen_size())


def thumb() -> Image.Image:
    """Tiny grayscale screenshot for cheap change detection (pink cursor included: it's static)."""
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        subprocess.run(["screencapture", "-x", "-m", "-t", "jpg", f.name], check=True)
        return Image.open(f.name).convert("L").resize((240, 156))


def changed(a: Image.Image, b: Image.Image, frac: float = 0.006) -> bool:
    """True if more than `frac` of the pixels changed noticeably (ignores hover flicker)."""
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 28 else 0)
    return diff.histogram()[255] > frac * a.width * a.height


def mouse_pos() -> tuple[float, float]:
    p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return p.x, p.y


def mouse_down() -> bool:
    return bool(Quartz.CGEventSourceButtonState(
        Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGMouseButtonLeft))


def wait_for_user_click(stop, timeout: float = 120) -> tuple[float, float] | None:
    """Block until the user presses and releases the left button. Returns where."""
    end = time.time() + timeout
    while mouse_down():  # ignore a click already in progress
        time.sleep(0.02)
    while time.time() < end and not stop():
        if mouse_down():
            pos = mouse_pos()
            while mouse_down():
                time.sleep(0.02)
            return pos
        time.sleep(0.02)
    return None


# Processes that show macOS security / permission prompts. DO mode must never act on them.
SYSTEM_APPS = {
    "UserNotificationCenter", "SecurityAgent", "System Settings", "System Preferences",
    "CoreServicesUIAgent", "universalAccessAuthWarn", "Install Command Line Developer Tools",
    "coreautha", "LocalAuthenticationRemoteService", "Keychain Access",
}


def frontmost_app() -> str:
    """App owning the topmost normal window. NSWorkspace goes stale in a process without a
    Cocoa run loop, so read the live window list instead."""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    for w in windows:  # front to back
        name = w.get("kCGWindowOwnerName", "")
        if w.get("kCGWindowLayer", 0) == 0 and w.get("kCGWindowAlpha", 1) > 0 and \
                name not in ("Electron", "Window Server", "Dock"):
            return name
    return ""


def front_window() -> tuple[str, str]:
    """(app, window title) of the topmost normal window. A change means the person moved on
    (switched app, opened a page) even if the pixels barely changed."""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    for w in windows:
        name = w.get("kCGWindowOwnerName", "")
        if w.get("kCGWindowLayer", 0) == 0 and w.get("kCGWindowAlpha", 1) > 0 and \
                name not in ("Electron", "Window Server", "Dock"):
            return name, w.get("kCGWindowName", "") or ""
    return "", ""


def seconds_since_input() -> tuple[float, float]:
    """(seconds since the last mouse click, seconds since the last key press), system-wide.
    Catches clicks too quick for polling the button state."""
    src = Quartz.kCGEventSourceStateCombinedSessionState
    click = Quartz.CGEventSourceSecondsSinceLastEventType(src, Quartz.kCGEventLeftMouseDown)
    key = Quartz.CGEventSourceSecondsSinceLastEventType(src, Quartz.kCGEventKeyDown)
    return click, key


def window_owner_at(x: float, y: float) -> str:
    """Name of the app whose window is topmost at (x, y), in global points."""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    for w in windows:  # front to back
        if w.get("kCGWindowAlpha", 1) == 0:
            continue
        b = w.get("kCGWindowBounds", {})
        if b.get("X", 0) <= x <= b.get("X", 0) + b.get("Width", 0) and \
                b.get("Y", 0) <= y <= b.get("Y", 0) + b.get("Height", 0):
            name = w.get("kCGWindowOwnerName", "")
            if name in ("Window Server", "Dock") or w.get("kCGWindowLayer", 0) > 1000:
                continue
            return name
    return ""


def _post(ev) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def click(x: float, y: float, double: bool = False) -> None:
    pt = (x, y)
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0))
    time.sleep(0.05)
    for n in range(2 if double else 1):
        for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            ev = Quartz.CGEventCreateMouseEvent(None, t, pt, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, n + 1)
            _post(ev)
            time.sleep(0.03)


def right_click(x: float, y: float) -> None:
    pt = (x, y)
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0))
    time.sleep(0.05)
    for t in (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp):
        _post(Quartz.CGEventCreateMouseEvent(None, t, pt, Quartz.kCGMouseButtonRight))
        time.sleep(0.03)


def drag(x0: float, y0: float, x1: float, y1: float, steps: int = 20) -> None:
    """Press at (x0, y0), move in small steps, release at (x1, y1) (apps need the moves)."""
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (x0, y0), 0))
    time.sleep(0.05)
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (x0, y0), Quartz.kCGMouseButtonLeft))
    time.sleep(0.12)
    for i in range(1, steps + 1):
        pt = (x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDragged, pt, Quartz.kCGMouseButtonLeft))
        time.sleep(0.015)
    time.sleep(0.1)
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (x1, y1), Quartz.kCGMouseButtonLeft))


def type_text(text: str) -> None:
    """Types text; '\t' presses Tab and '\n' presses Return, so a whole table row is one action.
    A Tab right before a Return is dropped: in a spreadsheet, Return on an empty cell opens it
    instead of going to the next row, which pushed the next rows onto the same line."""
    while "\t\n" in text:
        text = text.replace("\t\n", "\n")
    for ch in text:
        if ch in "\t\n":
            press("tab" if ch == "\t" else "enter")
            time.sleep(0.05)
            continue
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
            _post(ev)
        time.sleep(0.01)


KEYCODES = {
    "enter": 36, "return": 36, "tab": 48, "space": 49, "delete": 51, "backspace": 51,
    "escape": 53, "esc": 53, "left": 123, "right": 124, "down": 125, "up": 126,
    **{c: k for c, k in zip("asdfhgzxcv", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])},
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "o": 31, "u": 32,
    "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
}
MODIFIERS = {
    "cmd": Quartz.kCGEventFlagMaskCommand, "command": Quartz.kCGEventFlagMaskCommand,
    "ctrl": Quartz.kCGEventFlagMaskControl, "control": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate, "option": Quartz.kCGEventFlagMaskAlternate,
    "shift": Quartz.kCGEventFlagMaskShift,
}


def press(keys: str) -> None:
    """Press a key combo like 'cmd+s' or 'enter'."""
    parts = [p.strip().lower() for p in keys.replace(" ", "+").split("+") if p.strip()]
    flags = 0
    for p in parts[:-1]:
        flags |= MODIFIERS.get(p, 0)
    code = KEYCODES.get(parts[-1])
    if code is None:
        type_text(parts[-1])
        return
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, code, down)
        Quartz.CGEventSetFlags(ev, flags)
        _post(ev)
        time.sleep(0.02)


def scroll(direction: str, amount: int = 5, at: tuple[float, float] | None = None) -> None:
    if at:  # scroll events go to whatever is under the mouse
        _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, at, 0))
        time.sleep(0.05)
    dy = amount if direction == "up" else -amount
    dx = amount if direction == "left" else -amount if direction == "right" else 0
    if direction in ("left", "right"):
        dy = 0
    _post(Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 2, dy, dx))
