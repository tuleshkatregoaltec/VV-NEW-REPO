from datetime import date

from app.crm.service import (
    _LEAD_CTE,
    _commercial_mix_series,
    _dld_rooms,
    _empty_dashboard,
    _filter_metadata_sql,
    _fixed_mix_series,
    _lead_from_row,
    _quarter_label,
    _rebase_series,
    _same_building,
    _select_rental_comparables,
    _select_sales_comparables,
    _unit_series,
    _where_clause,
)


def _lead_row(**overrides):
    row = {
        "event_key": "lead-1",
        "unit_candidate_key": "candidate-1",
        "building_name": "L-07",
        "project_name": "Greece Cluster",
        "area_name": "International City",
        "property_type": "Apartment",
        "bedrooms": "1 Bed",
        "size_sqft": 732.0,
        "annual_rent_aed": 38_000,
        "purchase_price_aed": 460_000,
        "lease_start": date(2025, 7, 1),
        "lease_end": date(2026, 6, 30),
        "days_to_expiry": -28,
        "lead_status": "expired",
        "priority": "urgent",
        "raw_score": 100,
        "contract_state": "Renewed",
        "match_confidence": "high",
    }
    row.update(overrides)
    return row


def test_expired_candidate_is_an_owner_pursuit_not_a_confirmed_owner_record():
    lead = _lead_from_row(_lead_row())

    assert lead.status == "expired"
    assert lead.sale_conversation is False
    assert "exact-unit and renewal status remain unresolved" in lead.lead_reason
    assert "Resolve the exact unit" in lead.recommended_action
    assert lead.unit_number is None
    assert lead.gross_yield_pct is None


def test_saved_lead_join_columns_and_legacy_status_remain_readable():
    row = {"l." + key: value for key, value in _lead_row().items()}
    row["saved_candidate_key"] = "candidate-1"
    row["_legacy_identity"] = True
    lead = _lead_from_row(row)
    assert lead.lead_id == "lead-1"
    assert lead.unit_candidate_key == "candidate-1"
    assert "before the data refresh" in lead.lead_reason


def test_unique_sales_match_exposes_unit_purchase_date_and_gross_yield():
    lead = _lead_from_row(
        _lead_row(
            unit_number="604-S",
            unit_match_status="unique",
            matching_units=1,
            last_purchase_date=date(2022, 1, 24),
            matched_sale_price=6_977_760,
            annual_rent_aed=550_000,
        )
    )

    assert lead.unit_number == "604-S"
    assert lead.last_purchase_date == date(2022, 1, 24)
    assert lead.matched_sale_price_aed == 6_977_760
    assert lead.gross_yield_pct == 7.88
    assert "Use unit 604-S" in lead.recommended_action


def test_commercial_lease_uses_exact_sales_type_as_evidence_backed_subtype():
    lead = _lead_from_row(
        _lead_row(
            property_type="Commercial",
            asset_class="commercial",
            property_subtype="Office",
            latest_property_type="Office",
            unit_number="1204",
            unit_match_status="unique",
            matching_units=1,
        )
    )

    assert lead.asset_class == "commercial"
    assert lead.property_subtype == "Office"
    assert lead.matched_sales_property_type == "Office"
    assert "leasing mandate" in lead.recommended_action


def test_yield_uses_latest_unit_sale_not_the_older_identity_match():
    lead = _lead_from_row(
        _lead_row(
            unit_number="602",
            unit_match_status="unique",
            identity_sale_date=date(2018, 9, 4),
            identity_sale_price=1_300_000,
            last_purchase_date=date(2025, 1, 31),
            matched_sale_price=2_250_000,
            annual_rent_aed=240_000,
        )
    )

    assert lead.identity_sale_price_aed == 1_300_000
    assert lead.matched_sale_price_aed == 2_250_000
    assert lead.last_purchase_date == date(2025, 1, 31)
    assert lead.gross_yield_pct == 10.67


def test_sale_during_active_tenancy_is_an_occupancy_review_not_an_unlet_claim():
    lead = _lead_from_row(
        _lead_row(
            unit_number="602",
            unit_match_status="unique",
            ownership_timing="sale_during_lease",
            lease_evidence_state="ownership_review",
        )
    )

    assert lead.sale_conversation is False
    assert "Ownership changed during the lease" in lead.lead_reason
    assert "Verify the current owner and occupancy" in lead.recommended_action


def test_expired_exact_unit_without_later_lease_is_immediately_an_unlet_signal():
    lead = _lead_from_row(
        _lead_row(
            unit_number="602",
            unit_match_status="unique",
            ownership_timing="stable_rental_history",
            lease_evidence_state="unlet_signal",
        )
    )

    assert lead.sale_conversation is True
    assert lead.lead_reason.startswith("Unlet signal:")
    assert "no later registered lease" in lead.lead_reason


def test_lead_query_collapses_price_specific_candidates_by_exact_unit():
    assert "PARTITION BY property_identity_key" in _LEAD_CTE
    assert "identity_rank = 1" in _LEAD_CTE
    assert "sale_during_lease" in _LEAD_CTE
    assert "last_purchase_date >= lease_end" in _LEAD_CTE
    assert "'ownership_review'" in _LEAD_CTE
    assert "'unit_unresolved'" in _LEAD_CTE
    assert "registration_pending" not in _LEAD_CTE
    assert "sale_near_expiry" not in _LEAD_CTE


