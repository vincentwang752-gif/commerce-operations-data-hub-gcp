import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("shopify_airtable_sync")


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN", "")
AIRTABLE_API = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
ORDERS_TABLE = os.getenv("AIRTABLE_ORDERS_TABLE", "")

SHOPIFY_STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN", "").strip().lower()
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-07")
RECONCILE_TOKEN = os.getenv("RECONCILE_TOKEN", "")
SHOPIFY_FLOW_TOKEN = os.getenv("SHOPIFY_FLOW_TOKEN", "")


def _airtable_headers() -> Dict[str, str]:
    if not AIRTABLE_BASE_ID or not ORDERS_TABLE:
        raise RuntimeError("AIRTABLE_BASE_ID and AIRTABLE_ORDERS_TABLE are required")
    if not AIRTABLE_TOKEN:
        raise RuntimeError("AIRTABLE_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json",
    }


def _shopify_headers() -> Dict[str, str]:
    if not SHOPIFY_ACCESS_TOKEN:
        raise RuntimeError("SHOPIFY_ACCESS_TOKEN is not configured")
    return {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


def _formula_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _as_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _refund_total(order: Dict[str, Any]) -> Decimal:
    total = Decimal("0")
    for refund in order.get("refunds") or []:
        for transaction in refund.get("transactions") or []:
            if str(transaction.get("kind", "")).lower() == "refund":
                total += _money(transaction.get("amount"))
    if total:
        return total
    current_total = _money(order.get("current_total_price"))
    original_total = _money(order.get("total_price"))
    if current_total and original_total > current_total:
        return original_total - current_total
    return Decimal("0")


def _utm_fields(landing_site: str) -> Dict[str, str]:
    if not landing_site:
        return {}
    try:
        params = parse_qs(urlparse(landing_site).query)
    except ValueError:
        return {}

    def first(*keys: str) -> str:
        for key in keys:
            values = params.get(key)
            if values and values[0]:
                return values[0]
        return ""

    values = {
        "UTM Source": first("utm_source"),
        "UTM Medium": first("utm_medium"),
        "UTM Campaign": first("utm_campaign"),
        "UTM Content": first("utm_content"),
        "UTM Term": first("utm_term"),
        "Click ID": first("gclid", "wbraid", "gbraid", "fbclid", "ttclid"),
    }
    return {key: value for key, value in values.items() if value}


def _line_items(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in (order.get("line_items") or []) if isinstance(item, dict)]


def _main_product(items: Iterable[Dict[str, Any]]) -> str:
    titles = [str(item.get("title") or item.get("name") or "").strip() for item in items]
    return next((title for title in titles if title), "")


def order_to_airtable_fields(order: Dict[str, Any]) -> Dict[str, Any]:
    items = _line_items(order)
    order_id = str(order.get("id") or "").strip()
    if not order_id:
        raise ValueError("Shopify order payload is missing id")

    email = str(order.get("email") or order.get("contact_email") or "").strip().lower()
    customer = order.get("customer") or {}
    customer_id = str(customer.get("id") or "").strip()
    country = str(
        (order.get("shipping_address") or {}).get("country_code")
        or (order.get("billing_address") or {}).get("country_code")
        or ""
    ).strip()
    skus = [str(item.get("sku") or "").strip() for item in items]
    skus = [sku for sku in skus if sku]
    item_lines = []
    for item in items:
        title = str(item.get("title") or item.get("name") or "").strip()
        variant = str(item.get("variant_title") or "").strip()
        quantity = int(item.get("quantity") or 0)
        label = " — ".join(part for part in (title, variant) if part)
        item_lines.append(f"{label} × {quantity}" if label else f"Item × {quantity}")

    total = _money(order.get("total_price"))
    discounts = _money(order.get("total_discounts"))
    refunded = _refund_total(order)
    fields: Dict[str, Any] = {
        "Order ID": order_id,
        "Ordered At": order.get("created_at") or order.get("processed_at"),
        "SKU": skus[0] if skus else "",
        "Order Revenue": _as_float(total),
        "Discount Amount": _as_float(discounts),
        "Refund Amount": _as_float(refunded),
        "Cancelled": bool(order.get("cancelled_at") or order.get("cancel_reason")),
        "Refunded": bool(refunded > 0),
        "Country/Region": country,
        "Shopify Customer ID": customer_id,
        "Customer Email": email,
        "Currency": str(order.get("currency") or order.get("presentment_currency") or ""),
        "Payment Status": str(order.get("financial_status") or ""),
        "Fulfillment Status": str(order.get("fulfillment_status") or "unfulfilled"),
        "Net Revenue": _as_float(total - refunded),
        "Discount Codes": ", ".join(
            str(code.get("code") or "").strip()
            for code in (order.get("discount_codes") or [])
            if code.get("code")
        ),
        "Line Items": "\n".join(item_lines),
        "SKU List": ", ".join(skus),
        "Order Source": str(order.get("source_name") or ""),
        "Main Product": _main_product(items),
        "Landing Site": str(order.get("landing_site") or ""),
        "Referring Site": str(order.get("referring_site") or ""),
        "Last Synced At": datetime.now(timezone.utc).isoformat(),
    }
    fields.update(_utm_fields(fields["Landing Site"]))
    return {key: value for key, value in fields.items() if value not in (None, "")}


def _find_airtable_order(order_id: str) -> Optional[str]:
    formula = f"{{Order ID}}='{_formula_text(order_id)}'"
    response = requests.get(
        f"{AIRTABLE_API}/{ORDERS_TABLE}",
        headers=_airtable_headers(),
        params={"filterByFormula": formula, "maxRecords": 1, "fields[0]": "Order ID"},
        timeout=20,
    )
    response.raise_for_status()
    records = response.json().get("records", [])
    return records[0]["id"] if records else None


def upsert_airtable_order(order: Dict[str, Any]) -> Dict[str, Any]:
    fields = order_to_airtable_fields(order)
    order_id = str(fields["Order ID"])
    record_id = _find_airtable_order(order_id)
    if record_id:
        response = requests.patch(
            f"{AIRTABLE_API}/{ORDERS_TABLE}/{record_id}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "updated"
    else:
        response = requests.post(
            f"{AIRTABLE_API}/{ORDERS_TABLE}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "created"
    response.raise_for_status()
    body = response.json()
    return {"action": action, "record_id": body["id"], "order_id": order_id}


def _verify_webhook(raw_body: bytes, provided_hmac: str) -> bool:
    if not SHOPIFY_WEBHOOK_SECRET or not provided_hmac:
        return False
    computed = base64.b64encode(
        hmac.new(SHOPIFY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(computed, provided_hmac)


def _valid_shop_domain(value: str) -> bool:
    if not SHOPIFY_STORE_DOMAIN:
        return True
    return value.strip().lower() == SHOPIFY_STORE_DOMAIN


def _valid_flow_token(provided: str) -> bool:
    return bool(
        SHOPIFY_FLOW_TOKEN
        and provided
        and hmac.compare_digest(SHOPIFY_FLOW_TOKEN, provided)
    )


def _graphql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not SHOPIFY_STORE_DOMAIN:
        raise RuntimeError("SHOPIFY_STORE_DOMAIN is not configured")
    response = requests.post(
        f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
        headers=_shopify_headers(),
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(f"Shopify GraphQL error: {json.dumps(body['errors'])[:800]}")
    return body.get("data") or {}


ORDER_QUERY_FIELDS = """
    id
    legacyResourceId
    email
    createdAt
    processedAt
    cancelledAt
    displayFinancialStatus
    displayFulfillmentStatus
    currencyCode
    totalPriceSet { shopMoney { amount } }
    totalDiscountsSet { shopMoney { amount } }
    currentTotalPriceSet { shopMoney { amount } }
    customer { legacyResourceId email }
    shippingAddress { countryCodeV2 }
    lineItems(first: 250) { nodes { title name sku quantity variantTitle } }
"""


def _graphql_order_to_webhook(node: Dict[str, Any]) -> Dict[str, Any]:
    total = (((node.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount"))
    current = (((node.get("currentTotalPriceSet") or {}).get("shopMoney") or {}).get("amount"))
    discounts = (((node.get("totalDiscountsSet") or {}).get("shopMoney") or {}).get("amount"))
    return {
        "id": str(node.get("legacyResourceId") or ""),
        "email": node.get("email") or (node.get("customer") or {}).get("email"),
        "created_at": node.get("createdAt"),
        "processed_at": node.get("processedAt"),
        "cancelled_at": node.get("cancelledAt"),
        "financial_status": node.get("displayFinancialStatus"),
        "fulfillment_status": node.get("displayFulfillmentStatus"),
        "currency": node.get("currencyCode"),
        "total_price": total,
        "current_total_price": current,
        "total_discounts": discounts,
        "customer": {"id": (node.get("customer") or {}).get("legacyResourceId")},
        "shipping_address": {
            "country_code": (node.get("shippingAddress") or {}).get("countryCodeV2")
        },
        "line_items": (node.get("lineItems") or {}).get("nodes") or [],
    }


def fetch_shopify_order(order_id: str) -> Dict[str, Any]:
    # Shopify Flow can expose either the numeric legacy resource ID or the
    # GraphQL GID. Normalize both forms before querying Admin GraphQL.
    order_id = str(order_id or "").strip().rstrip("/").split("/")[-1]
    if not order_id.isdigit():
        raise ValueError("Shopify order ID must be a numeric legacy ID or Order GID")
    query = f"query OrderForSync($id: ID!) {{ order(id: $id) {{ {ORDER_QUERY_FIELDS} }} }}"
    data = _graphql(query, {"id": f"gid://shopify/Order/{order_id}"})
    if not data.get("order"):
        raise ValueError(f"Shopify order {order_id} was not found")
    return _graphql_order_to_webhook(data["order"])


def reconcile_orders(updated_since: datetime) -> Dict[str, Any]:
    query = f"""
    query OrdersForSync($cursor: String, $query: String!) {{
      orders(first: 100, after: $cursor, query: $query, sortKey: UPDATED_AT) {{
        nodes {{ {ORDER_QUERY_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """
    cursor = None
    processed = 0
    created = 0
    updated = 0
    while True:
        search = f"updated_at:>={updated_since.astimezone(timezone.utc).isoformat()}"
        data = _graphql(query, {"cursor": cursor, "query": search})
        connection = data.get("orders") or {}
        for node in connection.get("nodes") or []:
            result = upsert_airtable_order(_graphql_order_to_webhook(node))
            processed += 1
            if result["action"] == "created":
                created += 1
            else:
                updated += 1
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return {"processed": processed, "created": created, "updated": updated}


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "shopify-airtable-sync"})


@app.post("/webhooks/shopify")
def shopify_webhook():
    raw_body = request.get_data(cache=False)
    if not _verify_webhook(raw_body, request.headers.get("X-Shopify-Hmac-Sha256", "")):
        return jsonify({"ok": False, "error": "invalid webhook signature"}), 401
    if not _valid_shop_domain(request.headers.get("X-Shopify-Shop-Domain", "")):
        return jsonify({"ok": False, "error": "unexpected shop domain"}), 403

    try:
        topic = request.headers.get("X-Shopify-Topic", "").lower()
        payload = json.loads(raw_body.decode("utf-8"))
        if topic == "refunds/create":
            order_id = str(payload.get("order_id") or "")
            payload = fetch_shopify_order(order_id)
        elif topic not in {"orders/create", "orders/updated", "orders/cancelled"}:
            return jsonify({"ok": True, "status": "IGNORED", "topic": topic})
        result = upsert_airtable_order(payload)
        return jsonify({"ok": True, "status": "SYNCED", "topic": topic, **result})
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify({"ok": False, "status": "INVALID", "error": str(exc)}), 400
    except requests.RequestException as exc:
        logger.exception("External API request failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Shopify webhook sync failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 500


@app.post("/flow/shopify")
def shopify_flow():
    """Accept an order snapshot sent by Shopify Flow.

    This is the permission-light ingestion path for stores that can't yet
    create an app in Shopify's Dev Dashboard. The Flow action sends the same
    order-shaped JSON used by Shopify order webhooks and authenticates with a
    dedicated shared token. Upserts remain idempotent on Shopify order ID.
    """
    if not _valid_flow_token(request.headers.get("X-Shopify-Flow-Token", "")):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        payload = request.get_json(silent=False) or {}
        # Keep the Flow configuration intentionally small and stable: Flow
        # sends only an order identifier, and the service retrieves the full
        # canonical order snapshot from Shopify Admin API before the upsert.
        # A complete order-shaped payload is still accepted for compatibility.
        flow_order_id = payload.get("order_id")
        if flow_order_id:
            payload = fetch_shopify_order(str(flow_order_id))
        result = upsert_airtable_order(payload)
        return jsonify({"ok": True, "status": "SYNCED", "source": "shopify_flow", **result})
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify({"ok": False, "status": "INVALID", "error": str(exc)}), 400
    except requests.RequestException as exc:
        logger.exception("Shopify Flow sync failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Shopify Flow sync failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 500


@app.post("/reconcile")
def reconcile():
    provided = request.headers.get("X-Reconcile-Token", "")
    if not RECONCILE_TOKEN or not hmac.compare_digest(RECONCILE_TOKEN, provided):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        hours = min(max(int((request.get_json(silent=True) or {}).get("hours", 48)), 1), 168)
        result = reconcile_orders(datetime.now(timezone.utc) - timedelta(hours=hours))
        return jsonify({"ok": True, "status": "SYNCED", "hours": hours, **result})
    except Exception as exc:
        logger.exception("Reconciliation failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
