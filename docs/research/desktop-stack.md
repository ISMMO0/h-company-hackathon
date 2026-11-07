# Shadow Cursor — macOS desktop stack research

Decision doc for the Shadow Cursor prototype (pink "shadow" cursor + voice, GUIDE and DO modes).
Scope: what to build the macOS shell with, how to capture/act on the screen, how to wire voice.
Facts below link to official docs; "recommendation" lines are our call for a 24h build.

## TL;DR

- **Shell: Electron (TypeScript) for the overlay only + a Python 3.11 "brain" process** that owns
  every API key, the screenshots, the synthetic input and the Gladia/Holo/Linkup calls. Electron needs
  no macOS permissions at all; Python needs Screen Recording + Accessibility + Microphone.
- Screenshot with `screencapture -x` (or ScreenCaptureKit) in **device pixels**, send the *same bytes*
  to Holo, map `[0,1000]` → pixels → points with the display's `backingScaleFactor`.
- DO mode = `CGEvent` posts from Python; pause the moment a human-origin mouse event is seen.
- Push-to-talk = **toggle** hotkey (Electron `globalShortcut`) + Gladia endpointing/`speech_end` to
  auto-finish. True hold-to-talk needs key-up, which `globalShortcut` doesn't give.
- Gladia has **no TTS**. Use macOS `AVSpeechSynthesizer`/`say` (offline, instant) for the demo; swap
  in ElevenLabs Flash v2.5 or Cartesia Sonic for voice quality if time allows.

## 1. Overlay window

Requirements: transparent, always on top, click-through, one per display, visible over full-screen
apps and on every Space, animated pink cursor.

