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

CUSTOMERS_TABLE = os.getenv("AIRTABLE_CUSTOMERS_TABLE", "客户")
ORDERS_TABLE = os.getenv("AIRTABLE_ORDERS_TABLE", "订单")
LIFECYCLE_TABLE = os.getenv("AIRTABLE_LIFECYCLE_TABLE", "客户生命周期")

CUSTOMER_EMAIL = os.getenv("FIELD_CUSTOMER_EMAIL", "邮箱")
CUSTOMER_LIFECYCLE_LINKS = os.getenv("FIELD_CUSTOMER_LIFECYCLE_LINKS", "生命周期记录")

ORDER_ID = os.getenv("FIELD_ORDER_ID", "订单编号")
ORDER_TIME = os.getenv("FIELD_ORDER_TIME", "下单时间")
ORDER_EMAIL = os.getenv("FIELD_ORDER_EMAIL", "客户邮箱")
ORDER_CANCELLED = os.getenv("FIELD_ORDER_CANCELLED", "是否取消")
ORDER_MAIN_PRODUCT = os.getenv("FIELD_ORDER_MAIN_PRODUCT", "主要产品")
ORDER_ITEMS = os.getenv("FIELD_ORDER_ITEMS", "商品明细")
ORDER_SKUS = os.getenv("FIELD_ORDER_SKUS", "SKU列表")

LIFECYCLE_CUSTOMER = os.getenv("FIELD_LIFECYCLE_CUSTOMER", "客户")
LIFECYCLE_STEP1_DONE = os.getenv("FIELD_LIFECYCLE_STEP1_DONE", "阶段1已完成")
LIFECYCLE_STEP2_DONE = os.getenv("FIELD_LIFECYCLE_STEP2_DONE", "阶段2已完成")
LIFECYCLE_STEP1_AT = os.getenv("FIELD_LIFECYCLE_STEP1_AT", "阶段1完成时间")
LIFECYCLE_STEP2_AT = os.getenv("FIELD_LIFECYCLE_STEP2_AT", "阶段2完成时间")
LIFECYCLE_ORDER_ID = os.getenv("FIELD_LIFECYCLE_ORDER_ID", "关联订单编号")
LIFECYCLE_WARRANTY_DAYS = os.getenv("FIELD_LIFECYCLE_BENEFIT_DAYS", "奖励延保天数")
LIFECYCLE_REVIEW_STATUS = os.getenv("FIELD_LIFECYCLE_REVIEW_STATUS", "审核状态")
LIFECYCLE_SOURCE = os.getenv("FIELD_LIFECYCLE_SOURCE", "同步来源")
LIFECYCLE_SYNCED_AT = os.getenv("FIELD_LIFECYCLE_SYNCED_AT", "最后同步时间")

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
) -> str:
    warranty_days = STAGE1_BENEFIT_DAYS if stage == 1 else STAGE2_BENEFIT_DAYS
    fields: Dict[str, Any] = {
        LIFECYCLE_ORDER_ID: order_id,
        LIFECYCLE_WARRANTY_DAYS: warranty_days,
        LIFECYCLE_REVIEW_STATUS: "待审核" if customer else "需人工匹配",
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
        customer = _find_customer(data["email"])
        order = _find_eligible_order(data["email"])
        if not order:
            return jsonify({"ok": False, "status": "INELIGIBLE", "error": "No eligible product order found"}), 422
        order_id = str(order.get("fields", {}).get(ORDER_ID) or order.get("id"))

        _send_klaviyo_event(
            data["stage"], data["email"], data["response_id"], order_id, data["completed_at"]
        )
        lifecycle_id = _upsert_lifecycle(
            data["stage"], customer, order_id, data["completed_at"]
        )
        return jsonify(
            {
                "ok": True,
                "status": "SYNCED",
                "stage": data["stage"],
                "order_id": order_id,
                "lifecycle_id": lifecycle_id,
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
