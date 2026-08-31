"""Read-only Google Ads reporting bootstrap.

All credentials and customer identifiers are supplied at runtime. The default
execution mode is a dry run that only counts GAQL report rows.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Iterator, Mapping, Sequence

from google.ads.googleads.client import GoogleAdsClient


LOGGER = logging.getLogger("google_ads_sync")
PLATFORM = "google_ads"
ACCOUNT_TYPES = {"brand_managed", "agency_managed"}


ACCOUNT_QUERY = """
SELECT
  customer.id,
  customer.descriptive_name,
  customer.currency_code,
  customer.time_zone
FROM customer
LIMIT 1
"""

CAMPAIGN_QUERY = """
SELECT
  customer.id,
  customer.currency_code,
  customer.time_zone,
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  campaign_budget.amount_micros
FROM campaign
"""

AD_GROUP_QUERY = """
SELECT
  customer.id,
  customer.currency_code,
  customer.time_zone,
  campaign.id,
  ad_group.id,
  ad_group.name,
  ad_group.status,
  ad_group.type
FROM ad_group
"""

AD_QUERY = """
SELECT
  customer.id,
  customer.currency_code,
  customer.time_zone,
  campaign.id,
  ad_group.id,
  ad_group_ad.ad.id,
  ad_group_ad.ad.name,
  ad_group_ad.ad.type,
  ad_group_ad.ad.final_urls,
  ad_group_ad.ad.tracking_url_template,
  ad_group_ad.ad.final_url_suffix,
  ad_group_ad.status
FROM ad_group_ad
"""

DAILY_PERFORMANCE_QUERY = """
SELECT
  segments.date,
  customer.id,
  customer.currency_code,
  customer.time_zone,
  campaign.id,
  ad_group.id,
  ad_group_ad.ad.id,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM ad_group_ad
WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
"""


@dataclass(frozen=True)
class AccountConfig:
    alias: str
    customer_id: str
    account_type: str
    login_customer_id: str | None = None
    agency: str | None = None

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any], index: int) -> "AccountConfig":
        customer_id = str(item.get("customer_id", "")).replace("-", "").strip()
        account_type = str(item.get("account_type", "")).strip()
        alias = str(item.get("alias") or f"account_{index + 1}").strip()
        login_id = str(item.get("login_customer_id", "")).replace("-", "").strip()
        if not customer_id.isdigit():
            raise ValueError(f"{alias}: customer_id must contain digits only")
        if account_type not in ACCOUNT_TYPES:
            raise ValueError(f"{alias}: unsupported account_type {account_type!r}")
        if login_id and not login_id.isdigit():
            raise ValueError(f"{alias}: login_customer_id must contain digits only")
        return cls(
            alias=alias,
            customer_id=customer_id,
            account_type=account_type,
            login_customer_id=login_id or None,
            agency=str(item.get("agency") or "").strip() or None,
        )


def load_accounts(raw: str | None = None) -> list[AccountConfig]:
    """Load the approved account allowlist from a runtime-only JSON value."""
    value = raw if raw is not None else os.getenv("GOOGLE_ADS_ACCOUNTS_JSON", "")
    if not value:
        raise RuntimeError("GOOGLE_ADS_ACCOUNTS_JSON is required")
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("GOOGLE_ADS_ACCOUNTS_JSON must be a non-empty JSON array")
    accounts = [AccountConfig.from_mapping(item, i) for i, item in enumerate(parsed)]
    if len({account.customer_id for account in accounts}) != len(accounts):
        raise ValueError("GOOGLE_ADS_ACCOUNTS_JSON contains duplicate customer_id values")
    return accounts


def load_client(account: AccountConfig) -> GoogleAdsClient:
    """Build an SDK client exclusively from runtime environment variables."""
    required = {
        "GOOGLE_ADS_DEVELOPER_TOKEN": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
        "GOOGLE_ADS_CLIENT_ID": os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
        "GOOGLE_ADS_CLIENT_SECRET": os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
        "GOOGLE_ADS_REFRESH_TOKEN": os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing runtime secrets: {', '.join(missing)}")
    config: dict[str, Any] = {
        "developer_token": required["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": required["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": required["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": required["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
    }
    if account.login_customer_id:
        config["login_customer_id"] = account.login_customer_id
    return GoogleAdsClient.load_from_dict(config)


def _rows(client: GoogleAdsClient, customer_id: str, query: str) -> Iterator[Any]:
    service = client.get_service("GoogleAdsService")
    for batch in service.search_stream(customer_id=customer_id, query=query):
        yield from batch.results


def campaign_key(customer_id: str, campaign_id: int | str) -> str:
    return f"{PLATFORM}|{customer_id}|{campaign_id}"


def ad_group_key(customer_id: str, ad_group_id: int | str) -> str:
    return f"{PLATFORM}|{customer_id}|{ad_group_id}"


def ad_key(customer_id: str, ad_id: int | str) -> str:
    return f"{PLATFORM}|{customer_id}|{ad_id}"


def daily_key(day: date | str, customer_id: str, ad_id: int | str) -> str:
    return f"{day}|{PLATFORM}|{customer_id}|{ad_id}"


def account_record(row: Any, config: AccountConfig) -> dict[str, Any]:
    return {
        "platform": PLATFORM,
        "account_id": str(row.customer.id),
        "account_alias": config.alias,
        "account_type": config.account_type,
        "agency": config.agency,
        "account_name": row.customer.descriptive_name,
        "currency": row.customer.currency_code,
        "timezone": row.customer.time_zone,
    }


def count_rows(rows: Iterable[Any]) -> int:
    return sum(1 for _ in rows)


def default_window(today: date | None = None) -> tuple[date, date]:
    """Use the last mature day (T-4) until production policy chooses otherwise."""
    target = (today or date.today()) - timedelta(days=4)
    return target, target


def run_dry_run(
    account: AccountConfig,
    start_date: date,
    end_date: date,
    client: GoogleAdsClient | None = None,
) -> dict[str, Any]:
    if os.getenv("READ_ONLY", "true").lower() != "true":
        raise RuntimeError("READ_ONLY=true is required")
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    ads_client = client or load_client(account)
    account_rows = list(_rows(ads_client, account.customer_id, ACCOUNT_QUERY))
    if len(account_rows) != 1:
        raise RuntimeError(f"{account.alias}: expected one account row, got {len(account_rows)}")
    metadata = account_record(account_rows[0], account)
    if metadata["account_id"] != account.customer_id:
        raise RuntimeError(f"{account.alias}: report returned an unapproved customer")
    queries = {
        "accounts": account_rows,
        "campaigns": _rows(ads_client, account.customer_id, CAMPAIGN_QUERY),
        "ad_groups": _rows(ads_client, account.customer_id, AD_GROUP_QUERY),
        "ads": _rows(ads_client, account.customer_id, AD_QUERY),
        "daily_performance": _rows(
            ads_client,
            account.customer_id,
            DAILY_PERFORMANCE_QUERY.format(
                start_date=start_date.isoformat(), end_date=end_date.isoformat()
            ),
        ),
    }
    counts = {name: count_rows(rows) for name, rows in queries.items()}
    return {
        "account_alias": account.alias,
        "account_type": metadata["account_type"],
        "currency": metadata["currency"],
        "timezone": metadata["timezone"],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "row_counts": counts,
        "mode": "dry_run",
        "writes": 0,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    default_start, default_end = default_window()
    parser = argparse.ArgumentParser(description="Google Ads reporting dry run")
    parser.add_argument("--start-date", type=date.fromisoformat, default=default_start)
    parser.add_argument("--end-date", type=date.fromisoformat, default=default_end)
    parser.add_argument("--dry-run", action="store_true", default=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.dry_run:
        raise RuntimeError("This bootstrap supports dry run only")
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    summaries = [run_dry_run(account, args.start_date, args.end_date) for account in load_accounts()]
    print(json.dumps({"status": "ok", "accounts": summaries}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
