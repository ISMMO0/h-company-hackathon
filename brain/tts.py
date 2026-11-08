"""Shadow's voice: OpenAI TTS (voice 'sage' by default), cached on disk, Mac `say` as fallback.

Runs as its own process (`python -m brain.tts "text"`) that becomes `afplay` once the audio is
ready, so the agent can poll it to know when the voice ends and terminate it to hush it.
Only the standard library: the process must start fast.
"""

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

from brain import cloud

VOICE = os.environ.get("SHADOW_VOICE", "sage")
MODEL = "gpt-4o-mini-tts"
STYLE = "Friendly, calm tutor showing someone how to use an app. Natural, slightly brisk pace."
CACHE = Path("data") / "tts-cache"  # relative to the working dir: the repo, or the app's data folder


def _key() -> str:
    key = cloud.key("OPENAI_API_KEY")
    if key:
        return key
    env = Path(".env")
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def audio_file(text: str) -> Path:
    f = CACHE / f"{VOICE}-{hashlib.sha1(text.encode()).hexdigest()[:16]}.mp3"
    if f.exists():
        return f
    req = urllib.request.Request(
        cloud.base("openai", "https://api.openai.com/v1") + "/audio/speech",
        data=json.dumps({"model": MODEL, "voice": VOICE, "input": text, "instructions": STYLE,
                         "response_format": "mp3"}).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=6) as r:
        data = r.read()
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{os.getpid()}.part")
    tmp.write_bytes(data)
    tmp.replace(f)  # atomic: a parallel prefetch never exposes a half-written file
    return f


def main(text: str) -> None:
    try:
        if not _key() or VOICE == "mac":
            raise RuntimeError("no OpenAI voice")
        os.execvp("afplay", ["afplay", str(audio_file(text))])
    except Exception:  # noqa: BLE001 - never stay silent: the Mac voice
        os.execvp("say", ["say", "-r", "190", text])


def prefetch(text: str) -> None:
    """Fetch and cache the audio only (no sound), so the real `speak` starts instantly."""
    try:
        if _key() and VOICE != "mac":
            audio_file(text)
    except Exception:  # noqa: BLE001, S110 - the real call will retry or fall back
        pass


def cli(args: list[str]) -> None:
    if args[0] == "--prefetch":
        prefetch(args[1])
    else:
        main(args[0])


if __name__ == "__main__":
    cli(sys.argv[1:])
