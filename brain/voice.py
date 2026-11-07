"""Push-to-talk: mic → Gladia live STT, with live text.

    lis = Listener(on_text=print)
    await lis.start()          # ⌃⌥Space
    text = await lis.finish()  # ⌃⌥Space again: send now
    await lis.cancel()         # ⌃⌥X
"""

import asyncio
import os
from collections.abc import Callable

import aiohttp
import sounddevice as sd

SAMPLE_RATE = 16000
BLOCK = SAMPLE_RATE // 10  # 100 ms of audio per frame
SILENCE_SEND = 4.0  # fallback: send by itself after this long without new words
MAX_SECONDS = 60.0

SESSION_CONFIG = {
    "encoding": "wav/pcm",
    "sample_rate": SAMPLE_RATE,
    "bit_depth": 16,
    "channels": 1,
    "language_config": {"languages": ["fr", "en"], "code_switching": True},
    "endpointing": 0.8,
    "maximum_duration_without_endpointing": 15,
    "messages_config": {"receive_partial_transcripts": True, "receive_speech_events": True},
    # Default threshold missed quieter speech in testing; raise it if a noisy room triggers it.
    "pre_processing": {"speech_threshold": 0.3},
}


class Listener:
    """Mic → Gladia. Two uses:
    - push-to-talk: `on_text(text)` gets the live text (finals + current partial),
      `on_auto_send()` fires after SILENCE_SEND seconds of quiet, `finish()` returns the text;
    - open mic (continuous=True): `on_final(sentence)` fires for every finished sentence and
      the session stays open until `cancel()`.
    `muted()` returning True drops what is heard (e.g. while Shadow itself is speaking).
    `on_speech()` fires when the person starts talking."""

    def __init__(self, on_text: Callable[[str], None] | None = None,
                 on_auto_send: Callable[[], None] | None = None,
                 on_final: Callable[[str], None] | None = None,
                 on_speech: Callable[[], None] | None = None,
                 muted: Callable[[], bool] | None = None,
                 continuous: bool = False) -> None:
        self.on_text = on_text
        self.on_auto_send = on_auto_send
        self.on_final = on_final
        self.on_speech = on_speech
        self.muted = muted or (lambda: False)
        self.continuous = continuous
        self.finals: list[str] = []
        self.partial = ""
        self.last_words = 0.0
        self._http: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._stream: sd.RawInputStream | None = None
        self._tasks: list[asyncio.Task] = []
        self._closed = asyncio.Event()

    @property
    def text(self) -> str:
        return " ".join([*self.finals, self.partial]).strip()

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        frames: asyncio.Queue[bytes] = asyncio.Queue()
        self._http = aiohttp.ClientSession()
        async with self._http.post("https://api.gladia.io/v2/live",
                                   headers={"x-gladia-key": os.environ["GLADIA_API_KEY"]},
                                   json=SESSION_CONFIG) as resp:
            resp.raise_for_status()
            url = (await resp.json())["url"]
        self._ws = await self._http.ws_connect(url)
        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=BLOCK, channels=1, dtype="int16",
            callback=lambda d, *_: loop.call_soon_threadsafe(frames.put_nowait, bytes(d)))
        self._stream.start()
        self.last_words = loop.time()
        self._tasks = [asyncio.create_task(self._send(frames)),
                       asyncio.create_task(self._read()),
                       asyncio.create_task(self._watchdog())]

    async def _send(self, frames: asyncio.Queue) -> None:
        while True:
            chunk = await frames.get()
            # While Shadow speaks, Gladia gets silence: our own voice is never transcribed, and
            # nothing the person said before or after is dropped.
            await self._ws.send_bytes(bytes(len(chunk)) if self.muted() else chunk)

    async def _read(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            async for msg in self._ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                data = msg.json()
                if data.get("type") == "speech_start":
                    self.last_words = loop.time()
                    if self.on_speech and not self.muted():
                        self.on_speech()
                if data.get("type") != "transcript":
                    continue
                text = (data["data"].get("utterance") or {}).get("text", "").strip()
                if data["data"].get("is_final"):
                    self.partial = ""
                    if text and self.continuous:
                        if self.on_final:
                            self.on_final(text)
                    elif text:
                        self.finals.append(text)
                else:
                    self.partial = text
                self.last_words = loop.time()
                if self.on_text:
                    self.on_text(self.text)
        finally:
            self._closed.set()

    async def _watchdog(self) -> None:
        if self.continuous:
            return  # open mic: no auto-send, lives until cancel()
        loop = asyncio.get_running_loop()
        started = loop.time()
        while True:
            await asyncio.sleep(0.25)
            quiet = loop.time() - self.last_words
            if (self.text and quiet > SILENCE_SEND) or loop.time() - started > MAX_SECONDS:
                if self.on_auto_send:
                    self.on_auto_send()
                return

    async def finish(self) -> str:
        """Send now: stop the mic, let Gladia flush its last final (≤1.5 s), return the text."""
        self._stop_mic()
        try:
            if self._ws and not self._ws.closed:
                await self._ws.send_json({"type": "stop_recording"})
                await asyncio.wait_for(self._closed.wait(), 1.5)
        except (TimeoutError, aiohttp.ClientError, ConnectionError):
            pass
        text = self.text
        await self._close()
        return text

    async def cancel(self) -> None:
        self._stop_mic()
        await self._close()

    def _stop_mic(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._tasks:
            self._tasks[0].cancel()  # sender
            self._tasks[2].cancel()  # watchdog

    async def _close(self) -> None:
        for t in self._tasks:
            t.cancel()
        try:
            if self._ws and not self._ws.closed:
                await asyncio.wait_for(self._ws.close(), 1)
        except (TimeoutError, aiohttp.ClientError, ConnectionError):
            pass
        if self._http:
            await self._http.close()


async def listen_once(on_partial: Callable[[str], None] | None = None) -> str:
    """For scripts/try_voice.py: listen until a quiet pause, return the text."""
    done = asyncio.Event()
    lis = Listener(on_text=on_partial, on_auto_send=done.set)
    await lis.start()
    try:
        await asyncio.wait_for(done.wait(), MAX_SECONDS)
    except TimeoutError:
        pass
    return await lis.finish()
