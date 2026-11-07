import json
from unittest.mock import MagicMock

import pytest

from brain import billing


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "PATH", tmp_path / "data" / "billing.json")
    monkeypatch.setattr(billing, "_today", lambda: "2026-11-07")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    monkeypatch.setenv("SHADOW_FREE_TASKS", "2")


@pytest.fixture
def client(monkeypatch):
    c = MagicMock()
    monkeypatch.setattr(billing.stripe, "StripeClient", lambda key: c)
    return c


def test_free_quota_counts_down_then_blocks():
    assert not billing.is_pro()
    assert billing.tasks_left() == 2
    assert billing.allow_task() == (True, "Free: 1 tasks left today")
    assert billing.allow_task() == (True, "Free: 0 tasks left today")
    ok, hint = billing.allow_task()
    assert not ok
    assert "Upgrade to Shadow Pro" in hint and "127.0.0.1:8765" in hint
    assert billing.tasks_left() == 0


def test_quota_resets_each_day(monkeypatch):
    billing.count_task()
    billing.count_task()
    assert billing.tasks_left() == 0
    monkeypatch.setattr(billing, "_today", lambda: "2026-11-08")
    assert billing.tasks_left() == 2


def test_pro_is_unlimited():
    billing._save({"pro": True})
    for _ in range(5):
        assert billing.allow_task() == (True, "Pro")
    assert billing.is_pro()


def test_refuses_non_test_key(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_123")
    with pytest.raises(RuntimeError, match="sk_test_"):
        billing.create_checkout()
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    with pytest.raises(RuntimeError):
        billing.verify("cs_test_1")


def test_checkout_with_env_price(client, monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_env")
    client.v1.checkout.sessions.create.return_value = MagicMock(url="https://checkout.stripe.com/x")
    assert billing.create_checkout("http://127.0.0.1:8765") == "https://checkout.stripe.com/x"
    params = client.v1.checkout.sessions.create.call_args.kwargs["params"]
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_env", "quantity": 1}]
    assert params["success_url"] == (
        "http://127.0.0.1:8765/billing/success?session_id={CHECKOUT_SESSION_ID}")
    assert params["cancel_url"] == "http://127.0.0.1:8765/"
    client.v1.products.create.assert_not_called()


def test_checkout_creates_then_reuses_price(client):
    client.v1.prices.list.return_value = MagicMock(data=[])
    client.v1.products.create.return_value = MagicMock(id="prod_1")
    client.v1.prices.create.return_value = MagicMock(id="price_new")
    client.v1.checkout.sessions.create.return_value = MagicMock(url="https://checkout.stripe.com/y")

    billing.create_checkout()
    client.v1.products.create.assert_called_once_with(params={"name": "Shadow Pro"})
    price_params = client.v1.prices.create.call_args.kwargs["params"]
    assert price_params["product"] == "prod_1"
    assert price_params["unit_amount"] == 900
    assert price_params["currency"] == "eur"
    assert price_params["recurring"] == {"interval": "month"}
    assert json.loads(billing.PATH.read_text())["price_id"] == "price_new"

    billing.create_checkout()
    assert client.v1.products.create.call_count == 1
    assert client.v1.prices.create.call_count == 1
    line_items = client.v1.checkout.sessions.create.call_args.kwargs["params"]["line_items"]
    assert line_items == [{"price": "price_new", "quantity": 1}]


def test_checkout_reuses_existing_price(client):
    client.v1.prices.list.return_value = MagicMock(data=[MagicMock(id="price_old")])
    client.v1.checkout.sessions.create.return_value = MagicMock(url="https://checkout.stripe.com/z")
    billing.create_checkout()
    client.v1.products.create.assert_not_called()
    assert json.loads(billing.PATH.read_text())["price_id"] == "price_old"


def test_verify_marks_pro_only_when_paid(client):
    client.v1.checkout.sessions.retrieve.return_value = MagicMock(
        payment_status="unpaid", status="open")
    assert not billing.verify("cs_test_1")
    assert not billing.is_pro()

    client.v1.checkout.sessions.retrieve.return_value = MagicMock(
        payment_status="paid", status="complete")
    assert billing.verify("cs_test_1")
    client.v1.checkout.sessions.retrieve.assert_called_with("cs_test_1")
    assert billing.is_pro()
    assert billing.allow_task() == (True, "Pro")
