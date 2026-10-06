import pytest

from app.project import service as project_service


def test_radar_yield_uses_existing_sale_median_denominator():
    row = {
        "yield_existing_sale_count": 12,
        "yield_rental_contract_count": 18,
        "yield_existing_median_sale_price": 1_000_000,
        "yield_median_annual_rent": 75_000,
    }

    assert project_service._radar_gross_yield_pct(row) == 7.5


def test_radar_yield_blanks_implausible_or_thin_samples():
    assert (
        project_service._radar_gross_yield_pct(
            {
                "yield_existing_sale_count": 50,
                "yield_rental_contract_count": 50,
                "yield_existing_median_sale_price": 200_000,
                "yield_median_annual_rent": 100_000,
            }
        )
        is None
    )
    assert (
        project_service._radar_gross_yield_pct(
            {
                "yield_existing_sale_count": 4,
                "yield_rental_contract_count": 50,
                "yield_existing_median_sale_price": 1_000_000,
                "yield_median_annual_rent": 80_000,
            }
        )
        is None
    )


def test_radar_developer_display_prefers_english_and_drops_unmapped_arabic():
    lookup = project_service._developer_lookup(
        [
            {
                "developer_name_ar": "شركة نخيل (ش.م.خ)",
                "developer_name_en": "Nakheel",
            }
        ]
    )

    assert project_service._developer_display_name("شركة نخيل (ش.م.خ)", lookup) == "Nakheel"
    assert project_service._developer_display_name("Meraas", lookup) == "Meraas"
    assert project_service._developer_display_name("مطور غير معروف", lookup) is None
    assert project_service._developer_display_list(
        ["شركة نخيل (ش.م.خ)", "Nakheel", "مطور غير معروف", "Meraas"],
        lookup,
    ) == ["Nakheel", "Meraas"]


def test_radar_activity_period_is_limited_to_supported_ttm_windows():
    assert project_service._validated_radar_period_days(30) == 30
    assert project_service._validated_radar_period_days(365) == 365

    with pytest.raises(ValueError, match="30, 90, 180, or 365"):
        project_service._validated_radar_period_days(730)


def test_radar_queries_use_detailed_activity_sources_and_bound_period_parameter():
    area_sql = project_service._radar_area_sql(project_service._radar_geo_cte())
    stats_sql = project_service._radar_stats_sql(project_service._radar_geo_cte())

    for sql in (area_sql, stats_sql):
        assert "dxbi_sales_unit_events" in sql
        assert "dxbi_rental_events" in sql
        assert "{period_days:UInt16}" in sql
        assert "toIntervalDay({period_days:UInt16})" in sql


def test_radar_project_coordinates_require_unique_nearby_pf_or_reelly_match():
    geo_sql = project_service._radar_geo_cte()

    assert "lowerUTF8(trim(region)) = 'dubai'" in geo_sql
    assert "uniqExact(candidate.canonical_location_id) = 1" in geo_sql
    assert "uniqExact(project_id) = 1" in geo_sql
    assert "reelly_geo_projects" in geo_sql
    assert "FROM reelly_geo_projects" in geo_sql
    assert "WHERE reelly.property_id = 0" in geo_sql
    assert "'reelly_project' AS entity_source" in geo_sql
    assert "pf_distance_m <= 2000" in geo_sql
    assert "reelly_distance_m <= 2000" in geo_sql
    assert "source_spread_m <= 500" in geo_sql
    assert "building_centroid_fallback" in geo_sql


def test_radar_project_sales_use_approved_offplan_reelly_crosswalk():
    sql = project_service._radar_project_pins_sql(project_service._radar_geo_cte(), "1")

    assert "offplan_reelly_mapped_source_facts" in sql
    assert "orm.match_status IN ('auto_approved', 'manual_approved')" in sql
    assert "orm.normalized_reelly_project_name" in sql


def test_radar_building_query_uses_only_approved_tower_links_and_ready_sales():
    sql = project_service._radar_building_pins_sql()

    assert "location_type = 'TOWER'" in sql
    assert "gm.target_grain = 'tower'" in sql
    assert "gm.match_status IN ('auto_approved', 'manual_approved')" in sql
    assert "lowerUTF8(e.market_status) != 'offplan'" in sql
    assert "pf_listings_bronze" in sql
    assert "{period_days:UInt16}" in sql


def test_radar_stats_expose_selected_period_and_compatibility_totals():
    stats = project_service._radar_stats_from_row(
        {
            "sales_transaction_count": 120,
            "rental_contract_count": 340,
            "total_sales_volume": 1_500_000,
            "mapped_sales_transaction_count": 100,
            "mapped_rental_contract_count": 300,
            "activity_coverage_pct": 87.0,
        },
        90,
    )

    assert stats.activity_period_days == 90
    assert stats.sales_transaction_count == 120
    assert stats.sales_transaction_count_12m == 120
    assert stats.rental_contract_count == 340
    assert stats.activity_coverage_pct == 87.0
