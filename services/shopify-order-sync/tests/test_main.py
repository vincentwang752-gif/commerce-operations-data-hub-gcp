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
os.environ.setdefault("AIRTABLE_CUSTOMERS_TABLE", "tblExampleCustomers")
os.environ.setdefault("AIRTABLE_CREATORS_TABLE", "tblExampleCreators")
os.environ.setdefault("AIRTABLE_TOUCHPOINTS_TABLE", "tblExampleTouchpoints")
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
    assert fields["订单 ID"] == "1234567890"
    assert fields["客户邮箱"] == "buyer@example.com"
    assert fields["主产品"] == "Example Studio Kit"
    assert fields["SKU 列表"] == "EXAMPLE-STANDARD"
    assert fields["订单收入"] == 149.00
    assert fields["净收入"] == 149.00
    assert fields["UTM 来源"] == "creator"
    assert fields["点击 ID"] == "abc123"


def test_refund_mapping(sample_order):
    sample_order["refunds"] = [
        {"transactions": [{"kind": "refund", "amount": "25.50"}]}
    ]
    fields = main.order_to_airtable_fields(sample_order)
    assert fields["退款金额"] == 25.50
    assert fields["净收入"] == 123.50
    assert fields["是否退货"] is True


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.headers = {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_order_upsert_links_customer(monkeypatch, sample_order):
    calls = []
    monkeypatch.setattr(main, "upsert_airtable_customer", lambda order: "recCustomer")
    monkeypatch.setattr(main, "_find_airtable_order", lambda order_id: "recOrder")
    monkeypatch.setattr(main, "refresh_customer_aggregates", lambda *args: None)
    monkeypatch.setattr(main, "link_pending_collabs_touchpoints", lambda *args: 0)

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse({"id": "recOrder"})

    monkeypatch.setattr(main, "_airtable_request", fake_request)
    result = main.upsert_airtable_order(sample_order)

    assert result["customer_record_id"] == "recCustomer"
    assert calls[0][2]["json"]["fields"]["客户"] == ["recCustomer"]


def test_guest_customer_uses_email_identity(sample_order):
    sample_order["customer"] = {}
    identity = main._customer_identity(sample_order)
    assert identity["customer_id"] == ""
    assert identity["unique_key"] == "email:buyer@example.com"


def test_customer_match_formula_uses_order_email_field():
    formula = main._customer_match_formula("123", "buyer@example.com", "客户邮箱")
    assert "{Shopify 客户 ID}" in formula
    assert "{客户邮箱}" in formula


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


def test_collabs_creator_mapping_accepts_nested_payload():
    creator = main.collabs_creator_from_payload(
        {
            "creator": {
                "id": "gid://shopify/CollabsCreator/7788",
                "displayName": "Creator One",
                "email": "CREATOR@example.com",
                "handle": "@creatorone",
                "profileUrl": "https://instagram.com/creatorone",
            }
        }
    )
    assert creator["id"] == "7788"
    assert creator["email"] == "creator@example.com"
    assert creator["handle"] == "creatorone"
    assert creator["unique_key"] == "shopify-collabs:7788"


def test_collabs_attribution_mapping():
    result = main.collabs_attribution_from_payload(
        {
            "event_id": "evt-001",
            "event_time": "2026-08-28T09:00:00Z",
            "order": {
                "id": "gid://shopify/Order/1234567890",
                "totalPrice": "314.10",
            },
            "creator": {"id": "creator-88", "name": "Creator 88"},
            "commission_amount": "31.41",
            "discount_code": "CREATOR88",
        }
    )
    assert result["order_id"] == "1234567890"
    assert result["revenue"] == main.Decimal("314.10")
    assert result["commission"] == main.Decimal("31.41")
    assert result["touchpoint_key"] == "shopify-collabs:1234567890:creator-88:evt-001"


def test_collabs_attribution_accepts_flow_order_fields_and_discount_list():
    result = main.collabs_attribution_from_payload(
        {
            "event_time": "2026-08-28T09:00:00Z",
            "order_id": "1234567890",
            "attributed_revenue": "314.10",
            "discount_codes": ["CREATOR88", "FREE-SHIPPING"],
            "creator_id": "88",
            "creator_email": "creator@example.com",
        }
    )
    assert result["order_id"] == "1234567890"
    assert result["revenue"] == main.Decimal("314.10")
    assert result["coupon"] == "CREATOR88, FREE-SHIPPING"
    assert result["touchpoint_key"] == "shopify-collabs:1234567890:88"


def test_collabs_creator_flow_upserts(monkeypatch):
    monkeypatch.setattr(
        main,
        "upsert_airtable_creator",
        lambda payload: {
            "action": "created",
            "record_id": "recCreator",
            "creator_id": payload["creator_id"],
        },
    )
    client = main.app.test_client()
    response = client.post(
        "/flow/collabs/creator-approved",
        json={"creator_id": "7788", "creator_name": "Creator One"},
        headers={"X-Shopify-Flow-Token": "test-flow-token"},
    )
    assert response.status_code == 200
    assert response.json["status"] == "SYNCED"
    assert response.json["source"] == "shopify_collabs"


def test_collabs_attribution_flow_allows_pending_order_link(monkeypatch):
    monkeypatch.setattr(
        main,
        "upsert_collabs_attribution",
        lambda payload: {
            "action": "created",
            "record_id": "recTouchpoint",
            "order_id": payload["order_id"],
            "order_linked": False,
            "creator_record_id": "recCreator",
            "touchpoint_key": "shopify-collabs:123:7788",
        },
    )
    client = main.app.test_client()
    response = client.post(
        "/flow/collabs/order-attributed",
        json={"order_id": "123"},
        headers={"X-Shopify-Flow-Token": "test-flow-token"},
    )
    assert response.status_code == 200
    assert response.json["status"] == "SYNCED_PENDING_ORDER_LINK"


def test_shared_flow_endpoint_dispatches_collabs_event(monkeypatch):
    monkeypatch.setattr(
        main,
        "upsert_collabs_attribution",
        lambda payload: {
            "action": "created",
            "record_id": "recTouchpoint",
            "order_id": "123",
            "order_linked": True,
            "creator_record_id": "recCreator",
            "touchpoint_key": "shopify-collabs:123:7788",
        },
    )
    client = main.app.test_client()
    response = client.post(
        "/flow/shopify",
        json={"event_type": "collabs_order_attributed", "order_id": "123"},
        headers={"X-Shopify-Flow-Token": "test-flow-token"},
    )
    assert response.status_code == 200
    assert response.json["source"] == "shopify_collabs"
    assert response.json["order_linked"] is True
