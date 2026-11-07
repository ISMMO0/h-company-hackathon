# Agent instructions

Context for coding agents (Devin, Claude Code) working in this repo.

## Project
Entry for the H Company × 42AI Computer Use Agents Hackathon (Paris, Nov 7–8, 2026).
Goal: an agent that operates real software (websites, desktop apps) to complete a meaningful
real-world task. The demo must show the problem, the actions the agent takes, and the result.
Full brief: [HACKATHON_BRIEF.md](HACKATHON_BRIEF.md). Hard deadline: Sun Nov 8, 14:00.

## Stack
- Python 3.11+
- H Company Agents API via `hai-agents` (`pip install "hai-agents[cli]"`).
  Docs: https://hub.hcompany.ai/agents-api/introduction
  Pre-built agents: `h/web-surfer-flash` (fast), `h/web-surfer-pro`.
- Gladia (speech-to-text): https://docs.gladia.io
- Linkup (web search API): https://docs.linkup.so

## Rules
- API keys live in `.env` (see `.env.example`). Never commit `.env`, never hardcode keys,
  never print keys in logs.
- Keep changes small and scoped to the task. One feature per PR.
- Every PR: short description of what changed and how to run/test it.
- Do not add AI attribution (no "Co-Authored-By" or "Generated with" lines) to commits or PRs.
- Prefer simple, readable code over abstractions; this is a 2-day hackathon.
