from app.supply import service as supply_service


def test_project_risk_score_uses_available_signals_without_financial_feeds():
    indicators = [
        supply_service._risk_indicator(
            key="developer", label="Developer overlay", value="82.0", score=82.0
        ),
        supply_service._risk_indicator(
            key="delivery", label="Delivery timing", value="2027-12-31", score=84.0
        ),
        supply_service._risk_indicator(
            key="progress",
            label="Construction progress",
            value="~",
            score=None,
            available=False,
        ),
        supply_service._risk_indicator(
            key="sales", label="Sales absorption", value="120 sale units", score=68.0
        ),
    ]

    score, coverage = supply_service._score_weighted_indicators(indicators)

    assert coverage == 80.0
    assert score == 79.1
    assert supply_service._project_risk_badge(score, coverage) == "Low"


def test_financial_risk_metrics_are_visible_pending_fields():
    metrics = supply_service._financial_risk_metrics()

    assert [metric.key for metric in metrics] == [
        "escrow_balance",
        "adequacy_ratio",
        "authorised_withdrawals",
        "remaining_construction_cost",
        "compliance_record",
    ]
    assert all(metric.value == "~" for metric in metrics)
    assert all(metric.status == "Pending" for metric in metrics)


def test_reelly_launch_and_inventory_fields_feed_project_sales_score():
    data = {
        "raw": {"Launch_date": "1721921857000"},
        "units_in_sale": 20,
        "sale_status": "On sale",
        "units": [],
    }
    dld_signal = {
        "no_of_units": 100,
        "anchor_date": supply_service.date(2025, 7, 25),
    }

    inventory = supply_service._project_sales_inventory(data, dld_signal)
    indicator = supply_service._sales_indicator(data, dld_signal)

    assert supply_service._reelly_launch_date(data) == supply_service.date(2024, 7, 25)
    assert inventory["units_sold"] == 80
    assert inventory["units_unsold"] == 20
    assert inventory["registered_units"] == 100
    assert inventory["sales_absorption_pct"] == 80.0
    assert indicator.value == "80 sold / 20 unsold"
    assert indicator.available


def test_zero_reelly_inventory_is_pending_unless_project_is_out_of_stock():
    on_sale = {"raw": {}, "units_in_sale": 0, "sale_status": "On sale", "units": []}
    out_of_stock = {"raw": {}, "units_in_sale": 0, "sale_status": "Out of stock", "units": []}

    assert supply_service._reelly_unsold_units(on_sale) is None
    assert supply_service._reelly_unsold_units(out_of_stock) == 0


def test_developer_identity_matches_legal_entity_to_reelly_brand():
    logos = {
        supply_service._developer_logo_match_key("DAMAC"): (
            "DAMAC",
            "/api/v1/supply/catalogue/assets/1",
        ),
        supply_service._developer_logo_match_key("Emaar"): (
            "Emaar",
            "/api/v1/supply/catalogue/assets/2",
        ),
    }

    assert supply_service._developer_identity("DAMAC MRY INVESTMENT L.L.C", logos) == (
        "DAMAC",
        "/api/v1/supply/catalogue/assets/1",
    )
    assert supply_service._developer_identity("EMAAR DEVELOPMENT P.J.S.C.", logos) == (
        "Emaar",
        "/api/v1/supply/catalogue/assets/2",
    )


def test_developer_identity_does_not_merge_generic_dubai_brands():
    logos = {
        supply_service._developer_logo_match_key("Dubai Properties"): (
            "Dubai Properties",
            "/api/v1/supply/catalogue/assets/3",
        ),
    }

    assert supply_service._developer_identity("DUBAI HILLS ESTATE L.L.C", logos) == (
        "DUBAI HILLS ESTATE L.L.C",
        None,
    )


def test_developer_rankings_hide_q_properties_pending_validation():
    assert supply_service._developer_ranking_hidden("Q Properties")
    assert supply_service._developer_ranking_hidden("Q PROPERTIES L.L.C")
    assert not supply_service._developer_ranking_hidden("Dubai Properties")


