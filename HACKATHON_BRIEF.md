# H Company × 42AI — Computer Use Agents Hackathon

- **When:** Sat Nov 7 (09:00) – Sun Nov 8, 2026 · La Maison by Motier Ventures, Paris
- **Teams:** 1–4 people · **Prize pool:** €13,000 cash
- Event page: https://builderbase.com/event/h-company-42ai-computer-use-agents-hackathon
- Dashboard: https://builderbase.com/track-dashboard/h-company-42ai-computer-use-agents-hackathon
- Discord: https://discord.gg/WjmTcMW9e

## Challenge
Build an agent that uses real software: it navigates websites, desktop apps and software
interfaces to complete a meaningful real-world task. Pick a use case, build it, show it working.
The demo must clearly show **the problem, the actions the agent takes, and the result**.
Built on H Company's Agents API and models.

## Prizes
| Prize | Amount |
|---|---|
| 1st / 2nd / 3rd | €5,000 / €3,000 / €2,000 |
| Best use of Gladia | €1,000 |
| Best use of Devin (Cognition) | €1,000 |
| Best LinkedIn post / Best X post | €500 each |
| Top 3 teams | 1 free month of Morning Nomade coworking each |

## Key deadlines (Sun Nov 8)
- **14:00 project submission deadline**
- 14:30 first judging round · 15:45 final pitches · 17:45 winners
- Sat: venue closes to new entry at 21:00; reopens Sun 08:00

## Credits (redeem from the BuilderBase resources page)
- **H Company:** €100 API code. Sign up at https://platform.hcompany.ai/auth/signup, create an API key,
  then Billing & Subscription → Inference credits → Redeem a code
  (https://platform.hcompany.ai/settings/billing). Stripe checkout may show $0.00, then check the wallet.
- **Gladia:** 1K API credits + docs (speech-to-text)
- **Linkup:** $45 API credits + docs (web search API)
- **Stripe:** participation gift credits

## H Agents API quickstart
Docs: https://hub.hcompany.ai/agents-api/introduction · Models: https://hub.hcompany.ai/models-api/introduction

```bash
export HAI_API_KEY="hk-..."        # from platform.hcompany.ai/settings/api-keys
pip install "hai-agents[cli]"
holo login
holo "Open Hacker News and list the top 3 stories with their URLs."
```

```python
result = client.run_session(agent="h/web-surfer-flash", messages="...")
print(result.answer)
```

- Pre-built agents: `h/web-surfer-flash` (fast), `h/web-surfer-pro`
- Runs on a cloud browser, your own browser, or your desktop
- Features: credential/2FA vault, structured output (Pydantic/Zod/JSON Schema),
  live steering (`session.send_message`), subagents running in parallel
