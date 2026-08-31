import importlib
import os
from unittest.mock import Mock, patch


os.environ.setdefault("AIRTABLE_TOKEN", "test-token")
os.environ.setdefault("VOC_WEBHOOK_TOKEN", "test-webhook")
os.environ.setdefault("ELIGIBLE_PRODUCT_TERMS", "example product")

main = importlib.import_module("main")


def test_health():
    response = main.app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_rejects_bad_token():
    response = main.app.test_client().post("/form-submit", json={"stage": 1})
    assert response.status_code == 401


def test_rejects_ineligible_profile_without_event():
    with patch.object(main, "_find_customer", return_value=None), patch.object(
        main, "_find_eligible_order", return_value=None
    ), patch.object(
        main, "_recover_eligible_order", return_value=None
    ), patch.object(main, "_send_klaviyo_event") as send_event:
        response = main.app.test_client().post(
            "/form-submit",
            headers={"X-VOC-Token": "test-webhook"},
            json={"stage": 1, "email": "test@example.com", "response_id": "row-2"},
        )
    assert response.status_code == 422
    assert response.get_json()["status"] == "INELIGIBLE"
    send_event.assert_not_called()


def test_recovers_missing_order_before_completing_survey():
    recovered = {"id": "recOrder", "fields": {main.ORDER_ID: "1002"}}
    customer = {"id": "recCustomer", "fields": {main.CUSTOMER_LIFECYCLE_LINKS: []}}
    with patch.object(main, "_find_eligible_order", return_value=None), patch.object(
        main, "_recover_eligible_order", return_value=recovered
    ) as recover, patch.object(main, "_find_customer", return_value=customer), patch.object(
        main, "_upsert_lifecycle", return_value="recLifecycle"
    ), patch.object(main, "_send_klaviyo_event"):
        response = main.app.test_client().post(
            "/form-submit",
            headers={"X-VOC-Token": "test-webhook"},
            json={"stage": 1, "email": "test@example.com", "response_id": "row-9"},
        )
    assert response.status_code == 200
    assert response.get_json()["recovered_order"] is True
    recover.assert_called_once_with("test@example.com")


def test_stage1_updates_airtable_then_emits_event():
    customer = {"id": "recCustomer", "fields": {main.CUSTOMER_LIFECYCLE_LINKS: ["recLifecycle"]}}
    order = {"id": "recOrder", "fields": {main.ORDER_ID: "1001"}}
    with patch.object(main, "_find_customer", return_value=customer), patch.object(
        main, "_find_eligible_order", return_value=order
    ), patch.object(main, "_upsert_lifecycle", return_value="recLifecycle") as upsert, patch.object(
        main, "_send_klaviyo_event"
    ) as send_event:
        response = main.app.test_client().post(
            "/form-submit",
            headers={"X-VOC-Token": "test-webhook"},
            json={
                "stage": 1,
                "email": "test@example.com",
                "response_id": "row-2",
                "completed_at": "2026-08-25T10:00:00+00:00",
            },
        )
    assert response.status_code == 200
    upsert.assert_called_once()
    send_event.assert_called_once()
    assert response.get_json()["status"] == "SYNCED"


def test_unique_id_is_stable():
    first = main._event_unique_id(1, "Test@Example.com", "row-2")
    second = main._event_unique_id(1, "test@example.com", "row-2")
    assert first == second


def test_normalizes_apps_script_date_for_klaviyo():
    assert (
        main._normalize_datetime(
            "Wed Aug 26 2026 14:29:00 GMT+0800 (China Standard Time)"
        )
        == "2026-08-26T06:29:00Z"
    )


def test_normalizes_iso_date_for_klaviyo():
    assert main._normalize_datetime("2026-08-25T10:00:00+00:00") == "2026-08-25T10:00:00Z"


def test_eligible_order_uses_configured_terms():
    assert main._is_eligible_order({main.ORDER_MAIN_PRODUCT: "Example Product Starter Kit"})
    assert not main._is_eligible_order({main.ORDER_MAIN_PRODUCT: "Different Product"})
