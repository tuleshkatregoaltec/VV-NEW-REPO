from datetime import date

from holocron.sources.dxbi.rental_events import (
    canonical_area_name,
    normalize_rental_row,
    normalize_rental_rows,
)


def test_canonical_area_name_collapses_safe_market_aliases() -> None:
    assert canonical_area_name("Dubai South (Dubai World Central)") == "Dubai South"
    assert canonical_area_name("Dubai Investment Park (DIP)") == "Dubai Investment Park"
    assert canonical_area_name("Al Barshaa South 3") == "Al Barsha South 3"
    assert canonical_area_name("Za'Abeel 1") == "Zabeel 1"


def test_normalize_rental_row_builds_stable_owner_period_candidate() -> None:
    payload = {
        "transaction_type": "rentals",
        "shard": {"date": "2026-07-01"},
        "columns": [
            {
                "id": "PATH_NAME",
                "text": "L-07, Greece Cluster, International City Apartment , Floor No. u-hidden , No.",
            },
            {"id": "PROP_SIZES", "text": "1 Bed 732 sqft"},
            {"id": "TOTAL_PRICES", "text": "38,000 +8.26% Renewed"},
            {"id": "START_DATE", "text": "1 Jul, 2026 - 30 Jun, 2027 12 Months"},
            {"id": "PURCHASE_PRICE", "text": "AED 460K"},
        ],
        "scraped_at": "2026-07-25T22:36:20.321504+00:00",
    }

    event = normalize_rental_row(payload, source_account="account-b")

    assert event is not None
    assert event["building_name"] == "L-07"
    assert event["project_name"] == "Greece Cluster"
    assert event["area_name"] == "International City"
    assert event["property_type"] == "Apartment"
    assert event["bedrooms"] == "1 Bed"
    assert event["size_sqft"] == 732
    assert event["contract_amount_aed"] == 38_000
    assert event["contract_term_months"] == 12
    assert event["annual_rent_aed"] == 38_000
    assert event["purchase_price_aed"] == 460_000
    assert event["lease_start"] == date(2026, 7, 1)
    assert event["lease_end"] == date(2027, 6, 30)
    assert event["contract_state"] == "Renewed"
    assert event["source_account"] == "account-b"


def test_purchase_price_changes_candidate_not_physical_cohort() -> None:
    base = {
        "columns": [
            {"id": "PATH_NAME", "text": "Ritaj A, Ritaj, DIP Apartment, Floor No. u-hidden"},
            {"id": "PROP_SIZES", "text": "Studio 450 sqft"},
            {"id": "TOTAL_PRICES", "text": "42,000 New"},
            {"id": "START_DATE", "text": "8 Mar, 2025 - 7 Mar, 2026 12 Months"},
            {"id": "PURCHASE_PRICE", "text": "AED 440K"},
        ]
    }
    sold = {
        **base,
        "columns": [
            *base["columns"][:-1],
            {"id": "PURCHASE_PRICE", "text": "AED 525K"},
        ],
    }

    first = normalize_rental_row(base)
    second = normalize_rental_row(sold)

    assert first is not None and second is not None
    assert first["unit_cohort_key"] == second["unit_cohort_key"]
    assert first["unit_candidate_key"] != second["unit_candidate_key"]
    assert first["contract_key"] == second["contract_key"]


def test_short_contract_amount_is_annualized() -> None:
    payload = {
        "columns": [
            {
                "id": "PATH_NAME",
                "text": "Tower 108, Jumeirah Village Circle (JVC) Apartment",
            },
            {"id": "PROP_SIZES", "text": "Studio 450 sqft"},
            {"id": "TOTAL_PRICES", "text": "18,000 New"},
            {"id": "START_DATE", "text": "1 Jan, 2026 - 31 Mar, 2026 3 Months"},
        ]
    }

    event = normalize_rental_row(payload)

    assert event is not None
    assert event["area_name"] == "Jumeirah Village Circle"
    assert event["contract_amount_aed"] == 18_000
    assert event["annual_rent_aed"] == 72_000


def test_villa_phase_is_not_classified_as_a_building() -> None:
    payload = {
        "columns": [
            {
                "id": "PATH_NAME",
                "text": "Sun, Arabian Ranches 3, Wadi Al Safa 5 Villa",
            },
            {"id": "PROP_SIZES", "text": "3 Bed 1,940 sqft"},
            {"id": "TOTAL_PRICES", "text": "180,000 New"},
            {"id": "START_DATE", "text": "1 Jan, 2026 - 31 Dec, 2026 12 Months"},
        ]
    }

    event = normalize_rental_row(payload)

    assert event is not None
    assert event["building_name"] == ""
    assert event["project_name"] == "Sun"
    assert event["area_name"] == "Arabian Ranches 3"