def test_developer_brand_name_normalizes_visible_community_vehicles():
    assert supply_service._developer_brand_name("DUBAI HILLS ESTATE L.L.C") == "Emaar"
    assert supply_service._developer_brand_name("THE PALM - JEBEL ALI CO. (L.L.C)") == "Nakheel"
    assert supply_service._developer_brand_name("BUSINESS BAY (L.L.C)") == "Dubai Properties"
    assert supply_service._developer_brand_name("Sobha") == "Sobha"


def test_unmapped_legal_entities_are_not_rankable_developer_brands():
    assert not supply_service._developer_rankable_brand("DHRE 2 BTS L.L.C")
    assert not supply_service._developer_rankable_brand("Expo City Real Estate Development FZCO")
    assert not supply_service._developer_rankable_brand("GULF GENERAL INVESTMENTS CO. (P.S.C)")
    assert supply_service._developer_rankable_brand(
        supply_service._developer_brand_name("DUBAI HILLS ESTATE L.L.C")
    )
    assert supply_service._developer_rankable_brand("Sobha")


def test_developer_criteria_normalizes_score_over_available_weight():
    criteria, score, coverage = supply_service._developer_criteria(
        {
            "completed_units": 10_000,
            "pipeline_units": 15_000,
            "on_time_units": 80,
            "completed_units_with_schedule": 100,
        }
    )

    assert coverage == 100.0
    assert score == 87.0
    assert [item.key for item in criteria if item.available] == [
        "delivered_unit_scale",
        "pipeline_unit_scale",
        "on_time_delivery",
    ]


def test_developer_criteria_prefers_large_operators_then_adjusts_for_delivery_history():
    large_operator = supply_service._developer_criteria(
        {
            "completed_units": 10_000,
            "pipeline_units": 15_000,
            "on_time_units": 60,
            "completed_units_with_schedule": 100,
        }
    )
    small_operator = supply_service._developer_criteria(
        {
            "completed_units": 250,
            "pipeline_units": 500,
            "on_time_units": 100,
            "completed_units_with_schedule": 100,
        }
    )

    assert large_operator[1] == 74.0
    assert small_operator[1] == 70.9
    assert large_operator[1] > small_operator[1]


def test_developer_criteria_requires_enough_available_weight_for_score():
    criteria, score, coverage = supply_service._developer_criteria({"pipeline_units": 500})

    assert coverage == 15.0
    assert score is None
    assert [item.key for item in criteria if item.available] == ["pipeline_unit_scale"]


def test_catalogue_filters_exclude_past_completion_dates_by_default():
    where, params = supply_service._catalogue_ch_filters(None, None, "Presale")

    assert "lowerUTF8(trim(region)) = 'dubai'" in where
    assert "latitude BETWEEN 24.55" in where
    assert "Completion_time" in where
    assert "JSON_VALUE(list_item_json, '$.Status') = {status:String}" in where
    assert params["today_ms"] > 0
    assert params["status"] == "Presale"


def test_catalogue_filters_can_include_past_completion_dates():
    where, params = supply_service._catalogue_ch_filters(None, None, "Presale", include_past=True)

    assert "Completion_time" not in where
    assert "today_ms" not in params
    assert params["status"] == "Presale"


def test_catalogue_filters_follow_active_non_developer_filters():
    where, params = supply_service._catalogue_ch_filters(
        "Marina", "Dubai Marina", "Presale", include_past=True
    )

    assert "Project_name" in where
    assert "JSON_VALUE(list_item_json, '$.Area_name') = {area:String}" in where
    assert "JSON_VALUE(list_item_json, '$.Status') = {status:String}" in where
    assert "{developer:String}" not in where
    assert params == {
        "search": "Marina",
        "area": "Dubai Marina",
        "status": "Presale",
    }


def test_catalogue_sort_options_are_bounded():
    assert "scraped_at" in supply_service._catalogue_ch_order_by("newest")
    assert "Completion_time" in supply_service._catalogue_ch_order_by("delivery_soon")
    assert supply_service._catalogue_ch_order_by(
        "not-a-sort"
    ) == supply_service._catalogue_ch_order_by("recommended")
