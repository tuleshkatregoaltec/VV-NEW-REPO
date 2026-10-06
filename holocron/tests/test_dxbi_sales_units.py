from datetime import date

from holocron.sources.dxbi.sales_units import compact_payload, location_key, normalize_sales_row


def test_normalize_sales_row_preserves_unit_and_purchase_evidence() -> None:
    payload = {
        "unit_number": "R08",
        "location_text": (
            "Buyer's agent Binghatti Hillcrest, Arjan Offplan Apartment, "
            "Floor u-hidden, No. R08"
        ),
        "amount_text": "AED 1,315,999 (-) AED 1,823 /sqft u-hidden% LTV",
        "specs_text": "722 sqft • - sqft BUA 1 Bed Balcony 149 sqft",
        "date_text": "04, Jul 2026 Developer (u-hidden)",
        "detail_url": "https://dxbinteract.com/sold/t-sqy1sjc3y",
    }

    event = normalize_sales_row(payload)

    assert event is not None
    assert event["unit_number"] == "R08"
    assert event["building_name"] == "Binghatti Hillcrest"
    assert event["area_name"] == "Arjan"
    assert event["property_type"] == "Apartment"
    assert event["bedrooms"] == "1 Bed"
    assert event["size_sqft"] == 722
    assert event["sale_amount_aed"] == 1_315_999
    assert event["price_per_sqft_aed"] == 1_823
    assert event["capital_gain_pct"] is None
    assert event["ltv_pct"] is None
    assert event["market_status"] == "Offplan"
    assert event["seller_type"] == "Developer"
    assert event["seller_transaction_count"] is None
    assert event["agent_side"] == "buyer"
    assert event["balcony_sqft"] == 149
    assert event["built_up_area_sqft"] is None
    assert event["transaction_date"] == date(2026, 7, 4)


def test_location_key_normalizes_common_dxbi_spelling_variants() -> None:
    assert location_key("Muraba Residences Palm Jumeriah") == location_key(
        "Muraba Residence Palm Jumeirah"
    )


def test_sales_area_uses_same_canonical_vocabulary_as_rentals() -> None:
    event = normalize_sales_row(
        {
            "unit_number": "602",
            "location_text": (
                "Tower 108, Jumeirah Village Circle (JVC) Ready Apartment, Floor 6"
            ),
            "amount_text": "AED 900,000 AED 2,000 /sqft",
            "specs_text": "450 sqft Studio",
            "date_text": "01, Jan 2026 Individual",
        }
    )

    assert event is not None
    assert event["area_name"] == "Jumeirah Village Circle"
    assert event["area_key"] == "jumeirahvillagecircle"


def test_compact_payload_ignores_large_columns_array() -> None:
    payload = compact_payload(
        '{"unit_number":"302","location_text":"Tower, Area Ready Apartment, Floor 2",'
        '"columns":[{"html":"large"}]}'
    )

    assert payload == {
        "unit_number": "302",
        "location_text": "Tower, Area Ready Apartment, Floor 2",
    }


def test_compact_payload_adapts_current_raw_report_columns() -> None:
    payload = compact_payload(
        '{"transaction_type":"sales","columns":['
        '{"id":"PATH_NAME","text":"Buyer\'s agent Tower One, Business Bay Ready '
        'Apartment, Floor u-hidden, No. 604-S","links":[{"href":"https://dxbinteract.com/sold/t-123"}]},'
        '{"id":"TOTAL_PRICE","text":"AED 2,250,000 (+73%) AED 1,712 /sqft 80% LTV"},'
        '{"id":"BEDROOM","text":"1,314 sqft 2 Beds"},'
        '{"id":"SOLD_BY","text":"26, Aug 2026 Individual (4 Times)"}]}'
    )

    assert payload == {
        "unit_number": "604-S",
        "location_text": (
            "Buyer's agent Tower One, Business Bay Ready Apartment, "
            "Floor u-hidden, No. 604-S"
        ),
        "amount_text": "AED 2,250,000 (+73%) AED 1,712 /sqft 80% LTV",
        "specs_text": "1,314 sqft 2 Beds",
        "date_text": "26, Aug 2026 Individual (4 Times)",
        "detail_url": "https://dxbinteract.com/sold/t-123",
    }


def test_financing_and_resale_signals_are_normalized_without_guessing() -> None:
    event = normalize_sales_row(
        {
            "unit_number": "602",
            "location_text": (
                "Buyer's agent Aspect Tower, Executive Towers, Business Bay "
                "Ready Office, Floor u-hidden, No. 602"
            ),
            "amount_text": "AED 2,250,000 (+73%) AED 1,712 /sqft 80% LTV",
            "specs_text": "1,314 sqft • 1,400 sqft BUA",
            "date_text": "31, Jan 2025 Individual (4 Times)",
            "detail_url": "https://dxbinteract.com/sold/t-ozzxnlm",
        }
    )

    assert event is not None
    assert event["capital_gain_pct"] == 73
    assert event["ltv_pct"] == 80
    assert event["price_per_sqft_aed"] == 1_712
    assert event["seller_type"] == "Individual"
    assert event["seller_transaction_count"] == 4
    assert event["market_status"] == "Ready"
    assert event["built_up_area_sqft"] == 1_400
