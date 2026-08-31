import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("voc_survey_sync")


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN", "")
AIRTABLE_API = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
KLAVIYO_COMPANY_ID = os.getenv("KLAVIYO_COMPANY_ID", "")
KLAVIYO_REVISION = os.getenv("KLAVIYO_REVISION", "2026-07-15")
WEBHOOK_TOKEN = os.getenv("VOC_WEBHOOK_TOKEN", "")
SHOPIFY_STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN", "").strip()
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-07").strip()
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()

CUSTOMERS_TABLE = os.getenv("AIRTABLE_CUSTOMERS_TABLE", "客户")
ORDERS_TABLE = os.getenv("AIRTABLE_ORDERS_TABLE", "订单")
LIFECYCLE_TABLE = os.getenv("AIRTABLE_LIFECYCLE_TABLE", "客户生命周期")

CUSTOMER_EMAIL = os.getenv("FIELD_CUSTOMER_EMAIL", "邮箱")
CUSTOMER_LIFECYCLE_LINKS = os.getenv("FIELD_CUSTOMER_LIFECYCLE_LINKS", "关联生命周期")
CUSTOMER_NAME = os.getenv("FIELD_CUSTOMER_NAME", "客户名称")
CUSTOMER_SHOPIFY_ID = os.getenv("FIELD_CUSTOMER_SHOPIFY_ID", "Shopify 客户 ID")
CUSTOMER_UNIQUE_KEY = os.getenv("FIELD_CUSTOMER_UNIQUE_KEY", "客户唯一键")
CUSTOMER_LAST_ORDER_AT = os.getenv("FIELD_CUSTOMER_LAST_ORDER_AT", "最近下单时间")
CUSTOMER_FIRST_ORDER_AT = os.getenv("FIELD_CUSTOMER_FIRST_ORDER_AT", "首次下单时间")
CUSTOMER_SYNCED_AT = os.getenv("FIELD_CUSTOMER_SYNCED_AT", "最后同步时间")

ORDER_ID = os.getenv("FIELD_ORDER_ID", "订单 ID")
ORDER_TIME = os.getenv("FIELD_ORDER_TIME", "下单时间")
ORDER_EMAIL = os.getenv("FIELD_ORDER_EMAIL", "客户邮箱")
ORDER_CANCELLED = os.getenv("FIELD_ORDER_CANCELLED", "是否取消")
ORDER_MAIN_PRODUCT = os.getenv("FIELD_ORDER_MAIN_PRODUCT", "主产品")
ORDER_ITEMS = os.getenv("FIELD_ORDER_ITEMS", "商品明细")
ORDER_SKUS = os.getenv("FIELD_ORDER_SKUS", "SKU 列表")
ORDER_CUSTOMER = os.getenv("FIELD_ORDER_CUSTOMER", "客户")
ORDER_SHOPIFY_CUSTOMER_ID = os.getenv("FIELD_ORDER_SHOPIFY_CUSTOMER_ID", "Shopify 客户 ID")
ORDER_SKU = os.getenv("FIELD_ORDER_SKU", "SKU")
ORDER_REVENUE = os.getenv("FIELD_ORDER_REVENUE", "订单收入")
ORDER_DISCOUNT = os.getenv("FIELD_ORDER_DISCOUNT", "折扣金额")
ORDER_REFUND = os.getenv("FIELD_ORDER_REFUND", "退款金额")
ORDER_COUNTRY = os.getenv("FIELD_ORDER_COUNTRY", "国家/地区")
ORDER_CURRENCY = os.getenv("FIELD_ORDER_CURRENCY", "币种")
ORDER_PAYMENT_STATUS = os.getenv("FIELD_ORDER_PAYMENT_STATUS", "付款状态")
ORDER_FULFILLMENT_STATUS = os.getenv("FIELD_ORDER_FULFILLMENT_STATUS", "履约状态")
ORDER_NET_REVENUE = os.getenv("FIELD_ORDER_NET_REVENUE", "净收入")
ORDER_DISCOUNT_CODES = os.getenv("FIELD_ORDER_DISCOUNT_CODES", "优惠码")
ORDER_SOURCE = os.getenv("FIELD_ORDER_SOURCE", "订单来源")
ORDER_SYNCED_AT = os.getenv("FIELD_ORDER_SYNCED_AT", "最后同步时间")

