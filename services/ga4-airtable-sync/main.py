from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, List

import requests
from flask import Flask, jsonify
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from zoneinfo import ZoneInfo


app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("ga4_airtable_sync")


PROJECT_ID = os.environ.get("PROJECT_ID", "")
GA4_PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_ID = os.environ.get("AIRTABLE_TABLE_ID", "GA4运营与用户行为")
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "commerce_data")
BIGQUERY_TABLE = os.getenv("BIGQUERY_TABLE", "ga4_daily")
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Shanghai")
EXCLUDE_RECENT_DAYS = int(os.getenv("EXCLUDE_RECENT_DAYS", "3"))


FIELDS = {
    "key": "唯一键",
    "date": "日期",
    "grain": "数据粒度",
    "dimension": "维度值",
    "active_users": "活跃用户数",
    "new_users": "新用户数",
    "sessions": "会话数",
    "engaged_sessions": "互动会话数",
    "engagement_rate": "互动率",
    "avg_engagement_seconds": "平均互动时长（秒）",
    "views": "浏览量",
    "purchasers": "购买用户数",
    "purchases": "GA4购买事件数",
    "purchase_revenue": "GA4购买收入",
    "sync_source": "同步来源",
    "last_sync": "最后同步时间",
    "notes": "口径说明",
}


GA4_METRICS = [
    "activeUsers",
    "newUsers",
    "sessions",
    "screenPageViews",
    "engagedSessions",
    "engagementRate",
    "userEngagementDuration",
    "totalPurchasers",
    "ecommercePurchases",
    "purchaseRevenue",
]


BQ_SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("property_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("active_users", "INT64"),
    bigquery.SchemaField("new_users", "INT64"),
    bigquery.SchemaField("sessions", "INT64"),
    bigquery.SchemaField("views", "INT64"),
    bigquery.SchemaField("engaged_sessions", "INT64"),
    bigquery.SchemaField("engagement_rate", "FLOAT64"),
    bigquery.SchemaField("avg_engagement_seconds", "FLOAT64"),
    bigquery.SchemaField("purchasers", "INT64"),
    bigquery.SchemaField("purchases", "INT64"),
    bigquery.SchemaField("purchase_revenue", "NUMERIC"),
    bigquery.SchemaField("currency_code", "STRING"),
    bigquery.SchemaField("window_start", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("window_end", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("pulled_at", "TIMESTAMP", mode="REQUIRED"),
]


def reporting_window(today: date | None = None) -> tuple[date, date]:
    """Return only T-4, excluding the latest three complete dates."""
    current = today or datetime.now(ZoneInfo(TIME_ZONE)).date()
    end_date = current - timedelta(days=EXCLUDE_RECENT_DAYS + 1)
    return end_date, end_date


def _as_int(value: str) -> int:
    return int(round(float(value or 0)))


def _as_float(value: str) -> float:
    return float(value or 0)


def fetch_ga4(start_date: date, end_date: date) -> List[Dict]:
    client = BetaAnalyticsDataClient()
    request = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name=name) for name in GA4_METRICS],
        date_ranges=[DateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat())],
        limit=100000,
    )
    response = client.run_report(request)
    metric_names = [header.name for header in response.metric_headers]
    by_date: Dict[str, Dict] = {}
    pulled_at = datetime.now(timezone.utc).isoformat()

    for row in response.rows:
        values = {name: row.metric_values[i].value for i, name in enumerate(metric_names)}
        raw_date = row.dimension_values[0].value
        iso_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        sessions = _as_int(values["sessions"])
        engagement_seconds = _as_float(values["userEngagementDuration"])
        by_date[iso_date] = {
            "date": iso_date,
            "property_id": GA4_PROPERTY_ID,
            "active_users": _as_int(values["activeUsers"]),
            "new_users": _as_int(values["newUsers"]),
            "sessions": sessions,
            "views": _as_int(values["screenPageViews"]),
            "engaged_sessions": _as_int(values["engagedSessions"]),
            "engagement_rate": _as_float(values["engagementRate"]),
            "avg_engagement_seconds": engagement_seconds / sessions if sessions else 0,
            "purchasers": _as_int(values["totalPurchasers"]),
            "purchases": _as_int(values["ecommercePurchases"]),
            "purchase_revenue": str(Decimal(values["purchaseRevenue"] or "0")),
            "currency_code": response.metadata.currency_code or "USD",
            "window_start": start_date.isoformat(),
            "window_end": end_date.isoformat(),
            "pulled_at": pulled_at,
        }

    iso_date = start_date.isoformat()
    if iso_date not in by_date:
        by_date[iso_date] = {
            "date": iso_date,
            "property_id": GA4_PROPERTY_ID,
            "active_users": 0,
            "new_users": 0,
            "sessions": 0,
            "views": 0,
            "engaged_sessions": 0,
            "engagement_rate": 0,
            "avg_engagement_seconds": 0,
            "purchasers": 0,
            "purchases": 0,
            "purchase_revenue": "0",
            "currency_code": response.metadata.currency_code or "USD",
            "window_start": start_date.isoformat(),
            "window_end": end_date.isoformat(),
            "pulled_at": pulled_at,
        }

    rows = [by_date[key] for key in sorted(by_date)]
    if len(rows) != 1:
        raise RuntimeError(f"Expected one T-4 daily row, got {len(rows)}")
    return rows


