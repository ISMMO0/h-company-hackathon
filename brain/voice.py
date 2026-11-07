"""Voice command capture: mic → Gladia live STT → one final utterance.

    text = await voice.listen_once(on_partial=print)
"""

import asyncio
import os
from collections.abc import Callable

import aiohttp
import sounddevice as sd

SAMPLE_RATE = 16000
BLOCK = SAMPLE_RATE // 10  # 100 ms of audio per frame
TIMEOUT = 20.0

SESSION_CONFIG = {
    "encoding": "wav/pcm",
    "sample_rate": SAMPLE_RATE,
    "bit_depth": 16,
    "channels": 1,
    "language_config": {"languages": ["fr", "en"], "code_switching": True},
    "endpointing": 0.3,
    "maximum_duration_without_endpointing": 15,
    "messages_config": {"receive_partial_transcripts": True},
}


async def listen_once(on_partial: Callable[[str], None] | None = None) -> str:
    """Record the mic until the first final utterance and return its text ('' on timeout)."""
    try:
        return await asyncio.wait_for(_listen(on_partial), TIMEOUT)
    except TimeoutError:
        return ""


async def _listen(on_partial) -> str:
    loop = asyncio.get_running_loop()
    frames: asyncio.Queue[bytes] = asyncio.Queue()

    def on_audio(indata, _frames, _time, _status) -> None:
        loop.call_soon_threadsafe(frames.put_nowait, bytes(indata))

    async with aiohttp.ClientSession() as http:
        async with http.post(
            "https://api.gladia.io/v2/live",
            headers={"x-gladia-key": os.environ["GLADIA_API_KEY"]},
            json=SESSION_CONFIG,
        ) as resp:
            resp.raise_for_status()
            url = (await resp.json())["url"]

        async with http.ws_connect(url) as ws:
            stream = sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK, channels=1,
                                       dtype="int16", callback=on_audio)
            sender = asyncio.create_task(_send_audio(ws, frames))
            try:
                with stream:
                    return await _first_final(ws, on_partial)
            finally:
                sender.cancel()
                await _stop(ws)


async def _send_audio(ws: aiohttp.ClientWebSocketResponse, frames: asyncio.Queue) -> None:
    while True:
        await ws.send_bytes(await frames.get())


async def _first_final(ws: aiohttp.ClientWebSocketResponse, on_partial) -> str:
    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            break
        data = msg.json()
        if data.get("type") != "transcript":
            continue
        text = (data["data"].get("utterance") or {}).get("text", "").strip()
        if data["data"].get("is_final"):
            if text:
                return text
        elif on_partial and text:
            on_partial(text)
    return ""


async def _stop(ws: aiohttp.ClientWebSocketResponse) -> None:
    try:
        if not ws.closed:
            await ws.send_json({"type": "stop_recording"})
            await asyncio.wait_for(ws.close(), 2)
    except (TimeoutError, aiohttp.ClientError, ConnectionError):
        pass
