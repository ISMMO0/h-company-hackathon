# Deploy plan: the jury installs and uses Shadow Cursor

Status: **draft for Devin's review, nothing deployed yet** (team lead: "don't deploy yet").

## The constraint that changes everything
The jury will **use our app themselves**, on their own Mac. So it's not enough to run it on ours:
1. They must be able to **download and open it** in a couple of minutes, with no Python, no Terminal, no keys.
2. **Our API keys can never ship inside the app** (anyone could extract them).
3. It must work on **their** Mac: Apple Silicon or Intel, recent macOS, their permissions.

## What the juror does (target: under 3 minutes)
1. Opens the landing page (Vercel): "Activate your Shadow Cursor" → **Download for Mac** (.dmg).
2. Drags Shadow Cursor to Applications, opens it (right-click → Open the first time, see Risks).
3. A small **onboarding** window checks the 3 macOS permissions one by one (Screen Recording,
   Accessibility, Microphone), each with an "Open Settings" button and a ✓ when granted, then
   "Restart Shadow Cursor" if macOS requires it (Screen Recording does).
4. The pink cursor appears: "Press ⌃⌥Space and say what you want to do."

## Architecture
```
 Juror's Mac                                   Cloud
 ┌───────────────────────────────┐            ┌────────────────────────────────────┐
 │ Shadow Cursor.app (Electron)  │   HTTPS    │ Vercel (region cdg1, Paris)         │
 │  ├ overlay (pink cursor)      │ ─────────► │  /api/register   device token      │
 │  └ brain (Python, bundled)    │            │  /api/holo       → H Company API    │
 │     screen, mouse, mic, TTS   │            │  /api/llm        → OpenAI (router)  │
 │     only a device token       │            │  /api/tts        → OpenAI TTS       │
 └───────────────────────────────┘            │  /api/linkup     → Linkup           │
          │ WebSocket (audio)                 │  /api/gladia     → Gladia session   │
          └──────────► Gladia (temporary URL) │  /api/checkout, /api/stripe-webhook│
                                              │  landing page                      │
                                              └──────────────┬─────────────────────┘
                                                             │
                                              Aiven Postgres (shadow-cursor-db)
                                              devices, usage per day, Pro status
```
- **Proxy**: the brain gets a `SHADOW_API` base URL; each client (`planner`, `router`, `tts`,
  `linkup`, `voice`) calls our Vercel routes instead of the providers. Same request shapes
  (OpenAI-compatible for Holo and OpenAI), so the change in the brain is mostly base URLs + header.
- **Gladia**: the WebSocket audio stream does not go through Vercel. `/api/gladia` does the
  `POST /v2/live` with our key and returns the session's WebSocket URL (it carries its own temporary
  token); the brain streams audio straight to Gladia.
- **Device token**: first launch calls `/api/register` → random token stored in the macOS Keychain
  (or app data). Every proxy call sends it; the server counts usage per device per day in Postgres.
- **Quota & Stripe**: free = N tasks/day (server-side now, not local); Stripe Checkout (test mode)
  from the app or the landing page; the webhook marks the device Pro in Postgres.
- **Abuse guard** (jury only, but public URL): per-device and global daily caps, so a leaked
  token can't burn our credits.

## Packaging the Mac app
- **Electron** stays the shell (electron-builder → `.dmg`).
- **Brain**: frozen with **PyInstaller** (one-folder) and shipped inside the app's Resources;
  Electron starts it as a child process on launch and stops it on quit. Python 3.12 for the build
  (PyInstaller + pyobjc are safest there; we develop on 3.14).
- Permissions are granted to **Shadow Cursor.app** (the parent), which covers the bundled brain.
- Build **arm64 + x64** (or universal) so Intel Macs work too.
- The local control page (127.0.0.1:8765) stays, for us, hidden from jurors.

## Risks
| Risk | Mitigation |
|---|---|
| **Gatekeeper**: unsigned app → "cannot be opened" | Apple Developer ID + notarization if we have one ($99, takes time). Otherwise a clear "right-click → Open" step on the landing page and in the README |
| PyInstaller with pyobjc / Quartz / PIL | Build it first, today, as a spike; fall back to a script installer (`curl … \| bash` that creates a venv) if it fails |
| Proxy adds latency | Vercel region cdg1 (Paris), keep-alive, no extra work in the routes |
| Vercel function limits (time, body size) | Holo calls can take 12 s: set `maxDuration` ≥ 30 s; screenshots are ~100–300 KB, under the 4.5 MB body limit |
| Jurors on old macOS / Intel | State the minimum macOS on the page; build x64 too |
| Permissions confuse jurors | Onboarding window with ✓ per permission; 20-second screen recording on the landing page |
| Venue Wi-Fi | Everything is online anyway; hotspot backup |

## Fallbacks for the judging
1. Our demo Mac at the table, fully set up (jurors can try it there).
2. The recorded demo video.

## Work split (proposal)
- **Devin**: Vercel project (landing page + API routes + Stripe), Postgres schema on Aiven,
  electron-builder + PyInstaller packaging, onboarding window.
- **Claude**: brain changes (proxy base URLs, device token, quota errors), Gladia session via the
  proxy, end-to-end test of the packaged app.
- **Team lead**: Apple Developer account question, landing page wording, final test on a second Mac.

## Open questions
1. Do jurors install on their own Macs, or try it on ours? (ask the organizers: it changes the
   priority of packaging vs. polish)
2. Do we have an Apple Developer account for signing/notarization?
3. Free quota for jurors: unlimited during judging, or N tasks/day?
4. Minimum macOS version to support?

## Not now
Deploying anything (team lead's call). Windows/Linux. Auto-update.