def test_villa_path_markers_do_not_leak_into_the_area_name() -> None:
    payload = {
        "columns": [
            {
                "id": "PATH_NAME",
                "text": "Diamond View 1, 2, 3, 4, Jumeirah Village Circle (JVC) Villa",
            },
            {"id": "PROP_SIZES", "text": "4 Bed 3,200 sqft"},
            {"id": "TOTAL_PRICES", "text": "220,000 New"},
            {"id": "START_DATE", "text": "1 Jan, 2026 - 31 Dec, 2026 12 Months"},
        ]
    }

    event = normalize_rental_row(payload)

    assert event is not None
    assert event["building_name"] == ""
    assert event["project_name"] == "Diamond View 1"
    assert event["area_name"] == "Jumeirah Village Circle"


def test_area_aliases_and_ordinals_are_canonicalized() -> None:
    assert canonical_area_name("Dubai Hills") == "Dubai Hills Estate"
    assert canonical_area_name("Dubai Hills Estate") == "Dubai Hills Estate"
    assert canonical_area_name("Al Barsha First") == "Al Barsha 1"
    assert canonical_area_name("Al Barsha South Fourth") == "Al Barsha South 4"


def test_visible_unit_and_hidden_source_id_are_preserved() -> None:
    payload = {
        "row_attributes": {"data-contract-id": "rent-99117", "class": "report-row"},
        "hidden_attributes": {"internal_record": "opaque-7"},
        "columns": [
            {
                "id": "PATH_NAME",
                "text": (
                    "L-07, Greece Cluster, International City Apartment, "
                    "Floor No. u-hidden, No. 1204"
                ),
            },
            {"id": "PROP_SIZES", "text": "1 Bed 732 sqft"},
            {"id": "TOTAL_PRICES", "text": "38,000 New"},
            {"id": "START_DATE", "text": "1 Jul, 2026 - 30 Jun, 2027 12 Months"},
        ],
    }

    event = normalize_rental_row(payload)

    assert event is not None
    assert event["unit_number"] == "1204"
    assert event["source_contract_id"] == "rent-99117"
    assert '"internal_record":"opaque-7"' in event["raw_attributes_json"]


def test_hidden_unit_marker_is_not_treated_as_an_identity() -> None:
    payload = {
        "columns": [
            {
                "id": "PATH_NAME",
                "text": "Ritaj A, Ritaj, DIP Apartment, Floor No. u-hidden",
            },
            {"id": "PROP_SIZES", "text": "Studio 450 sqft"},
            {"id": "TOTAL_PRICES", "text": "42,000 New"},
            {"id": "START_DATE", "text": "8 Mar, 2025 - 7 Mar, 2026 12 Months"},
        ]
    }

    event = normalize_rental_row(payload)

    assert event is not None
    assert event["unit_number"] == ""


def test_duplicate_visible_rows_get_deterministic_occurrence_keys() -> None:
    payload = {
        "source_account": "account-b",
        "filter_profile": {"id": "broad"},
        "source_location": {"id": "1"},
        "configuration_hash": "12345678901234567890",
        "columns": [
            {"id": "PATH_NAME", "text": "Tower 108, JVC Apartment, No. 1701"},
            {"id": "PROP_SIZES", "text": "Studio 450 sqft"},
            {"id": "TOTAL_PRICES", "text": "42,000 New"},
            {"id": "START_DATE", "text": "8 Mar, 2025 - 7 Mar, 2026 12 Months"},
        ],
    }

    result = normalize_rental_rows([(payload, "a.jsonl", ""), (payload, "a.jsonl", "")])

    assert result.raw_rows == result.normalized_rows + len(result.quarantined)
    assert result.unique_source_rows == 2
    assert [event["occurrence_index"] for event in result.events] == [1, 2]
    assert len({event["contract_key"] for event in result.events}) == 2


def test_overlapping_profiles_collapse_to_the_source_multiset() -> None:
    base = {
        "source_account": "account-b",
        "source_location": {"id": "1"},
        "columns": [
            {"id": "PATH_NAME", "text": "Tower 108, JVC Apartment, No. 1701"},
            {"id": "PROP_SIZES", "text": "Studio 450 sqft"},
            {"id": "TOTAL_PRICES", "text": "42,000 New"},
            {"id": "START_DATE", "text": "8 Mar, 2025 - 7 Mar, 2026 12 Months"},
        ],
    }
    broad = {
        **base,
        "filter_profile": {"id": "broad"},
        "configuration_hash": "12345678901234567890",
    }
    apartment = {
        **base,
        "filter_profile": {"id": "property-apartment"},
        "configuration_hash": "abcdefghijklmnopqrst",
    }

    result = normalize_rental_rows([(broad, "broad.jsonl", ""), (apartment, "apartment.jsonl", "")])

    assert result.raw_rows == 2
    assert result.normalized_rows == 2
    assert result.unique_source_rows == 1
    assert result.profile_overlap == 1
    assert len(result.events) == 1
    assert result.events[0]["filter_profile_id"] == "broad"


def test_malformed_row_is_quarantined_without_a_silent_skip() -> None:
    result = normalize_rental_rows([({"columns": []}, "bad.jsonl", "account-b")])

    assert result.raw_rows == 1
    assert result.normalized_rows == 0
    assert len(result.quarantined) == 1
    assert result.events == []