def ensure_bigquery(client: bigquery.Client) -> tuple[str, str]:
    dataset_id = f"{PROJECT_ID}.{BIGQUERY_DATASET}"
    table_id = f"{dataset_id}.{BIGQUERY_TABLE}"
    stage_id = f"{dataset_id}.{BIGQUERY_TABLE}_stage"

    try:
        client.get_dataset(dataset_id)
    except NotFound:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = os.getenv("BIGQUERY_LOCATION", "asia-east1")
        client.create_dataset(dataset)

    try:
        client.get_table(table_id)
    except NotFound:
        table = bigquery.Table(table_id, schema=BQ_SCHEMA)
        table.time_partitioning = bigquery.TimePartitioning(field="date")
        table.clustering_fields = ["property_id"]
        client.create_table(table)

    return table_id, stage_id


def upsert_bigquery(rows: List[Dict]) -> None:
    client = bigquery.Client(project=PROJECT_ID)
    table_id, stage_id = ensure_bigquery(client)
    job_config = bigquery.LoadJobConfig(schema=BQ_SCHEMA, write_disposition="WRITE_TRUNCATE")
    client.load_table_from_json(rows, stage_id, job_config=job_config).result()

    columns = [field.name for field in BQ_SCHEMA]
    update_columns = [column for column in columns if column not in {"date", "property_id"}]
    update_clause = ",\n      ".join(f"T.{column} = S.{column}" for column in update_columns)
    insert_columns = ", ".join(columns)
    insert_values = ", ".join(f"S.{column}" for column in columns)
    query = f"""
    MERGE `{table_id}` T
    USING `{stage_id}` S
    ON T.date = S.date AND T.property_id = S.property_id
    WHEN MATCHED THEN UPDATE SET
      {update_clause}
    WHEN NOT MATCHED THEN INSERT ({insert_columns})
    VALUES ({insert_values})
    """
    client.query(query).result()


def chunks(items: List[Dict], size: int) -> Iterable[List[Dict]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def upsert_airtable(rows: List[Dict]) -> int:
    token = os.environ["AIRTABLE_TOKEN"]
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    sync_time = datetime.now(timezone.utc).isoformat()
    records = []
    note = (
        "GA4 Data API自动同步；已排除最近3个完整自然日。"
        "GA4为行为与平台归因口径，订单及净收入以Shopify为准。"
    )

    for row in rows:
        day = row["date"]
        records.append(
            {
                "fields": {
                    FIELDS["key"]: f"{day}|全站|全站||",
                    FIELDS["date"]: day,
                    FIELDS["grain"]: "全站",
                    FIELDS["dimension"]: "全站",
                    FIELDS["active_users"]: row["active_users"],
                    FIELDS["new_users"]: row["new_users"],
                    FIELDS["sessions"]: row["sessions"],
                    FIELDS["engaged_sessions"]: row["engaged_sessions"],
                    FIELDS["engagement_rate"]: row["engagement_rate"],
                    FIELDS["avg_engagement_seconds"]: row["avg_engagement_seconds"],
                    FIELDS["views"]: row["views"],
                    FIELDS["purchasers"]: row["purchasers"],
                    FIELDS["purchases"]: row["purchases"],
                    FIELDS["purchase_revenue"]: float(row["purchase_revenue"]),
                    FIELDS["sync_source"]: "GA4 Data API",
                    FIELDS["last_sync"]: sync_time,
                    FIELDS["notes"]: note,
                }
            }
        )

    written = 0
    for batch in chunks(records, 10):
        payload = {
            "performUpsert": {"fieldsToMergeOn": [FIELDS["key"]]},
            "records": batch,
            "typecast": False,
        }
        response = requests.patch(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        written += len(response.json().get("records", []))
    return written


def execute_sync() -> Dict:
    missing = [
        name
        for name, value in {
            "PROJECT_ID": PROJECT_ID,
            "GA4_PROPERTY_ID": GA4_PROPERTY_ID,
            "AIRTABLE_BASE_ID": AIRTABLE_BASE_ID,
            "AIRTABLE_TOKEN": os.getenv("AIRTABLE_TOKEN", ""),
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")
    start_date, end_date = reporting_window()
    logger.info("Starting GA4 sync for %s through %s", start_date, end_date)
    rows = fetch_ga4(start_date, end_date)
    upsert_bigquery(rows)
    written = upsert_airtable(rows)
    result = {
        "status": "ok",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "rows_fetched": len(rows),
        "airtable_rows_written": written,
        "purchases": sum(row["purchases"] for row in rows),
        "purchase_revenue": float(sum(Decimal(row["purchase_revenue"]) for row in rows)),
    }
    logger.info(json.dumps(result, ensure_ascii=False))
    return result


@app.route("/", methods=["GET", "POST"])
def run_sync():
    try:
        return jsonify(execute_sync()), 200
    except Exception as exc:
        logger.exception("GA4 sync failed")
        return jsonify({"status": "error", "error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
