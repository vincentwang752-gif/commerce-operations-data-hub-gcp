from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "google_ads_sync.py"
SPEC = importlib.util.spec_from_file_location("google_ads_sync", MODULE_PATH)
sync = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)


def test_account_allowlist_supports_brand_and_agency_accounts():
    accounts = sync.load_accounts(
        json.dumps(
            [
                {"alias": "brand_us", "customer_id": "111-222-3333", "account_type": "brand_managed"},
                {
                    "alias": "agency_us",
                    "customer_id": "4445556666",
                    "login_customer_id": "9998887777",
                    "account_type": "agency_managed",
                    "agency": "example_agency",
                },
            ]
        )
    )
    assert [item.account_type for item in accounts] == ["brand_managed", "agency_managed"]
    assert accounts[0].customer_id == "1112223333"
    assert accounts[1].login_customer_id == "9998887777"


def test_duplicate_accounts_are_rejected():
    raw = json.dumps(
        [
            {"customer_id": "111", "account_type": "brand_managed"},
            {"customer_id": "111", "account_type": "agency_managed"},
        ]
    )
    with pytest.raises(ValueError, match="duplicate"):
        sync.load_accounts(raw)


def test_stable_keys_are_deterministic():
    assert sync.campaign_key("123", 45) == "google_ads|123|45"
    assert sync.ad_group_key("123", 67) == "google_ads|123|67"
    assert sync.ad_key("123", 89) == "google_ads|123|89"
    assert sync.daily_key("2026-08-27", "123", 89) == "2026-08-27|google_ads|123|89"
    assert sync.daily_key("2026-08-27", "123", 89) == sync.daily_key("2026-08-27", "123", 89)


def test_every_platform_request_is_a_select_report():
    queries = [
        sync.ACCOUNT_QUERY,
        sync.CAMPAIGN_QUERY,
        sync.AD_GROUP_QUERY,
        sync.AD_QUERY,
        sync.DAILY_PERFORMANCE_QUERY,
    ]
    assert all(query.lstrip().startswith("SELECT") for query in queries)


class FakeService:
    def __init__(self):
        self.queries = []

    def search_stream(self, customer_id, query):
        self.queries.append((customer_id, query))
        if "FROM customer" in query:
            customer = SimpleNamespace(
                id=123,
                descriptive_name="Example",
                currency_code="USD",
                time_zone="America/Los_Angeles",
            )
            return [SimpleNamespace(results=[SimpleNamespace(customer=customer)])]
        return [SimpleNamespace(results=[object(), object()])]


class FakeClient:
    def __init__(self):
        self.service = FakeService()

    def get_service(self, name):
        assert name == "GoogleAdsService"
        return self.service


def test_dry_run_counts_all_report_levels_and_preserves_metadata(monkeypatch):
    monkeypatch.setenv("READ_ONLY", "true")
    account = sync.AccountConfig("brand_us", "123", "brand_managed")
    client = FakeClient()
    result = sync.run_dry_run(account, date(2026, 8, 27), date(2026, 8, 27), client)
    assert result["currency"] == "USD"
    assert result["timezone"] == "America/Los_Angeles"
    assert result["row_counts"] == {
        "accounts": 1,
        "campaigns": 2,
        "ad_groups": 2,
        "ads": 2,
        "daily_performance": 2,
    }
    assert result["writes"] == 0
    assert all(customer_id == "123" for customer_id, _ in client.service.queries)
    assert any("segments.date BETWEEN '2026-08-27' AND '2026-08-27'" in q for _, q in client.service.queries)


def test_read_only_cannot_be_disabled(monkeypatch):
    monkeypatch.setenv("READ_ONLY", "false")
    account = sync.AccountConfig("brand_us", "123", "brand_managed")
    with pytest.raises(RuntimeError, match="READ_ONLY=true"):
        sync.run_dry_run(account, date(2026, 8, 27), date(2026, 8, 27), FakeClient())
