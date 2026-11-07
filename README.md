# H Company × 42AI Computer Use Agents Hackathon

Project for the H Company × 42AI Computer Use Agents Hackathon (Paris, Nov 7–8, 2026).
See [HACKATHON_BRIEF.md](HACKATHON_BRIEF.md) for the challenge, prizes and deadlines.

## Setup

```bash
cp .env.example .env   # then add your API keys
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
(cd overlay && npm install)
```

## Run

```bash
./start.sh
```

This starts the brain and the pink-cursor overlay and opens http://127.0.0.1:8765.
Type a task, pick **Guide me** or **Do it**, press **Go**, then switch to your app within 3 s.
macOS will ask for Screen Recording (and Accessibility for Do it) for the app running it.
