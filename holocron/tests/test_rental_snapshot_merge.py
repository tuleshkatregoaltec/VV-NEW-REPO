from copy import deepcopy
from datetime import timedelta

from holocron.sources.dxbi.rental_events import merge_rental_snapshots, normalize_rental_rows


def snapshot(*units: str, run: str = "old") -> list[dict]:
    payloads = []
    for unit in units:
        payload = {
            "source_account": "account-b",
            "filter_profile": {"id": "broad"},
            "source_location": {"id": "1"},
            "configuration_hash": "12345678901234567890",
            "shard": {"date": "2026-07-01"},
            "scraped_at": "2026-07-02T00:00:00+00:00",
            "columns": [
                {"id": "PATH_NAME", "text": ""},
                {"id": "PROP_SIZES", "text": "1 Bed 732 sqft"},
                {"id": "TOTAL_PRICES", "text": "38,000 Renewed"},
                {"id": "START_DATE", "text": "1 Jul, 2026 - 30 Jun, 2027 12 Months"},
            ],
        }
        payload["source_run_id"] = run
        payload["columns"][0]["text"] = "L-07, Greece Cluster, International City Apartment" + (
            f", No. {unit}" if unit else ""
        )
        payloads.append((payload, f"/{run}/date=2026-07-01/a.jsonl", "account-b"))
    return normalize_rental_rows(payloads).events


def test_newly_visible_unit_replaces_the_hidden_snapshot():
    old = snapshot("")
    new = snapshot("1204", run="new")
    result = merge_rental_snapshots(old + new)
    assert len(result) == 1
    assert result[0]["unit_number"] == "1204"
    assert merge_rental_snapshots(result + new) == result


def test_hidden_multiplicity_survives_repeated_partial_snapshots():
    old = snapshot("", "", "")
    new = snapshot("1204", run="new")
    result = merge_rental_snapshots(old + new)
    assert len(result) == 3
    for _ in range(3):
        result = merge_rental_snapshots(result + new)
        assert len(result) == 3
    fuller = snapshot("1204", "1205", "1206", run="full")
    result = merge_rental_snapshots(result + fuller)
    assert len(result) == 3
    assert all(row["unit_number"] for row in result)


def test_mixed_same_snapshot_retains_unidentified_occurrence_when_known_row_moves():
    old = snapshot("1204", "")
    new = deepcopy(snapshot("1204", run="new"))
    new[0]["scraped_at"] = old[0]["scraped_at"] + timedelta(days=1)
    result = merge_rental_snapshots(old + new)
    assert len(result) == 2
    assert len(merge_rental_snapshots(result + new)) == 2


def test_distinct_units_and_different_lease_amounts_are_preserved():
    known = snapshot("1204", "1205")
    hidden = snapshot("", run="new")
    hidden[0]["contract_amount_aed"] += 1
    assert len(merge_rental_snapshots(known + hidden)) == 3


def test_database_naive_utc_and_raw_aware_timestamps_can_be_merged():
    old = snapshot("1204")
    old[0]["scraped_at"] = old[0]["scraped_at"].replace(tzinfo=None)
    new = snapshot("1204", run="new")
    assert len(merge_rental_snapshots(old + new)) == 1