def test_filters_use_bound_parameters_for_agent_search():
    where, params = _where_clause(
        status="expired",
        priority="urgent",
        area="Dubai Marina",
        project=None,
        building=None,
        search="Marina Gate",
        asset_class="commercial",
        property_type="Office",
    )

    assert "lead_status = {status:String}" in where
    assert "{search:String}" in where
    assert "Marina Gate" not in where
    assert params == {
        "status": "expired",
        "priority": "urgent",
        "area": "Dubai Marina",
        "search": "Marina Gate",
        "asset_class": "commercial",
        "property_type": "Office",
    }


def test_filter_options_are_derived_from_the_live_lead_window() -> None:
    sql = _filter_metadata_sql("lead_status = {status:String}")

    assert "FROM leads" in sql
    assert "WHERE lead_status = {status:String}" in sql
    assert "groupUniqArrayIf(area_name" in sql
    assert "FROM dxbi_rental_unit_candidates FINAL" not in sql


def test_commercial_price_index_keeps_a_stable_office_shop_mix():
    rows = [
        {"quarter": date(2026, 1, 1), "segment": "Office", "median_psf": 1_000, "transactions": 80},
        {"quarter": date(2026, 1, 1), "segment": "Shop", "median_psf": 2_000, "transactions": 20},
    ]

    values, counts = _commercial_mix_series(rows)

    assert values[date(2026, 1, 1)] == 1_200
    assert counts[date(2026, 1, 1)] == 100


def test_unloaded_dashboard_surfaces_coverage_state_instead_of_fake_leads():
    dashboard = _empty_dashboard(date(2026, 7, 28), 50, 0, "area")

    assert dashboard.leads == []
    assert dashboard.coverage.exact_unit_ids_available is False
    assert "Load the normalized rental snapshot" in dashboard.coverage.caveat


def test_dxbi_bedroom_labels_are_normalized_for_dld_sale_candidates():
    assert _dld_rooms("2 Bed") == "2 B/R"
    assert _dld_rooms("Studio") == "Studio"


def test_unit_series_and_prefixed_building_names_are_normalized():
    assert _unit_series("604-S") == "S"
    assert _unit_series("S-602") == "S"
    assert _unit_series("B606") == "B"
    assert _same_building(
        "Muraba Residences Palm Jumeriah",
        "Nipun Muraba Residences Palm Jumeriah",
    )


def test_report_sales_selection_prefers_anchored_s_series():
    rows = [
        {
            "transaction_date": date(2026, 3, 16),
            "building_name": "Nipun Muraba Residences Palm Jumeriah",
            "unit_number": "704-S",
            "bedrooms": "2 Bed",
            "size_sqft": 1768,
        },
        {
            "transaction_date": date(2025, 7, 29),
            "building_name": "Ellington Beach House",
            "unit_number": "S-602",
            "bedrooms": "2 Bed",
            "size_sqft": 1770,
        },
        {
            "transaction_date": date(2026, 2, 20),
            "building_name": "Anantara Residences North",
            "unit_number": "303",
            "bedrooms": "2 Bed",
            "size_sqft": 1771,
        },
    ]

    selected, basis = _select_sales_comparables(
        rows,
        building_name="Muraba Residences Palm Jumeriah",
        bedrooms="2 Bed",
        unit_number="604-S",
        size=1768,
    )

    assert [row["unit_number"] for row, _ in selected] == ["704-S", "S-602"]
    assert "S-designated" in basis


def test_report_rental_selection_prefers_tight_same_building_evidence():
    rows = [
        {
            "lease_start": date(2025, 12, 22),
            "building_name": "Muraba Residences Palm Jumeriah",
            "unit_number": "",
            "bedrooms": "2 Bed",
            "size_sqft": 1768,
        },
        {
            "lease_start": date(2025, 11, 14),
            "building_name": "Muraba Residences Palm Jumeriah",
            "unit_number": "303-N",
            "bedrooms": "2 Bed",
            "size_sqft": 1758,
        },
        {
            "lease_start": date(2026, 2, 28),
            "building_name": "Anantara Residences South",
            "unit_number": "619",
            "bedrooms": "2 Bed",
            "size_sqft": 1769,
        },
    ]

    selected, basis = _select_rental_comparables(
        rows,
        building_name="Muraba Residences Palm Jumeriah",
        bedrooms="2 Bed",
        unit_number="604-S",
        size=1768,
    )

    assert len(selected) == 2
    assert all("Muraba" in row["building_name"] for row, _ in selected)
    assert "Same building" in basis


def test_lease_expiry_lookback_is_a_bound_query_parameter():
    assert "addDays({as_of:Date}, -{expired_days:Int32})" in _LEAD_CTE


def test_price_index_uses_fixed_apartment_villa_mix_and_rebases():
    rows = [
        {
            "quarter": date(2025, 1, 1),
            "segment": "Apartment",
            "median_psf": 1_000,
            "transactions": 750,
        },
        {
            "quarter": date(2025, 1, 1),
            "segment": "Villa",
            "median_psf": 2_000,
            "transactions": 250,
        },
        {
            "quarter": date(2025, 4, 1),
            "segment": "Apartment",
            "median_psf": 1_100,
            "transactions": 900,
        },
        {
            "quarter": date(2025, 4, 1),
            "segment": "Villa",
            "median_psf": 2_200,
            "transactions": 300,
        },
    ]

    series, counts = _fixed_mix_series(rows)
    index = _rebase_series(series)

    assert series[date(2025, 1, 1)] == 1_250
    assert series[date(2025, 4, 1)] == 1_375
    assert counts[date(2025, 4, 1)] == 1_200
    assert index[date(2025, 1, 1)] == 100
    assert index[date(2025, 4, 1)] == 110
    assert _quarter_label(date(2025, 4, 1)) == "Q2 2025"
