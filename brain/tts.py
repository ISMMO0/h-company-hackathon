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

VOICE = os.environ.get("SHADOW_VOICE", "sage")
MODEL = "gpt-4o-mini-tts"
STYLE = "Friendly, calm tutor showing someone how to use an app. Natural, slightly brisk pace."
CACHE = Path(__file__).resolve().parent.parent / "data" / "tts-cache"


def _key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    env = Path(__file__).resolve().parent.parent / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def audio_file(text: str) -> Path:
    f = CACHE / f"{VOICE}-{hashlib.sha1(text.encode()).hexdigest()[:16]}.mp3"
    if f.exists():
        return f
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps({"model": MODEL, "voice": VOICE, "input": text, "instructions": STYLE,
                         "response_format": "mp3"}).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=6) as r:
        data = r.read()
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f


def main(text: str) -> None:
    try:
        if not _key() or VOICE == "mac":
            raise RuntimeError("no OpenAI voice")
        os.execvp("afplay", ["afplay", str(audio_file(text))])
    except Exception:  # noqa: BLE001 - never stay silent: the Mac voice
        os.execvp("say", ["say", "-r", "190", text])


if __name__ == "__main__":
    main(sys.argv[1])
