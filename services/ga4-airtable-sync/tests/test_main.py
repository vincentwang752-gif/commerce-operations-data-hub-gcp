from datetime import date

from main import chunks, reporting_window


def test_reporting_window_excludes_latest_three_complete_dates():
    start_date, end_date = reporting_window(date(2026, 8, 24))
    assert end_date == date(2026, 8, 20)
    assert start_date == date(2026, 8, 20)


def test_chunks_batches_for_airtable_limit():
    items = list(range(90))
    batches = list(chunks(items, 10))
    assert len(batches) == 9
    assert all(len(batch) == 10 for batch in batches)


def test_field_mapping_uses_names_not_production_ids():
    from main import FIELDS

    assert FIELDS["date"] == "日期"
    assert all(not value.startswith("fld") for value in FIELDS.values())
