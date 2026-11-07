"""Shadow Pro billing: a free tier of N tasks per day, then Stripe Checkout (test mode only).

State lives in data/billing.json: {"pro": bool, "day": "YYYY-MM-DD", "used": int, "price_id": str}.
The agent calls allow_task() before each task; the server exposes the checkout and the callback.
"""

import datetime
import json
import os
from pathlib import Path

import stripe

PATH = Path("data/billing.json")
PRODUCT_NAME = "Shadow Pro"
LOOKUP_KEY = "shadow_pro_monthly"
PRICE_EUR_CENTS = 900
ERRORS = (RuntimeError, stripe.StripeError)  # what create_checkout / verify can raise


def free_tasks() -> int:
    # 20 so rehearsals don't hit the wall; set SHADOW_FREE_TASKS=2 to show the paywall in the demo.
    return int(os.environ.get("SHADOW_FREE_TASKS", "20"))


# -- quota ------------------------------------------------------------------------------------


def is_pro() -> bool:
    return bool(_load().get("pro"))


def tasks_left() -> int:
    return max(0, free_tasks() - _load()["used"])


def count_task() -> None:
    state = _load()
    state["used"] += 1
    _save(state)


def allow_task() -> tuple[bool, str]:
    """Counts one task against today's quota. (False, hint) when the free tier is used up."""
    if is_pro():
        return True, "Pro"
    left = tasks_left()
    if left <= 0:
        return False, (f"Free quota used ({free_tasks()} tasks a day). "
                       "Upgrade to Shadow Pro on http://127.0.0.1:8765")
    count_task()
    return True, f"Free: {left - 1} tasks left today"


# -- Stripe (test mode only) ------------------------------------------------------------------


def create_checkout(base_url: str = "http://127.0.0.1:8765") -> str:
    """Creates a subscription Checkout Session for Shadow Pro and returns its URL."""
    client = _client()
    session = client.v1.checkout.sessions.create(params={
        "mode": "subscription",
        "line_items": [{"price": _price_id(client), "quantity": 1}],
        "success_url": f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base_url}/",
    })
    return session.url


def verify(session_id: str) -> bool:
    """Retrieves the Checkout Session; marks Pro when it is paid or complete."""
    session = _client().v1.checkout.sessions.retrieve(session_id)
    if session.payment_status != "paid" and session.status != "complete":
        return False
    state = _load()
    state["pro"] = True
    _save(state)
    return True


def _client() -> stripe.StripeClient:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key.startswith("sk_test_"):
        raise RuntimeError("STRIPE_SECRET_KEY must be a Stripe test key (sk_test_...)")
    return stripe.StripeClient(key)


def _price_id(client: stripe.StripeClient) -> str:
    """STRIPE_PRICE_ID if set, else the cached or existing 9 EUR/month price, else a new one."""
    if os.environ.get("STRIPE_PRICE_ID"):
        return os.environ["STRIPE_PRICE_ID"]
    state = _load()
    if state.get("price_id"):
        return state["price_id"]
    existing = client.v1.prices.list(params={"lookup_keys": [LOOKUP_KEY], "active": True})
    if existing.data:
        price = existing.data[0]
    else:
        product = client.v1.products.create(params={"name": PRODUCT_NAME})
        price = client.v1.prices.create(params={
            "product": product.id,
            "unit_amount": PRICE_EUR_CENTS,
            "currency": "eur",
            "recurring": {"interval": "month"},
            "lookup_key": LOOKUP_KEY,
        })
    state["price_id"] = price.id
    _save(state)
    return price.id


# -- state ------------------------------------------------------------------------------------


def _today() -> str:
    return datetime.date.today().isoformat()


def _load() -> dict:
    try:
        state = json.loads(PATH.read_text())
    except (OSError, ValueError):
        state = {}
    if state.get("day") != _today():
        state["day"], state["used"] = _today(), 0
    state.setdefault("pro", False)
    return state


def _save(state: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(state, indent=1))