LIFECYCLE_CUSTOMER = os.getenv("FIELD_LIFECYCLE_CUSTOMER", "客户")
LIFECYCLE_STEP1_DONE = os.getenv("FIELD_LIFECYCLE_STEP1_DONE", "售前问卷已完成")
LIFECYCLE_STEP2_DONE = os.getenv("FIELD_LIFECYCLE_STEP2_DONE", "使用后问卷已完成")
LIFECYCLE_STEP1_AT = os.getenv("FIELD_LIFECYCLE_STEP1_AT", "第一阶段完成时间")
LIFECYCLE_STEP2_AT = os.getenv("FIELD_LIFECYCLE_STEP2_AT", "第二阶段完成时间")
LIFECYCLE_ORDER_ID = os.getenv("FIELD_LIFECYCLE_ORDER_ID", "对应S1订单ID")
LIFECYCLE_WARRANTY_DAYS = os.getenv("FIELD_LIFECYCLE_BENEFIT_DAYS", "延保天数")
LIFECYCLE_REVIEW_STATUS = os.getenv("FIELD_LIFECYCLE_REVIEW_STATUS", "延保审核状态")
LIFECYCLE_SOURCE = os.getenv("FIELD_LIFECYCLE_SOURCE", "问卷回写来源")
LIFECYCLE_SYNCED_AT = os.getenv("FIELD_LIFECYCLE_SYNCED_AT", "问卷最后同步时间")

ELIGIBLE_PRODUCT_TERMS = tuple(
    term.strip().lower()
    for term in os.getenv("ELIGIBLE_PRODUCT_TERMS", "example product").split(",")
    if term.strip()
)
STAGE1_BENEFIT_DAYS = int(os.getenv("STAGE1_BENEFIT_DAYS", "180"))
STAGE2_BENEFIT_DAYS = int(os.getenv("STAGE2_BENEFIT_DAYS", "360"))
KLAVIYO_EVENT_PREFIX = os.getenv("KLAVIYO_EVENT_PREFIX", "Completed VOC Survey Step")


def _headers() -> Dict[str, str]:
    if not AIRTABLE_TOKEN:
        raise RuntimeError("AIRTABLE_TOKEN is not configured")
    return {"Authorization": f"Bearer {AIRTABLE_TOKEN}", "Content-Type": "application/json"}


