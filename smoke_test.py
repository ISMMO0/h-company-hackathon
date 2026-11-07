"""Check that each API key in .env works.

    python smoke_test.py          # cheap checks only (no agent run)
    python smoke_test.py --agent  # also runs one short H web agent session
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()


def check_h(run_agent: bool) -> str:
    from hai_agents import Client

    client = Client(api_key=os.environ["HAI_API_KEY"])
    quota = client.quota.get_token_quota()
    msg = f"key OK, quota: {quota}"
    if run_agent:
        result = client.run_session(
            agent="h/web-surfer-flash",
            messages="Open https://example.com and tell me the page's main heading.",
        )
        msg += f"\n    agent answer: {result.answer}"
    return msg


def check_linkup() -> str:
    r = requests.post(
        "https://api.linkup.so/v1/search",
        headers={"Authorization": f"Bearer {os.environ['LINKUP_API_KEY']}"},
        json={"q": "H Company Holo model", "depth": "standard", "outputType": "searchResults"},
        timeout=60,
    )
    r.raise_for_status()
    return f"key OK, {len(r.json().get('results', []))} results"


def check_gladia() -> str:
    r = requests.get(
        "https://api.gladia.io/v2/pre-recorded",
        headers={"x-gladia-key": os.environ["GLADIA_API_KEY"]},
        params={"limit": 1},
        timeout=30,
    )
    if r.status_code in (401, 403):
        r.raise_for_status()
    return f"key OK (HTTP {r.status_code})"


def main() -> int:
    checks = {
        "H Agents API": ("HAI_API_KEY", lambda: check_h("--agent" in sys.argv)),
        "Linkup": ("LINKUP_API_KEY", check_linkup),
        "Gladia": ("GLADIA_API_KEY", check_gladia),
    }
    failed = 0
    for name, (env_var, fn) in checks.items():
        if not os.environ.get(env_var):
            print(f"[SKIP] {name}: {env_var} is empty in .env")
            continue
        try:
            print(f"[ OK ] {name}: {fn()}")
        except Exception as e:  # report and keep going
            failed += 1
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
