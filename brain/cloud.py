"""In the jury's app the brain holds no API keys: SHADOW_API points to our cloud (server/proxy.py on
Aiven), which adds them. Without SHADOW_API (our own Macs) it calls the providers with the .env keys.
Only the standard library: brain.tts imports it and must start fast."""

import os

API = os.environ.get("SHADOW_API", "").rstrip("/")
TOKEN = os.environ.get("SHADOW_APP_TOKEN", "shadow-cursor-jury")  # not a secret: keeps scanners out


def base(name: str, direct: str) -> str:
    return f"{API}/{name}" if API else direct


def key(env: str) -> str:
    return TOKEN if API else os.environ.get(env, "")