def _formula_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _list_records(table: str, formula: str, fields: List[str], max_records: int = 20) -> List[Dict[str, Any]]:
    params = {
        "filterByFormula": formula,
        "maxRecords": max_records,
    }
    for idx, field in enumerate(fields):
        params[f"fields[{idx}]"] = field
    response = requests.get(
        f"{AIRTABLE_API}/{table}",
        headers=_headers(),
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("records", [])


def _find_customer(email: str) -> Optional[Dict[str, Any]]:
    safe_email = _formula_text(email.lower())
    records = _list_records(
        CUSTOMERS_TABLE,
        f"LOWER({{{CUSTOMER_EMAIL}}})='{safe_email}'",
        [CUSTOMER_EMAIL, CUSTOMER_LIFECYCLE_LINKS],
        2,
    )
    return records[0] if records else None


def _is_eligible_order(fields: Dict[str, Any]) -> bool:
    if fields.get(ORDER_CANCELLED):
        return False
    combined = " ".join(
        str(fields.get(field, "")) for field in (ORDER_MAIN_PRODUCT, ORDER_ITEMS, ORDER_SKUS)
    ).lower()
    return any(term in combined for term in ELIGIBLE_PRODUCT_TERMS)


def _find_eligible_order(email: str) -> Optional[Dict[str, Any]]:
    safe_email = _formula_text(email.lower())
    records = _list_records(
        ORDERS_TABLE,
        f"LOWER({{{ORDER_EMAIL}}})='{safe_email}'",
        [ORDER_ID, ORDER_TIME, ORDER_EMAIL, ORDER_CANCELLED, ORDER_MAIN_PRODUCT, ORDER_ITEMS, ORDER_SKUS],
        50,
    )
    eligible = [record for record in records if _is_eligible_order(record.get("fields", {}))]
    eligible.sort(key=lambda record: str(record.get("fields", {}).get(ORDER_TIME, "")), reverse=True)
    return eligible[0] if eligible else None


def _shopify_enabled() -> bool:
    return bool(SHOPIFY_STORE_DOMAIN and SHOPIFY_ACCESS_TOKEN)


def _shopify_graphql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(
        f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
        headers={
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": variables},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(f"Shopify GraphQL error: {json.dumps(body['errors'])[:600]}")
    return body.get("data") or {}


def _shopify_order_is_eligible(order: Dict[str, Any]) -> bool:
    if order.get("cancelledAt"):
        return False
    items = (order.get("lineItems") or {}).get("nodes") or []
    combined = " ".join(
        str(item.get(field) or "")
        for item in items
        for field in ("title", "name", "sku", "variantTitle")
    ).lower()
    return any(term in combined for term in ELIGIBLE_PRODUCT_TERMS)


def _find_shopify_eligible_order(email: str) -> Optional[Dict[str, Any]]:
    if not _shopify_enabled():
        return None
    query = """
    query OrdersByEmail($query: String!) {
      orders(first: 50, query: $query, sortKey: PROCESSED_AT, reverse: true) {
        nodes {
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
          discountCodes
          customer { legacyResourceId email displayName }
          shippingAddress { countryCodeV2 }
          lineItems(first: 250) {
            nodes { title name sku quantity variantTitle }
          }
        }
      }
    }
    """
    data = _shopify_graphql(query, {"query": f"email:{email}"})
    orders = (data.get("orders") or {}).get("nodes") or []
    return next((order for order in orders if _shopify_order_is_eligible(order)), None)


def _money_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _shopify_order_values(order: Dict[str, Any], email: str) -> Dict[str, Any]:
    items = (order.get("lineItems") or {}).get("nodes") or []
    skus = [str(item.get("sku") or "").strip() for item in items]
    skus = [sku for sku in skus if sku]
    item_lines = []
    main_product = ""
    for item in items:
        title = str(item.get("title") or item.get("name") or "").strip()
        variant = str(item.get("variantTitle") or "").strip()
        quantity = int(item.get("quantity") or 0)
        label = " — ".join(part for part in (title, variant) if part)
        item_lines.append(f"{label} × {quantity}" if label else f"Item × {quantity}")
        searchable = " ".join(
            str(item.get(field) or "") for field in ("title", "name", "sku", "variantTitle")
        ).lower()
        if not main_product and any(term in searchable for term in ELIGIBLE_PRODUCT_TERMS):
            main_product = title or str(item.get("name") or "").strip()

    total = _money_value((((order.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount")))
    current_total = _money_value((((order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}).get("amount")))
    discount = _money_value((((order.get("totalDiscountsSet") or {}).get("shopMoney") or {}).get("amount")))
    refund = max(0.0, total - current_total)
    customer = order.get("customer") or {}
    return {
        "order_id": str(order.get("legacyResourceId") or ""),
        "email": str(order.get("email") or customer.get("email") or email).strip().lower(),
        "ordered_at": order.get("createdAt") or order.get("processedAt"),
        "cancelled": bool(order.get("cancelledAt")),
        "customer_id": str(customer.get("legacyResourceId") or ""),
        "customer_name": str(customer.get("displayName") or "").strip(),
        "country": str((order.get("shippingAddress") or {}).get("countryCodeV2") or ""),
        "sku": skus[0] if skus else "",
        "skus": ", ".join(skus),
        "items": "\n".join(item_lines),
        "main_product": main_product,
        "total": total,
        "discount": discount,
        "refund": refund,
        "net_total": current_total,
        "currency": str(order.get("currencyCode") or ""),
        "payment_status": str(order.get("displayFinancialStatus") or "").lower(),
        "fulfillment_status": str(order.get("displayFulfillmentStatus") or "unfulfilled").lower(),
        "discount_codes": ", ".join(
            str(code) for code in (order.get("discountCodes") or []) if code
        ),
    }


def _upsert_customer_snapshot(values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    customer = _find_customer(values["email"])
    if customer:
        return customer
    fields = {
        CUSTOMER_NAME: values["customer_name"] or values["email"],
        CUSTOMER_EMAIL: values["email"],
        CUSTOMER_SHOPIFY_ID: values["customer_id"],
        CUSTOMER_UNIQUE_KEY: (
            f"shopify:{values['customer_id']}"
            if values["customer_id"]
            else f"email:{values['email']}"
        ),
        CUSTOMER_FIRST_ORDER_AT: values["ordered_at"],
        CUSTOMER_LAST_ORDER_AT: values["ordered_at"],
        CUSTOMER_SYNCED_AT: datetime.now(timezone.utc).isoformat(),
    }
    fields = {key: value for key, value in fields.items() if value not in (None, "")}
    response = requests.post(
        f"{AIRTABLE_API}/{CUSTOMERS_TABLE}",
        headers=_headers(),
        json={"fields": fields, "typecast": True},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def _upsert_customer_identity(email: str) -> Dict[str, Any]:
    """Ensure each survey response has a customer identity before order matching."""
    customer = _find_customer(email)
    if customer:
        return customer
    response = requests.post(
        f"{AIRTABLE_API}/{CUSTOMERS_TABLE}",
        headers=_headers(),
        json={
            "fields": {
                CUSTOMER_NAME: email,
                CUSTOMER_EMAIL: email,
                CUSTOMER_UNIQUE_KEY: f"email:{email}",
                CUSTOMER_SYNCED_AT: datetime.now(timezone.utc).isoformat(),
            },
            "typecast": True,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def _upsert_order_snapshot(order: Dict[str, Any], email: str) -> Dict[str, Any]:
    values = _shopify_order_values(order, email)
    customer = _upsert_customer_snapshot(values)
    existing = _list_records(
        ORDERS_TABLE,
        f"{{{ORDER_ID}}}='{_formula_text(values['order_id'])}'",
        [ORDER_ID],
        1,
    )
    fields: Dict[str, Any] = {
        ORDER_ID: values["order_id"],
        ORDER_TIME: values["ordered_at"],
        ORDER_EMAIL: values["email"],
        ORDER_CANCELLED: values["cancelled"],
        ORDER_MAIN_PRODUCT: values["main_product"],
        ORDER_ITEMS: values["items"],
        ORDER_SKUS: values["skus"],
        ORDER_SKU: values["sku"],
        ORDER_REVENUE: values["total"],
        ORDER_DISCOUNT: values["discount"],
        ORDER_REFUND: values["refund"],
        ORDER_COUNTRY: values["country"],
        ORDER_SHOPIFY_CUSTOMER_ID: values["customer_id"],
        ORDER_CURRENCY: values["currency"],
        ORDER_PAYMENT_STATUS: values["payment_status"],
        ORDER_FULFILLMENT_STATUS: values["fulfillment_status"],
        ORDER_NET_REVENUE: values["net_total"],
        ORDER_DISCOUNT_CODES: values["discount_codes"],
        ORDER_SOURCE: "shopify-voc-recovery",
        ORDER_SYNCED_AT: datetime.now(timezone.utc).isoformat(),
    }
    if customer:
        fields[ORDER_CUSTOMER] = [customer["id"]]
    fields = {key: value for key, value in fields.items() if value not in (None, "")}
    if existing:
        response = requests.patch(
            f"{AIRTABLE_API}/{ORDERS_TABLE}/{existing[0]['id']}",
            headers=_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
    else:
        response = requests.post(
            f"{AIRTABLE_API}/{ORDERS_TABLE}",
            headers=_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
    response.raise_for_status()
    return response.json()


def _recover_eligible_order(email: str) -> Optional[Dict[str, Any]]:
    shopify_order = _find_shopify_eligible_order(email)
    if not shopify_order:
        return None
    logger.info("Recovering missing eligible order from Shopify for survey response")
    return _upsert_order_snapshot(shopify_order, email)


def _event_unique_id(stage: int, email: str, response_id: str) -> str:
    raw = f"voc|{stage}|{email.lower()}|{response_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalize_datetime(value: Any) -> str:
    """Return an ISO-8601 UTC timestamp accepted by Klaviyo and Airtable."""
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        parsed = None

        if raw:
            try:
                numeric = float(raw)
                if numeric > 10_000_000_000:
                    numeric /= 1000
                parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass

        if parsed is None and raw:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        if parsed is None and raw:
            # Apps Script String(Date) format, for example:
            # Wed Aug 26 2026 14:29:00 GMT+0800 (China Standard Time)
            without_zone_name = raw.split(" (", 1)[0]
            try:
                parsed = datetime.strptime(without_zone_name, "%a %b %d %Y %H:%M:%S GMT%z")
            except ValueError:
                pass

        if parsed is None:
            parsed = datetime.now(timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _send_klaviyo_event(stage: int, email: str, response_id: str, order_id: str, completed_at: str) -> None:
    metric_name = f"{KLAVIYO_EVENT_PREFIX} {stage}"
    warranty_days = STAGE1_BENEFIT_DAYS if stage == 1 else STAGE2_BENEFIT_DAYS
    payload = {
        "data": {
            "type": "event",
            "attributes": {
                "metric": {"data": {"type": "metric", "attributes": {"name": metric_name}}},
                "profile": {
                    "data": {
                        "type": "profile",
                        "attributes": {
                            "email": email,
                            "properties": {
                                f"VOC_Stage{stage}_Completed": True,
                                "VOC_Benefit_Days": warranty_days,
                            },
                        },
                    }
                },
                "properties": {
                    "survey_stage": stage,
                    "source": "Google Cloud",
                    "response_id": response_id,
                    "order_id": order_id,
                    "warranty_extension_days": warranty_days,
                },
                "time": completed_at,
                "unique_id": _event_unique_id(stage, email, response_id),
            },
        }
    }
    response = requests.post(
        f"https://a.klaviyo.com/client/events/?company_id={quote(KLAVIYO_COMPANY_ID)}",
        headers={"Content-Type": "application/json", "revision": KLAVIYO_REVISION},
        json=payload,
        timeout=20,
    )
    if response.status_code != 202:
        raise RuntimeError(f"Klaviyo returned HTTP {response.status_code}: {response.text[:300]}")


def _upsert_lifecycle(
    stage: int,
    customer: Optional[Dict[str, Any]],
    order_id: str,
    completed_at: str,
    order_matched: bool = True,
) -> str:
    warranty_days = STAGE1_BENEFIT_DAYS if stage == 1 else STAGE2_BENEFIT_DAYS
    fields: Dict[str, Any] = {
        LIFECYCLE_ORDER_ID: order_id,
        LIFECYCLE_WARRANTY_DAYS: warranty_days,
        LIFECYCLE_REVIEW_STATUS: "待审核" if order_matched else "需人工匹配",
        LIFECYCLE_SOURCE: "Google Cloud",
        LIFECYCLE_SYNCED_AT: datetime.now(timezone.utc).isoformat(),
    }
    if stage == 1:
        fields[LIFECYCLE_STEP1_DONE] = True
        fields[LIFECYCLE_STEP1_AT] = completed_at
    else:
        fields[LIFECYCLE_STEP1_DONE] = True
        fields[LIFECYCLE_STEP2_DONE] = True
        fields[LIFECYCLE_STEP2_AT] = completed_at

    lifecycle_ids: List[str] = []
    if customer:
        lifecycle_ids = customer.get("fields", {}).get(CUSTOMER_LIFECYCLE_LINKS, []) or []

    if lifecycle_ids:
        lifecycle_id = lifecycle_ids[0]
        response = requests.patch(
            f"{AIRTABLE_API}/{LIFECYCLE_TABLE}/{lifecycle_id}",
            headers=_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
    else:
        if customer:
            fields[LIFECYCLE_CUSTOMER] = [customer["id"]]
        response = requests.post(
            f"{AIRTABLE_API}/{LIFECYCLE_TABLE}",
            headers=_headers(),
            json={"fields": fields, "typecast": True},
            timeout=20,
        )
    response.raise_for_status()
    return response.json()["id"]


def _valid_token(provided: str) -> bool:
    return bool(WEBHOOK_TOKEN and provided and hmac.compare_digest(WEBHOOK_TOKEN, provided))


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    stage = int(payload.get("stage", 0))
    if stage not in (1, 2):
        raise ValueError("stage must be 1 or 2")
    email = str(payload.get("email", "")).strip().lower()
    if "@" not in email:
        raise ValueError("valid email is required")
    response_id = str(payload.get("response_id") or payload.get("row_number") or "").strip()
    if not response_id:
        raise ValueError("response_id or row_number is required")
    completed_at = _normalize_datetime(payload.get("completed_at"))
    return {
        "stage": stage,
        "email": email,
        "response_id": response_id,
        "completed_at": completed_at,
    }


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "voc-survey-sync"})


@app.post("/form-submit")
def form_submit():
    if not _valid_token(request.headers.get("X-VOC-Token", "")):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    try:
        data = _normalize_payload(request.get_json(silent=True) or {})
        order = _find_eligible_order(data["email"])
        recovered_order = False
        if not order:
            order = _recover_eligible_order(data["email"])
            recovered_order = bool(order)
        order_matched = bool(order)
        customer = _upsert_customer_identity(data["email"])
        order_id = (
            str(order.get("fields", {}).get(ORDER_ID) or order.get("id"))
            if order
            else ""
        )

        # Preserve the response for manual review when an exact order match is
        # unavailable, but do not automatically grant the warranty benefit.
        if order_matched:
            _send_klaviyo_event(
                data["stage"], data["email"], data["response_id"], order_id, data["completed_at"]
            )
        lifecycle_id = _upsert_lifecycle(
            data["stage"], customer, order_id, data["completed_at"], order_matched
        )
        return jsonify(
            {
                "ok": True,
                "status": "SYNCED",
                "stage": data["stage"],
                "order_id": order_id,
                "lifecycle_id": lifecycle_id,
                "recovered_order": recovered_order,
                "order_match_status": "MATCHED" if order_matched else "REVIEW_REQUIRED",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "status": "INVALID", "error": str(exc)}), 400
    except requests.RequestException as exc:
        logger.exception("External API request failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 502
    except Exception as exc:
        logger.exception("VOC sync failed")
        return jsonify({"ok": False, "status": "ERROR", "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
