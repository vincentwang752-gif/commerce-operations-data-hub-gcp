import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, quote, urlparse

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("shopify_airtable_sync")


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN", "")
AIRTABLE_API = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
ORDERS_TABLE = os.getenv("AIRTABLE_ORDERS_TABLE", "")
CUSTOMERS_TABLE = os.getenv("AIRTABLE_CUSTOMERS_TABLE", "客户")
CREATORS_TABLE = os.getenv("AIRTABLE_CREATORS_TABLE", "红人")
TOUCHPOINTS_TABLE = os.getenv("AIRTABLE_TOUCHPOINTS_TABLE", "归因触点")

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


def _airtable_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Call Airtable and respect its per-base rate limit.

    A Shopify bulk Flow run can fan out many Cloud Run requests at once. Airtable
    returns 429 before applying the write, so retrying that status is safe even
    for create requests. Other failures are returned to the caller unchanged.
    """
    for attempt in range(6):
        response = requests.request(method, url, **kwargs)
        if response.status_code != 429 or attempt == 5:
            return response
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = max(float(retry_after), 0.25)
        except ValueError:
            delay = min(0.5 * (2**attempt), 8.0)
        time.sleep(delay)
    return response


def _airtable_table_url(table: str) -> str:
    return f"{AIRTABLE_API}/{quote(table, safe='')}"


def _shopify_headers() -> Dict[str, str]:
    if not SHOPIFY_ACCESS_TOKEN:
        raise RuntimeError("SHOPIFY_ACCESS_TOKEN is not configured")
    return {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


def _formula_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _normalize_shopify_id(value: Any) -> str:
    return str(value or "").strip().rstrip("/").split("/")[-1]


def _nested(payload: Dict[str, Any], *paths: str) -> Any:
    """Return the first non-empty value from dot-separated aliases."""
    for path in paths:
        value: Any = payload
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value.get(part)
        if value not in (None, "", [], {}):
            return value
    return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_only(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else datetime.now(timezone.utc).date().isoformat()


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _as_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _whole_number(value: Any) -> int:
    try:
        return max(int(Decimal(str(value or "0"))), 0)
    except (InvalidOperation, ValueError):
        return 0


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
        "UTM 来源": first("utm_source"),
        "UTM 媒介": first("utm_medium"),
        "UTM 广告系列": first("utm_campaign"),
        "UTM 内容": first("utm_content"),
        "UTM 关键词": first("utm_term"),
        "点击 ID": first("gclid", "wbraid", "gbraid", "fbclid", "ttclid"),
    }
    return {key: value for key, value in values.items() if value}


def _line_items(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in (order.get("line_items") or []) if isinstance(item, dict)]


def _main_product(items: Iterable[Dict[str, Any]]) -> str:
    titles = [str(item.get("title") or item.get("name") or "").strip() for item in items]
    for title in titles:
        lowered = title.lower()
        if "airstudio s1" in lowered or "hisong s1" in lowered:
            return "AirStudio S1"
        if "airstudio s2" in lowered or "hisong s2" in lowered:
            return "AirStudio S2"
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
        "订单 ID": order_id,
        "下单时间": order.get("created_at") or order.get("processed_at"),
        "SKU": skus[0] if skus else "",
        "订单收入": _as_float(total),
        "折扣金额": _as_float(discounts),
        "退款金额": _as_float(refunded),
        "是否取消": bool(order.get("cancelled_at") or order.get("cancel_reason")),
        "是否退货": bool(refunded > 0),
        "国家/地区": country,
        "Shopify 客户 ID": customer_id,
        "客户邮箱": email,
        "币种": str(order.get("currency") or order.get("presentment_currency") or ""),
        "付款状态": str(order.get("financial_status") or ""),
        "履约状态": str(order.get("fulfillment_status") or "unfulfilled"),
        "净收入": _as_float(total - refunded),
        "优惠码": ", ".join(
            str(code.get("code") or "").strip()
            for code in (order.get("discount_codes") or [])
            if code.get("code")
        ),
        "商品明细": "\n".join(item_lines),
        "SKU 列表": ", ".join(skus),
        "订单来源": str(order.get("source_name") or ""),
        "主产品": _main_product(items),
        "Landing Site": str(order.get("landing_site") or ""),
        "Referring Site": str(order.get("referring_site") or ""),
        "最后同步时间": datetime.now(timezone.utc).isoformat(),
    }
    fields.update(_utm_fields(fields["Landing Site"]))
    return {key: value for key, value in fields.items() if value not in (None, "")}


def _find_airtable_order(order_id: str) -> Optional[str]:
    formula = f"{{订单 ID}}='{_formula_text(order_id)}'"
    response = _airtable_request(
        "GET",
        f"{AIRTABLE_API}/{ORDERS_TABLE}",
        headers=_airtable_headers(),
        params={"filterByFormula": formula, "maxRecords": 1, "fields[0]": "订单 ID"},
        timeout=20,
    )
    response.raise_for_status()
    records = response.json().get("records", [])
    return records[0]["id"] if records else None


def _customer_identity(order: Dict[str, Any]) -> Dict[str, str]:
    customer = order.get("customer") or {}
    customer_id = str(customer.get("id") or "").strip()
    email = str(order.get("email") or customer.get("email") or "").strip().lower()
    first_name = str(customer.get("first_name") or "").strip()
    last_name = str(customer.get("last_name") or "").strip()
    display_name = str(customer.get("display_name") or "").strip()
    name = display_name or " ".join(value for value in (first_name, last_name) if value)
    country = str(
        (order.get("shipping_address") or {}).get("country_code")
        or (order.get("billing_address") or {}).get("country_code")
        or ""
    ).strip()
    return {
        "customer_id": customer_id,
        "email": email,
        "name": name,
        "country": country,
        "unique_key": f"shopify:{customer_id}" if customer_id else (f"email:{email}" if email else ""),
    }


def _customer_match_formula(
    customer_id: str, email: str, email_field: str = "邮箱"
) -> str:
    conditions = []
    if customer_id:
        conditions.append(f"{{Shopify 客户 ID}}='{_formula_text(customer_id)}'")
    if email:
        conditions.append(
            f"LOWER({{{email_field}}})='{_formula_text(email.lower())}'"
        )
    if not conditions:
        return "FALSE()"
    return conditions[0] if len(conditions) == 1 else f"OR({','.join(conditions)})"


def _find_airtable_customer(customer_id: str, email: str) -> Optional[Dict[str, Any]]:
    response = _airtable_request(
        "GET",
        f"{AIRTABLE_API}/{CUSTOMERS_TABLE}",
        headers=_airtable_headers(),
        params={
            "filterByFormula": _customer_match_formula(customer_id, email),
            "maxRecords": 2,
            "fields[0]": "Shopify 客户 ID",
            "fields[1]": "邮箱",
            "fields[2]": "客户名称",
        },
        timeout=20,
    )
    response.raise_for_status()
    records = response.json().get("records", [])
    if not records:
        return None
    if customer_id:
        exact = [
            record
            for record in records
            if str(record.get("fields", {}).get("Shopify 客户 ID") or "") == customer_id
        ]
        if exact:
            return exact[0]
    return records[0]


def upsert_airtable_customer(order: Dict[str, Any]) -> Optional[str]:
    identity = _customer_identity(order)
    if not identity["customer_id"] and not identity["email"]:
        return None

    existing = _find_airtable_customer(identity["customer_id"], identity["email"])
    ordered_at = order.get("created_at") or order.get("processed_at")
    fields: Dict[str, Any] = {
        "邮箱": identity["email"],
        "国家/地区": identity["country"],
        "Shopify 客户 ID": identity["customer_id"],
        "最近下单时间": ordered_at,
        "最后同步时间": datetime.now(timezone.utc).isoformat(),
        "客户唯一键": identity["unique_key"],
    }
    fields = {key: value for key, value in fields.items() if value not in (None, "")}

    if existing:
        if identity["name"]:
            fields["客户名称"] = identity["name"]
        response = _airtable_request(
            "PATCH",
            f"{AIRTABLE_API}/{CUSTOMERS_TABLE}/{existing['id']}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
    else:
        fields["客户名称"] = identity["name"] or identity["email"] or identity["customer_id"]
        if ordered_at:
            fields["首次下单时间"] = ordered_at
        response = _airtable_request(
            "POST",
            f"{AIRTABLE_API}/{CUSTOMERS_TABLE}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
    response.raise_for_status()
    return response.json()["id"]


def _matching_orders(customer_id: str, email: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset = ""
    while True:
        params: Dict[str, Any] = {
            "filterByFormula": _customer_match_formula(
                customer_id, email, email_field="客户邮箱"
            ),
            "pageSize": 100,
            "fields[0]": "下单时间",
            "fields[1]": "净收入",
            "fields[2]": "是否取消",
        }
        if offset:
            params["offset"] = offset
        response = _airtable_request(
            "GET",
            f"{AIRTABLE_API}/{ORDERS_TABLE}",
            headers=_airtable_headers(),
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
        records.extend(body.get("records", []))
        offset = body.get("offset", "")
        if not offset:
            return records


def refresh_customer_aggregates(customer_record_id: str, order: Dict[str, Any]) -> None:
    identity = _customer_identity(order)
    records = _matching_orders(identity["customer_id"], identity["email"])
    active = [record for record in records if not record.get("fields", {}).get("是否取消")]
    dates = [
        str(record.get("fields", {}).get("下单时间") or "")
        for record in active
        if record.get("fields", {}).get("下单时间")
    ]
    revenue = sum(
        (_money(record.get("fields", {}).get("净收入")) for record in active),
        Decimal("0"),
    )
    fields: Dict[str, Any] = {
        "累计订单数": len(active),
        "累计收入": _as_float(revenue),
        "最后同步时间": datetime.now(timezone.utc).isoformat(),
    }
    if dates:
        fields["首次下单时间"] = min(dates)
        fields["最近下单时间"] = max(dates)
    response = _airtable_request(
        "PATCH",
        f"{AIRTABLE_API}/{CUSTOMERS_TABLE}/{customer_record_id}",
        headers=_airtable_headers(),
        json={"fields": fields, "typecast": True},
        timeout=20,
    )
    response.raise_for_status()


def _orders_for_customer_repair() -> List[Dict[str, Any]]:
    """Read the identity and value fields needed to rebuild customer links."""
    records: List[Dict[str, Any]] = []
    offset = ""
    field_names = [
        "订单 ID",
        "下单时间",
        "Shopify 客户 ID",
        "客户邮箱",
        "国家/地区",
        "净收入",
        "是否取消",
        "客户",
    ]
    while True:
        params: List[tuple] = [("pageSize", "100")]
        params.extend((f"fields[{index}]", name) for index, name in enumerate(field_names))
        if offset:
            params.append(("offset", offset))
        response = _airtable_request(
            "GET",
            f"{AIRTABLE_API}/{ORDERS_TABLE}",
            headers=_airtable_headers(),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        records.extend(body.get("records", []))
        offset = body.get("offset", "")
        if not offset:
            return records


def _customers_for_customer_repair() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset = ""
    field_names = ["Shopify 客户 ID", "邮箱", "客户名称"]
    while True:
        params: List[tuple] = [("pageSize", "100")]
        params.extend((f"fields[{index}]", name) for index, name in enumerate(field_names))
        if offset:
            params.append(("offset", offset))
        response = _airtable_request(
            "GET",
            f"{AIRTABLE_API}/{CUSTOMERS_TABLE}",
            headers=_airtable_headers(),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        records.extend(body.get("records", []))
        offset = body.get("offset", "")
        if not offset:
            return records


def _batch_update_airtable_records(table: str, records: List[Dict[str, Any]]) -> None:
    for start in range(0, len(records), 10):
        response = _airtable_request(
            "PATCH",
            f"{AIRTABLE_API}/{table}",
            headers=_airtable_headers(),
            json={"records": records[start : start + 10], "typecast": True},
            timeout=30,
        )
        response.raise_for_status()


def repair_customer_links() -> Dict[str, int]:
    """Backfill Customers and Orders.Customer from the existing Orders table.

    This is intentionally based on Airtable's stored order snapshots, so it can
    repair historical data without Shopify Admin API access.
    """
    orders = _orders_for_customer_repair()
    customers = _customers_for_customer_repair()
    customers_by_id: Dict[str, str] = {}
    customers_by_email: Dict[str, str] = {}
    for customer in customers:
        fields = customer.get("fields", {})
        customer_id = str(fields.get("Shopify 客户 ID") or "").strip()
        email = str(fields.get("邮箱") or "").strip().lower()
        if customer_id:
            customers_by_id[customer_id] = customer["id"]
        if email:
            customers_by_email[email] = customer["id"]

    customer_cache: Dict[str, str] = {}
    aggregates: Dict[str, Dict[str, Any]] = {}
    customer_updates: Dict[str, Dict[str, Any]] = {}
    order_updates: List[Dict[str, Any]] = []
    linked = 0
    skipped = 0
    created_customers = 0

    for record in orders:
        fields = record.get("fields", {})
        customer_id = str(fields.get("Shopify 客户 ID") or "").strip()
        email = str(fields.get("客户邮箱") or "").strip().lower()
        if not customer_id and not email:
            skipped += 1
            continue

        identity_key = f"shopify:{customer_id}" if customer_id else f"email:{email}"
        order = {
            "id": str(fields.get("订单 ID") or ""),
            "email": email,
            "created_at": fields.get("下单时间"),
            "customer": {"id": customer_id, "email": email},
            "shipping_address": {"country_code": fields.get("国家/地区") or ""},
        }
        customer_record_id = (
            customer_cache.get(identity_key)
            or (customers_by_id.get(customer_id) if customer_id else None)
            or customers_by_email.get(email)
        )
        if not customer_record_id:
            customer_record_id = upsert_airtable_customer(order)
            if not customer_record_id:
                skipped += 1
                continue
            created_customers += 1
        customer_cache[identity_key] = customer_record_id
        if customer_id:
            customers_by_id[customer_id] = customer_record_id
        if email:
            customers_by_email[email] = customer_record_id

        update_fields = customer_updates.setdefault(customer_record_id, {})
        if email:
            update_fields["邮箱"] = email
        if customer_id:
            update_fields["Shopify 客户 ID"] = customer_id
        if fields.get("国家/地区"):
            update_fields["国家/地区"] = fields["国家/地区"]
        update_fields["客户唯一键"] = identity_key

        if fields.get("客户") != [customer_record_id]:
            order_updates.append(
                {"id": record["id"], "fields": {"客户": [customer_record_id]}}
            )
            linked += 1

        stats = aggregates.setdefault(
            customer_record_id,
            {"count": 0, "revenue": Decimal("0"), "dates": []},
        )
        if fields.get("是否取消"):
            continue
        stats["count"] += 1
        stats["revenue"] += _money(fields.get("净收入"))
        if fields.get("下单时间"):
            stats["dates"].append(str(fields["下单时间"]))

    synced_at = datetime.now(timezone.utc).isoformat()
    for customer_record_id, stats in aggregates.items():
        customer_fields = customer_updates.setdefault(customer_record_id, {})
        customer_fields.update({
            "累计订单数": stats["count"],
            "累计收入": _as_float(stats["revenue"]),
            "最后同步时间": synced_at,
        })
        if stats["dates"]:
            customer_fields["首次下单时间"] = min(stats["dates"])
            customer_fields["最近下单时间"] = max(stats["dates"])

    _batch_update_airtable_records(ORDERS_TABLE, order_updates)
    _batch_update_airtable_records(
        CUSTOMERS_TABLE,
        [
            {"id": customer_record_id, "fields": fields}
            for customer_record_id, fields in customer_updates.items()
        ],
    )

    return {
        "orders_scanned": len(orders),
        "customers_upserted": len(customer_cache),
        "customers_created": created_customers,
        "orders_linked": linked,
        "orders_skipped_without_identity": skipped,
    }


def upsert_airtable_order(order: Dict[str, Any]) -> Dict[str, Any]:
    fields = order_to_airtable_fields(order)
    customer_record_id = upsert_airtable_customer(order)
    if customer_record_id:
        fields["客户"] = [customer_record_id]
    order_id = str(fields["订单 ID"])
    record_id = _find_airtable_order(order_id)
    if record_id:
        response = _airtable_request(
            "PATCH",
            f"{AIRTABLE_API}/{ORDERS_TABLE}/{record_id}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "updated"
    else:
        response = _airtable_request(
            "POST",
            f"{AIRTABLE_API}/{ORDERS_TABLE}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "created"
    response.raise_for_status()
    body = response.json()
    pending_touchpoints_linked = link_pending_collabs_touchpoints(order_id, body["id"])
    if customer_record_id:
        refresh_customer_aggregates(customer_record_id, order)
    return {
        "action": action,
        "record_id": body["id"],
        "order_id": order_id,
        "customer_record_id": customer_record_id,
        "pending_collabs_touchpoints_linked": pending_touchpoints_linked,
    }


def collabs_creator_from_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    creator_id = _normalize_shopify_id(
        _nested(
            payload,
            "creator_id",
            "collabs_creator_id",
            "creator.id",
            "creator.legacyResourceId",
            "creator.collabsId",
            "collaborator.id",
        )
    )
    email = str(
        _nested(payload, "creator_email", "creator.email", "collaborator.email") or ""
    ).strip().lower()
    first_name = str(_nested(payload, "first_name", "creator.firstName") or "").strip()
    last_name = str(_nested(payload, "last_name", "creator.lastName") or "").strip()
    name = str(
        _nested(
            payload,
            "creator_name",
            "creator.displayName",
            "creator.name",
            "collaborator.name",
        )
        or " ".join(value for value in (first_name, last_name) if value)
    ).strip()
    handle = str(
        _nested(
            payload,
            "creator_handle",
            "creator.handle",
            "creator.socialHandle",
            "collaborator.handle",
        )
        or ""
    ).strip().lstrip("@")
    profile_url = str(
        _nested(
            payload,
            "creator_profile_url",
            "creator.profileUrl",
            "creator.url",
            "collaborator.profileUrl",
        )
        or ""
    ).strip()
    affiliate_url = str(
        _nested(
            payload,
            "affiliate_link",
            "creator.affiliateLink",
            "creator.link",
            "collaborator.affiliateLink",
        )
        or ""
    ).strip()
    coupon = str(
        _nested(
            payload,
            "discount_code",
            "coupon_code",
            "creator.discountCode",
            "creator.code",
            "collaborator.discountCode",
        )
        or ""
    ).strip()
    platform = str(
        _nested(payload, "creator_platform", "creator.platform", "collaborator.platform")
        or ""
    ).strip()
    country = str(
        _nested(payload, "creator_country", "country", "creator.location") or ""
    ).strip()
    if creator_id:
        unique_key = f"shopify-collabs:{creator_id}"
    elif email:
        unique_key = f"shopify-collabs-email:{email}"
    elif profile_url:
        unique_key = f"shopify-collabs-url:{profile_url.lower()}"
    elif handle:
        unique_key = f"shopify-collabs-handle:{platform.lower()}:{handle.lower()}"
    else:
        unique_key = ""
    return {
        "id": creator_id,
        "email": email,
        "name": name,
        "handle": handle,
        "profile_url": profile_url,
        "affiliate_url": affiliate_url,
        "coupon": coupon,
        "platform": platform,
        "country": country,
        "unique_key": unique_key,
    }


def _creator_match_formula(creator: Dict[str, str]) -> str:
    conditions = []
    if creator.get("id"):
        conditions.append(
            f"{{Shopify Collabs ID}}='{_formula_text(creator['id'])}'"
        )
    if creator.get("unique_key"):
        conditions.append(f"{{红人唯一键}}='{_formula_text(creator['unique_key'])}'")
    if creator.get("email"):
        conditions.append(f"LOWER({{邮箱}})='{_formula_text(creator['email'])}'")
    if not conditions:
        return "FALSE()"
    return conditions[0] if len(conditions) == 1 else f"OR({','.join(conditions)})"


def _find_airtable_creator(creator: Dict[str, str]) -> Optional[Dict[str, Any]]:
    response = _airtable_request(
        "GET",
        _airtable_table_url(CREATORS_TABLE),
        headers=_airtable_headers(),
        params={
            "filterByFormula": _creator_match_formula(creator),
            "maxRecords": 3,
            "fields[0]": "Shopify Collabs ID",
            "fields[1]": "红人唯一键",
            "fields[2]": "邮箱",
        },
        timeout=20,
    )
    response.raise_for_status()
    records = response.json().get("records", [])
    if not records:
        return None
    for record in records:
        fields = record.get("fields", {})
        if creator.get("id") and str(fields.get("Shopify Collabs ID") or "") == creator["id"]:
            return record
        if creator.get("unique_key") and str(fields.get("红人唯一键") or "") == creator["unique_key"]:
            return record
    return records[0]


def upsert_airtable_creator(payload: Dict[str, Any]) -> Dict[str, Any]:
    creator = collabs_creator_from_payload(payload)
    if not creator["unique_key"]:
        raise ValueError("Collabs creator payload has no stable ID, email, URL, or handle")
    existing = _find_airtable_creator(creator)
    discovered_at = str(
        _nested(payload, "event_time", "occurred_at", "created_at", "creator.createdAt")
        or _iso_now()
    )
    fields: Dict[str, Any] = {
        "红人名称": creator["name"] or creator["handle"] or creator["email"] or creator["id"],
        "邮箱": creator["email"],
        "红人唯一键": creator["unique_key"],
        "账号名称": creator["handle"],
        "主页链接": creator["profile_url"],
        "国家/地区": creator["country"],
        "Shopify Collabs ID": creator["id"],
        "默认推广链接": creator["affiliate_url"],
        "默认优惠码": creator["coupon"],
        "引入方/供应商": "Shopify Collabs",
        "最后更新时间": _date_only(discovered_at),
        "最后发现时间": discovered_at,
    }
    audience_by_platform = {
        "X/Twitter": _whole_number(
            _nested(payload, "twitter_follower_count", "twitterFollowerCount")
        ),
        "Twitch": _whole_number(
            _nested(payload, "twitch_follower_count", "twitchFollowerCount")
        ),
        "TikTok": _whole_number(
            _nested(payload, "tiktok_follower_count", "tiktokFollowerCount")
        ),
        "YouTube": _whole_number(
            _nested(payload, "youtube_subscriber_count", "youtubeSubscriberCount")
        ),
        "Facebook": _whole_number(
            _nested(payload, "facebook_like_count", "facebookLikeCount")
        ),
        "Instagram": _whole_number(
            _nested(payload, "instagram_follower_count", "instagramFollowerCount")
        ),
    }
    detected_platforms = [
        platform for platform, audience in audience_by_platform.items() if audience > 0
    ]
    if creator["platform"] and creator["platform"] not in detected_platforms:
        detected_platforms.append(creator["platform"])
    if detected_platforms:
        fields["平台"] = detected_platforms
    if audience_by_platform and max(audience_by_platform.values()) > 0:
        fields["粉丝量"] = max(audience_by_platform.values())
    fields = {key: value for key, value in fields.items() if value not in (None, "", [])}
    if existing:
        response = _airtable_request(
            "PATCH",
            f"{_airtable_table_url(CREATORS_TABLE)}/{existing['id']}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "updated"
    else:
        fields["首次发现时间"] = discovered_at
        response = _airtable_request(
            "POST",
            _airtable_table_url(CREATORS_TABLE),
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "created"
    response.raise_for_status()
    return {
        "action": action,
        "record_id": response.json()["id"],
        "creator_id": creator["id"],
        "creator_key": creator["unique_key"],
        "creator": creator,
    }


def collabs_attribution_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    creator = collabs_creator_from_payload(payload)
    order_id = _normalize_shopify_id(
        _nested(
            payload,
            "order_id",
            "order.id",
            "order.legacyResourceId",
            "attribution.orderId",
        )
    )
    event_id = _normalize_shopify_id(
        _nested(payload, "event_id", "attribution_id", "attribution.id")
    )
    occurred_at = str(
        _nested(
            payload,
            "event_time",
            "occurred_at",
            "created_at",
            "attribution.createdAt",
            "order.createdAt",
        )
        or _iso_now()
    )
    revenue = _money(
        _nested(
            payload,
            "attributed_revenue",
            "attributed_sales",
            "sales",
            "order_total",
            "attribution.amount",
            "order.totalPrice",
            "order.totalPriceSet.shopMoney.amount",
        )
    )
    commission = _money(
        _nested(
            payload,
            "commission",
            "commission_amount",
            "attribution.commission",
            "attribution.commissionAmount",
        )
    )
    status = str(
        _nested(payload, "status", "attribution.status", "commission_status") or ""
    ).strip()
    discount_codes = _text_list(
        _nested(payload, "discount_codes", "order.discountCodes")
    )
    coupon = str(
        _nested(
            payload,
            "discount_code",
            "coupon_code",
            "order.discountCode",
            "attribution.discountCode",
        )
        or (", ".join(discount_codes) if discount_codes else "")
        or creator["coupon"]
    ).strip()
    affiliate_url = str(
        _nested(payload, "affiliate_link", "attribution.affiliateLink")
        or creator["affiliate_url"]
    ).strip()
    if not order_id:
        raise ValueError("Collabs attribution payload is missing Shopify order ID")
    creator_key = creator["id"] or creator["unique_key"] or "unknown"
    touchpoint_key = f"shopify-collabs:{order_id}:{creator_key}"
    if event_id:
        touchpoint_key = f"{touchpoint_key}:{event_id}"
    return {
        "order_id": order_id,
        "event_id": event_id,
        "occurred_at": occurred_at,
        "revenue": revenue,
        "commission": commission,
        "status": status,
        "coupon": coupon,
        "affiliate_url": affiliate_url,
        "touchpoint_key": touchpoint_key,
        "creator": creator,
    }


def _find_airtable_touchpoint(touchpoint_key: str) -> Optional[str]:
    formula = f"{{触点唯一键}}='{_formula_text(touchpoint_key)}'"
    response = _airtable_request(
        "GET",
        _airtable_table_url(TOUCHPOINTS_TABLE),
        headers=_airtable_headers(),
        params={"filterByFormula": formula, "maxRecords": 1, "fields[0]": "触点唯一键"},
        timeout=20,
    )
    response.raise_for_status()
    records = response.json().get("records", [])
    return records[0]["id"] if records else None


def link_pending_collabs_touchpoints(order_id: str, order_record_id: str) -> int:
    marker = f"shopify_order_id={order_id}"
    formula = (
        f"AND(FIND('{_formula_text(marker)}',{{UTM 参数}}),"
        "NOT({订单}),{行为数据来源}='Shopify')"
    )
    response = _airtable_request(
        "GET",
        _airtable_table_url(TOUCHPOINTS_TABLE),
        headers=_airtable_headers(),
        params={
            "filterByFormula": formula,
            "pageSize": 100,
            "fields[0]": "触点唯一键",
        },
        timeout=20,
    )
    response.raise_for_status()
    records = response.json().get("records", [])
    if not records:
        return 0
    _batch_update_airtable_records(
        TOUCHPOINTS_TABLE,
        [
            {"id": record["id"], "fields": {"订单": [order_record_id]}}
            for record in records
        ],
    )
    return len(records)


def upsert_collabs_attribution(payload: Dict[str, Any]) -> Dict[str, Any]:
    attribution = collabs_attribution_from_payload(payload)
    creator_result = upsert_airtable_creator(payload)
    order_record_id = _find_airtable_order(attribution["order_id"])
    summary_parts = [f"shopify_order_id={attribution['order_id']}"]
    if attribution["event_id"]:
        summary_parts.append(f"collabs_event_id={attribution['event_id']}")
    if attribution["commission"]:
        summary_parts.append(f"commission={_as_float(attribution['commission'])}")
    if attribution["status"]:
        summary_parts.append(f"status={attribution['status']}")
    sales_number = _nested(payload, "sales_number", "salesNumber")
    sales_cumulative_cents = _nested(
        payload, "sales_cumulative_cents", "salesCumulativeCents"
    )
    commission_cumulative_cents = _nested(
        payload, "commission_cumulative_cents", "commissionCumulativeCents"
    )
    if sales_number not in (None, ""):
        summary_parts.append(f"creator_sales_number={sales_number}")
    if sales_cumulative_cents not in (None, ""):
        summary_parts.append(
            f"creator_sales_cumulative={_as_float(_money(sales_cumulative_cents) / Decimal('100'))}"
        )
    if commission_cumulative_cents not in (None, ""):
        summary_parts.append(
            f"creator_commission_cumulative={_as_float(_money(commission_cumulative_cents) / Decimal('100'))}"
        )
    fields: Dict[str, Any] = {
        "红人": [creator_result["record_id"]],
        "平台": "Shopify Collabs",
        "UTM 参数": "; ".join(summary_parts),
        "推广链接": attribution["affiliate_url"],
        "优惠码": attribution["coupon"],
        "是否最终触点": True,
        "触点日期": _date_only(attribution["occurred_at"]),
        "来源类型": "红人",
        "归因方式": "Shopify Collabs 平台归因",
        "归因置信度": "High",
        "归因收入": _as_float(attribution["revenue"]),
        "归因角色": "最终",
        "触点唯一键": attribution["touchpoint_key"],
        "行为数据来源": "Shopify",
    }
    if order_record_id:
        fields["订单"] = [order_record_id]
    fields = {key: value for key, value in fields.items() if value not in (None, "", [])}
    record_id = _find_airtable_touchpoint(attribution["touchpoint_key"])
    if record_id:
        response = _airtable_request(
            "PATCH",
            f"{_airtable_table_url(TOUCHPOINTS_TABLE)}/{record_id}",
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "updated"
    else:
        response = _airtable_request(
            "POST",
            _airtable_table_url(TOUCHPOINTS_TABLE),
            headers=_airtable_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
        action = "created"
    response.raise_for_status()
    return {
        "action": action,
        "record_id": response.json()["id"],
        "order_id": attribution["order_id"],
        "order_linked": bool(order_record_id),
        "creator_record_id": creator_result["record_id"],
        "touchpoint_key": attribution["touchpoint_key"],
    }


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
        event_type = str(payload.get("event_type") or "").strip().lower()
        if event_type == "collabs_creator_approved":
            result = upsert_airtable_creator(payload)
            return jsonify(
                {"ok": True, "status": "SYNCED", "source": "shopify_collabs", **result}
            )
        if event_type == "collabs_order_attributed":
            result = upsert_collabs_attribution(payload)
            status = "SYNCED" if result["order_linked"] else "SYNCED_PENDING_ORDER_LINK"
            return jsonify(
                {"ok": True, "status": status, "source": "shopify_collabs", **result}
            )
        # Prefer a complete order snapshot from Shopify Flow. This path does
        # not require a Shopify Admin API token and is useful when the operator
        # can manage Flow but cannot create or manage apps in Dev Dashboard.
        # The order-ID-only path remains available when Admin API access is
        # configured, and is also used by reconciliation and refund refreshes.
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


@app.post("/flow/collabs/creator-approved")
def collabs_creator_approved_flow():
    """Upsert a creator approved in Shopify Collabs into Airtable."""
    if not _valid_flow_token(request.headers.get("X-Shopify-Flow-Token", "")):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        payload = request.get_json(silent=False) or {}
        result = upsert_airtable_creator(payload)
        return jsonify(
            {"ok": True, "status": "SYNCED", "source": "shopify_collabs", **result}
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify({"ok": False, "status": "INVALID", "error": str(exc)}), 400
    except requests.RequestException as exc:
        logger.exception("Shopify Collabs creator sync failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Shopify Collabs creator sync failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 500


@app.post("/flow/collabs/order-attributed")
def collabs_order_attributed_flow():
    """Create or update a Collabs-backed order attribution touchpoint."""
    if not _valid_flow_token(request.headers.get("X-Shopify-Flow-Token", "")):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        payload = request.get_json(silent=False) or {}
        result = upsert_collabs_attribution(payload)
        status = "SYNCED" if result["order_linked"] else "SYNCED_PENDING_ORDER_LINK"
        return jsonify(
            {"ok": True, "status": status, "source": "shopify_collabs", **result}
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify({"ok": False, "status": "INVALID", "error": str(exc)}), 400
    except requests.RequestException as exc:
        logger.exception("Shopify Collabs attribution sync failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Shopify Collabs attribution sync failed")
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


@app.post("/repair/customer-links")
def repair_customer_links_endpoint():
    provided = request.headers.get("X-Reconcile-Token", "")
    if not RECONCILE_TOKEN or not hmac.compare_digest(RECONCILE_TOKEN, provided):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        result = repair_customer_links()
        return jsonify({"ok": True, "status": "SYNCED", **result})
    except Exception as exc:
        logger.exception("Customer-link repair failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