| Option | Overlay effort | Native access (capture/input) | Verdict for 24h |
|---|---|---|---|
| **Electron** | Trivial: `transparent`, `setIgnoreMouseEvents`, `setAlwaysOnTop('screen-saver')`, `setVisibleOnAllWorkspaces(..., {visibleOnFullScreen})`, `type: 'panel'`. CSS/canvas animation for free. | None built in (no CGEvent). Needs a native module or a sidecar. | **Pick** (as view layer) |
| Tauri v2 | Needs `app.macOSPrivateApi: true` for transparency ([config](https://v2.tauri.app/reference/config/#macosprivateapi)); `setIgnoreCursorEvents`, `setAlwaysOnTop`, `setVisibleOnAllWorkspaces` exist ([Window API](https://v2.tauri.app/reference/javascript/api/namespacewindow/)). | Rust for everything native. | Only if the team writes Rust daily |
| Native Swift (AppKit) | `NSPanel` with `.nonactivatingPanel`, `level = .screenSaver`, `ignoresMouseEvents = true`, `collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]`, Core Animation cursor. | Best: ScreenCaptureKit, CGEvent, AVAudioEngine, AVSpeechSynthesizer, all first-party. | Best product; **pick only if one teammate is fluent in Swift** |
| Python / PyObjC | Same AppKit calls as Swift but from Python; animation must be done via Core Animation (not a Python loop). Run loop + asyncio integration is fiddly, few examples. | Same APIs as Swift via `pyobjc-framework-Quartz/Cocoa/ScreenCaptureKit`. | Good for the *brain* process; avoid for the overlay |

Electron overlay, one window per display ([BrowserWindow](https://www.electronjs.org/docs/latest/api/browser-window),
[BaseWindow types](https://www.electronjs.org/docs/latest/api/base-window), [screen](https://www.electronjs.org/docs/latest/api/screen)):

```ts
app.dock.hide();                                   // accessory app: no Dock icon, never steals focus
for (const d of screen.getAllDisplays()) {
  const win = new BrowserWindow({
    ...d.bounds, transparent: true, frame: false, hasShadow: false, focusable: false,
    skipTaskbar: true, roundedCorners: false, type: 'panel', alwaysOnTop: true,
  });
  win.setAlwaysOnTop(true, 'screen-saver');        // above Dock and full-screen apps
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true });  // click-through, still gets mousemove
  win.loadFile('overlay.html');                    // draws cursor at (x - d.bounds.x, y - d.bounds.y)
}
```

Gotchas:
- **Multiple displays**: one window per `Display`; keep every coordinate in *global points* (Electron
  DIP == Quartz global coords, origin top-left of primary) and subtract `display.bounds` only when drawing.
  Listen to `screen` `display-added/removed/metrics-changed` and rebuild windows.
- **Retina**: Electron sizes/positions are in points; `display.scaleFactor` (2 on Retina) converts to the
  device pixels a screenshot is in. Never mix the two (Holo docs call this out explicitly).
- **Full-screen apps**: both `'screen-saver'` level and `visibleOnFullScreen: true` are needed; Electron
  docs say the `panel` type is what lets a window float over full-screened apps. Test with Figma in
  full-screen on day 1.
- **Mission Control / Spaces**: `visibleOnFullScreen` sets `canJoinAllSpaces` + `fullScreenAuxiliary`.
  High-level windows are not shown as tiles, but verify; natively add `.stationary` + `.ignoresCycle`
  ([NSWindow.CollectionBehavior](https://developer.apple.com/documentation/appkit/nswindow/collectionbehavior-swift.struct)).
- **Floating button**: the overlay is click-through, so toggle `setIgnoreMouseEvents(false)` while the
  pointer is over the button (`forward: true` keeps `mousemove` flowing so you can detect hover).
- **Don't capture yourself**: the pink cursor must not appear in screenshots sent to Holo. Electron's
  `setContentProtection(true)` hides the window from legacy capture, but Electron documents that
  ScreenCaptureKit (used by `screencapture` on modern macOS) still captures it — so hide the overlay
  windows for one frame before each shot and show them again.

## 2. Screen capture

- **Permission**: Screen Recording (TCC). Preflight with
  [`CGPreflightScreenCaptureAccess()`](https://developer.apple.com/documentation/coregraphics/cgpreflightscreencaptureaccess())
  and prompt with [`CGRequestScreenCaptureAccess()`](https://developer.apple.com/documentation/coregraphics/cgrequestscreencaptureaccess()).
  It is granted to the *calling binary*: for the Python brain that is the venv's `python` (or Terminal
  when launched from a shell). Electron needs nothing if it never captures.
- **Fastest practical path (Python)**: `screencapture -x -D <n> -t png /tmp/shot.png` (silent, one display,
  ~100–200 ms) or [`mss`](https://pypi.org/project/mss/) for in-memory grabs. The modern first-party API
  is ScreenCaptureKit's
  [`SCScreenshotManager.captureImage`](https://developer.apple.com/documentation/screencapturekit/scscreenshotmanager/captureimage(contentfilter:configuration:completionhandler:))
  (macOS 14+, reachable from Python via `pyobjc-framework-ScreenCaptureKit`); the old
  `CGWindowListCreateImage` is deprecated since macOS 14 — see
  [Capturing screen content in macOS](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos).
- **Electron alternative**: `desktopCapturer.getSources({types:['screen'], thumbnailSize: devicePixelSize})`
  ([docs](https://www.electronjs.org/docs/latest/api/desktop-capturer)) — fine, but then Electron also needs
  Screen Recording and you have two processes with pixel conventions. Keep capture + click in one process.
- **Retina mapping** (screenshot is in device pixels, events are in points):

```python
# Holo returns x,y in [0,1000] normalized to the image you sent (origin top-left).
px = holo_x / 1000 * img_w;  py = holo_y / 1000 * img_h          # pixels in the sent image
scale = img_w / display_width_points                                # == backingScaleFactor if not downscaled
point = (display_origin_x + px / scale, display_origin_y + py / scale)  # global points for CGEvent
```

  Downscaling the PNG before sending (e.g. to ~1440 px wide) cuts upload/latency; it is safe as long as
  `img_w/img_h` are the dimensions of the bytes actually sent
  ([Holo core concepts](https://hub.hcompany.ai/models-api/build-an-agent/core-concepts)).

## 3. Input simulation (DO mode)

- **Permission**: Accessibility, checked with
  [`AXIsProcessTrustedWithOptions`](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions)
  (`kAXTrustedCheckOptionPrompt: true` opens the Settings pane). Again per calling binary.
- **API**: Quartz `CGEvent` — create with
  [`CGEvent(mouseEventSource:mouseType:mouseCursorPosition:mouseButton:)`](https://developer.apple.com/documentation/coregraphics/cgevent/init(mouseeventsource:mousetype:mousecursorposition:mousebutton:)),
  post with [`post(tap: .cghidEventTap)`](https://developer.apple.com/documentation/coregraphics/cgevent/post(tap:)). Keyboard: `CGEventCreateKeyboardEvent`
  + `CGEventKeyboardSetUnicodeString` for typing text. From Python via `pyobjc-framework-Quartz`:

```python
from Quartz import *
def click(x, y):                                   # x,y in global points
    for t, k in ((kCGEventMouseMoved, 0), (kCGEventLeftMouseDown, 1), (kCGEventLeftMouseUp, 1)):
        ev = CGEventCreateMouseEvent(SRC, t, (x, y), kCGMouseButtonLeft)
        CGEventSetIntegerValueField(ev, kCGEventSourceUserData, MAGIC)   # tag our own events
        CGEventPost(kCGHIDEventTap, ev)
```

  `pynput`/`pyautogui` wrap the same calls if you prefer; Electron-side `nut.js` exists but adds a native
  dependency for no benefit once Python already posts events.
- **The real cursor moves**: macOS has one pointer; posted mouse events move it. Avoiding the fight:
  1. In DO mode the user is *watching*: glide the pink cursor first, then warp the real one with
     [`CGWarpMouseCursorPosition`](https://developer.apple.com/documentation/coregraphics/cgwarpmousecursorposition(_:))
     and click; restore the previous position afterwards.
  2. Detect human input and **pause**: a listen-only
     [`CGEvent.tapCreate`](https://developer.apple.com/documentation/coregraphics/cgevent/tapcreate(tap:place:options:eventsofinterest:callback:userinfo:))
     (or [`NSEvent.addGlobalMonitorForEvents`](https://developer.apple.com/documentation/appkit/nsevent/addglobalmonitorforevents(matching:handler:)))
     sees every mouse event; ours carry the `MAGIC` user-data tag, anything else is the human → stop DO.
  3. Where possible click without the pointer: `AXUIElementCopyElementAtPosition` → `AXUIElementPerformAction(kAXPress)`.
     Works on native controls, not on canvases (Figma, Electron apps), so treat as an optimisation.
- GUIDE mode uses the same event tap to notice the user's click and advance to the next step.
- `Esc` (global) = kill switch that cancels the current DO run.

## 4. Global hotkey + push-to-talk

- **Hotkey**: Electron [`globalShortcut`](https://www.electronjs.org/docs/latest/api/global-shortcut) fires on
  *press only*; there is no key-up event. Tauri's
  [global-shortcut plugin](https://v2.tauri.app/plugin/global-shortcut/) and native Carbon
  `RegisterEventHotKey` (wrapped by [KeyboardShortcuts](https://github.com/sindresorhus/KeyboardShortcuts) / [HotKey](https://github.com/soffes/HotKey))
  do deliver pressed/released. [`uiohook-napi`](https://github.com/SnosMe/uiohook-napi) gives key-up in
  Electron but needs Accessibility.
- **Recommendation**: toggle-to-talk. Press `⌥Space` (or the floating button) → start streaming; stop on a
  second press *or* automatically when Gladia emits `speech_end` / a final transcript after
  `endpointing` silence. No key-up needed, feels like PTT.
- **Mic capture**: in the Python brain with [`sounddevice`](https://pypi.org/project/sounddevice/)
  (`InputStream(samplerate=16000, channels=1, dtype='int16', blocksize=1600)` → 100 ms PCM frames).
  Microphone TCC prompt appears on first open; for a bundled app add
  [`NSMicrophoneUsageDescription`](https://developer.apple.com/documentation/bundleresources/information-property-list/nsmicrophoneusagedescription).
  (Electron's `getUserMedia` also works, but then audio has to hop to Python anyway.)

## 5. Gladia real-time STT, and TTS

Flow ([quickstart](https://docs.gladia.io/chapters/live-stt/quickstart), [WebSocket reference](https://docs.gladia.io/api-reference/v2/live/websocket)):

1. `POST https://api.gladia.io/v2/live` (header `x-gladia-key`) with the audio format and options →
   `{ "id", "url": "wss://api.gladia.io/v2/live?token=..." }`.
2. Open the WebSocket; send PCM as **binary frames** (or `{"type":"audio_chunk","data":{"chunk":"<base64>"}}`).
3. Receive `transcript` messages (`data.is_final`, `data.utterance.text`, `data.utterance.language`),
   plus `speech_start` / `speech_end` if enabled. Partials for the same utterance share `data.id`.
4. Send `{"type":"stop_recording"}`; Gladia flushes, then closes with code 1000. Sessions cap at 3 h.

```python
cfg = {"encoding": "wav/pcm", "sample_rate": 16000, "bit_depth": 16, "channels": 1,
       "language_config": {"languages": ["fr", "en"], "code_switching": True},
       "endpointing": 0.1, "maximum_duration_without_endpointing": 15,
       "messages_config": {"receive_partial_transcripts": True, "receive_speech_events": True}}
```

- **Languages**: `language_config.languages: ["fr","en"]` + `code_switching: true` detects the language per
  utterance and returns it with each transcript; docs recommend a *small* expected-language list
  ([code switching](https://docs.gladia.io/chapters/language/code-switching)).
- **Latency knobs**: `endpointing` 0.05–0.1 s, `maximum_duration_without_endpointing` 15, partials on —
  Gladia's own [voice-agent preset](https://docs.gladia.io/chapters/live-stt/recommended-parameters).
  Partials come from a smaller/faster model than finals ([partial transcripts](https://docs.gladia.io/chapters/live-stt/features/partial-transcripts)).
  Gladia publishes no streaming-latency number, so measure end-of-speech → final on the venue Wi-Fi.
  Live supports model `solaria-1` only; supported sample rates are 8/16/32/44.1/48 kHz.
- SDKs: `pip install gladiaio-sdk` / `npm i @gladiaio/sdk` wrap steps 1–4
  ([samples](https://github.com/gladiaio/gladia-samples)).
- **TTS**: Gladia is STT + audio intelligence only — the docs index has no text-to-speech product.
  Options on macOS, in order for a hackathon:
  1. System TTS, offline and instant: `AVSpeechSynthesizer`
     ([docs](https://developer.apple.com/documentation/avfaudio/avspeechsynthesizer)) or the
     [`say`](https://ss64.com/mac/say.html) CLI (`say -v Thomas "Cliquez ici"`, `say -v Samantha "Click here"`).
     Download "Enhanced"/"Premium" voices in System Settings → Accessibility → Spoken Content.
     Electron's `speechSynthesis` uses the same voices.
  2. Cloud, streamed, ~100 ms model latency: [ElevenLabs Flash v2.5](https://elevenlabs.io/docs/overview/models)
     (32 languages incl. FR) or [Cartesia Sonic](https://docs.cartesia.ai/get-started/overview) (~90 ms TTFB).
     Keep system TTS as the fallback when the network is slow.

## 6. Proposed architecture

```
┌──────────────── Electron (TypeScript) ─────────────────┐   localhost WS (JSON)   ┌──────────── Python 3.11 brain ────────────┐
│ overlay windows (1/display): pink cursor, labels,     │ ◄──────────────────────► │ state machine: IDLE→LISTEN→PLAN→STEP…     │
│ floating button, hotkey (globalShortcut), TTS via     │  {cursor,x,y,label}      │ mic (sounddevice) → Gladia WS             │
│ speechSynthesis (or Python calls `say`)               │  {speak,text} {mode}     │ Linkup search → step plan (LLM)           │
│ NO permissions, NO API keys                           │  {hotkey} {user_clicked} │ screenshot → Holo localize → point        │
└────────────────────────────────────────────────────────┘                          │ CGEvent click/type, event tap (pause)     │
                                                                                    │ .env keys: HAI, GLADIA, LINKUP, STRIPE    │
                                                                                    └───────────────────────────────────────────┘
```

- **Why this split**: the repo is Python-first and the API SDKs (`openai` for Holo, `gladiaio-sdk`,
  `linkup-sdk`) are Python; Electron is the fastest way to draw a smooth cursor across displays. Capture
  and input live in the same process so pixel units never cross a boundary. Two teammates can work in
  parallel against a 6-message JSON contract.
- **Holo call** ([element localization](https://hub.hcompany.ai/models-api/element-localization),
  [models](https://hub.hcompany.ai/models-api/models)): OpenAI client with
  `base_url="https://api.hcompany.ai/v1/"`, `api_key=HAI_API_KEY`; model `holo4-35b-a3b` (fastest paid)
  or `holo3-1-35b-a3b` (free) — localization is supported on all models except `holo3-122b-a10b`;
  `temperature=0`, thinking off (`extra_body={"chat_template_kwargs": {"enable_thinking": False}}` or
  `reasoning_effort="none"`), `structured_outputs` with `x`,`y` integers in `[0,1000]`, image as a
  base64 data URI. Max 5 images per request; keep ≤3 screenshots in any agent-loop context.
- **Planning**: the user asks "how do I export as PNG in Figma" → Linkup
  ([search endpoint](https://docs.linkup.so/pages/documentation/api-reference/endpoint/post-search)) for the
  steps → an LLM turns them into an ordered list of element descriptions → each step: screenshot →
  Holo → pink cursor → (GUIDE: wait for user click | DO: CGEvent) → re-screenshot to verify.
- **Stripe**: not a desktop concern — open a [Payment Link / Checkout](https://docs.stripe.com/payment-links)
  URL in the browser from the Python side; keys stay in `.env`.
- Native Swift could replace Electron later with the same WS contract if the overlay needs polish.

### Top 5 technical risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Off-target clicks** (Retina px/pt mix, resized screenshot, wrong display offset) | One pixel-unit pipeline in Python; always scale with the sent image's dimensions; debug mode draws Holo's point on the screenshot; day-1 test on 2 displays |
| 2 | **Latency chain** (speech → plan → Holo → draw) feels sluggish | Partials + `endpointing` 0.1; thinking off + fast Holo model; downscale PNG; pre-fetch Linkup steps while the user is still talking; speak "Looking…" immediately |
| 3 | **TCC permissions** (Screen Recording, Accessibility, Mic) are per-binary and reset when the binary changes | Fixed venv `python` path; `scripts/check_perms.py` calling `CGPreflightScreenCaptureAccess` / `AXIsProcessTrustedWithOptions`; grant on the demo Mac before the pitch, never rebuild it after |
| 4 | **Overlay invisible** over full-screen Figma, on a second display, or after Space switch | `screen-saver` level + `visibleOnFullScreen` + `type:'panel'`; rebuild windows on display events; test in full-screen on day 1; fallback: non-full-screen window demo |
| 5 | **DO mode runs away** or fights the user | Human-input event tap pauses instantly; global `Esc` kill switch; step limit + screenshot verification after each action; confirm before anything destructive |
