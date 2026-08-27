import base64
import hashlib
import hmac
import json
import os

import pytest

os.environ.setdefault("AIRTABLE_TOKEN", "test-token")
os.environ.setdefault("SHOPIFY_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("AIRTABLE_BASE_ID", "appExampleBase")
os.environ.setdefault("AIRTABLE_ORDERS_TABLE", "tblExampleOrders")
os.environ.setdefault("SHOPIFY_STORE_DOMAIN", "example-store.myshopify.com")
os.environ.setdefault("SHOPIFY_FLOW_TOKEN", "test-flow-token")

import main


@pytest.fixture()
def sample_order():
    return {
        "id": 1234567890,
        "email": "buyer@example.com",
        "created_at": "2026-01-15T10:00:00-05:00",
        "total_price": "149.00",
        "current_total_price": "149.00",
        "total_discounts": "10.00",
        "currency": "USD",
        "financial_status": "paid",
        "fulfillment_status": None,
        "cancelled_at": None,
        "customer": {"id": 987654321},
        "shipping_address": {"country_code": "US"},
        "discount_codes": [{"code": "WELCOME10"}],
        "source_name": "web",
        "landing_site": "/products/s1?utm_source=creator&utm_campaign=launch&gclid=abc123",
        "referring_site": "https://www.google.com/",
        "line_items": [
            {
                "title": "Example Studio Kit",
                "variant_title": "Standard",
                "sku": "EXAMPLE-STANDARD",
                "quantity": 1,
            }
        ],
        "refunds": [],
    }


def test_order_mapping(sample_order):
    fields = main.order_to_airtable_fields(sample_order)
    assert fields["Order ID"] == "1234567890"
    assert fields["Customer Email"] == "buyer@example.com"
    assert fields["Main Product"] == "Example Studio Kit"
    assert fields["SKU List"] == "EXAMPLE-STANDARD"
    assert fields["Order Revenue"] == 149.00
    assert fields["Net Revenue"] == 149.00
    assert fields["UTM Source"] == "creator"
    assert fields["Click ID"] == "abc123"


def test_refund_mapping(sample_order):
    sample_order["refunds"] = [
        {"transactions": [{"kind": "refund", "amount": "25.50"}]}
    ]
    fields = main.order_to_airtable_fields(sample_order)
    assert fields["Refund Amount"] == 25.50
    assert fields["Net Revenue"] == 123.50
    assert fields["Refunded"] is True


def test_webhook_hmac(sample_order):
    raw = json.dumps(sample_order).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(b"test-secret", raw, hashlib.sha256).digest()
    ).decode("ascii")
    assert main._verify_webhook(raw, signature)
    assert not main._verify_webhook(raw, "wrong")


def test_webhook_upserts(monkeypatch, sample_order):
    monkeypatch.setattr(
        main,
        "upsert_airtable_order",
        lambda payload: {"action": "created", "record_id": "rec123", "order_id": str(payload["id"])},
    )
    raw = json.dumps(sample_order).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(b"test-secret", raw, hashlib.sha256).digest()
    ).decode("ascii")
    client = main.app.test_client()
    response = client.post(
        "/webhooks/shopify",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Hmac-Sha256": signature,
            "X-Shopify-Shop-Domain": "example-store.myshopify.com",
            "X-Shopify-Topic": "orders/create",
        },
    )
    assert response.status_code == 200
    assert response.json["status"] == "SYNCED"


def test_shopify_flow_upserts(monkeypatch, sample_order):
    monkeypatch.setattr(
        main,
        "upsert_airtable_order",
        lambda payload: {"action": "updated", "record_id": "rec123", "order_id": str(payload["id"])},
    )
    client = main.app.test_client()
    response = client.post(
        "/flow/shopify",
        json=sample_order,
        headers={"X-Shopify-Flow-Token": "test-flow-token"},
    )
    assert response.status_code == 200
    assert response.json["status"] == "SYNCED"
    assert response.json["source"] == "shopify_flow"


def test_shopify_flow_fetches_full_order_from_order_id(monkeypatch, sample_order):
    fetched = []

    def fake_fetch(order_id):
        fetched.append(order_id)
        return sample_order

    monkeypatch.setattr(main, "fetch_shopify_order", fake_fetch)
    monkeypatch.setattr(
        main,
        "upsert_airtable_order",
        lambda payload: {
            "action": "created",
            "record_id": "rec123",
            "order_id": str(payload["id"]),
        },
    )
    client = main.app.test_client()
    response = client.post(
        "/flow/shopify",
        json={"order_id": "gid://shopify/Order/1234567890"},
        headers={"X-Shopify-Flow-Token": "test-flow-token"},
    )
    assert response.status_code == 200
    assert fetched == ["gid://shopify/Order/1234567890"]
    assert response.json["order_id"] == "1234567890"


def test_fetch_shopify_order_rejects_invalid_id():
    with pytest.raises(ValueError, match="numeric legacy ID"):
        main.fetch_shopify_order("not-an-order")


def test_shopify_flow_rejects_bad_token(sample_order):
    client = main.app.test_client()
    response = client.post(
        "/flow/shopify",
        json=sample_order,
        headers={"X-Shopify-Flow-Token": "wrong"},
    )
    assert response.status_code == 401
