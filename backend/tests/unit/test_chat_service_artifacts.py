from datetime import date

import pytest

from app.chat import service as chat_service
from app.chat.models import Message
from app.core.market_constants import SQM_TO_SQFT
from app.listings.models import ListingFiltersResponse, ListingListResponse


def test_pydantic_history_includes_rendered_artifact_context():
    messages = [
        Message(
            conversation_id=1,
            role="assistant",
            content="Chart ready.",
            meta_data={
                "artifacts": [
                    {
                        "type": "custom_chart",
                        "status": "ready",
                        "title": "Gross yield",
                        "subtitle": "Areas · Gross yield · Dubai",
                        "query": {"sort_direction": "desc"},
                        "data": {
                            "metric_label": "Gross yield",
                            "sort_direction": "desc",
                            "points": [
                                {
                                    "label": "Al Furjan",
                                    "value": 9.52,
                                    "record_count": 305,
                                },
                                {
                                    "label": "Dubai South",
                                    "value": 8.84,
                                    "record_count": 412,
                                },
                            ],
                        },
                    },
                    {
                        "type": "listing_results",
                        "status": "ready",
                        "title": "Sales listings",
                        "query": {"mode": "sale", "area": "Al Furjan"},
                        "data": {"total": 0},
                    },
                ]
            },
        )
    ]

    history = chat_service._convert_to_pydantic_messages(messages)

    content = history[0].parts[0].content
    assert "[Rendered card context for follow-up references]" in content
    assert "Al Furjan: Gross yield 9.52, 305 records" in content
    assert "Dubai South: Gross yield 8.84, 412 records" in content
    assert (
        "Rendered listings card: Sales listings; mode sale; area Al Furjan; exact matches 0."
        in content
    )


@pytest.mark.asyncio
async def test_resolve_transaction_area_uses_master_project_alias(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [{"area_name_en": "Marsa Dubai"}]

    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    area = await chat_service._resolve_transaction_area("Dubai Marina")

    assert area == "Marsa Dubai"
    assert "master_project_en" in str(seen["sql"])
    assert seen["params"] == {
        "area": "Dubai Marina",
        "search_text": "Dubai Marina",
        "pattern": "%Dubai Marina%",
    }


@pytest.mark.asyncio
async def test_latest_transaction_date_applies_market_filters(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [{"max_date": "2026-01-20"}]

    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    max_date = await chat_service._latest_transaction_date(
        property_usage="Residential",
        property_type="Unit",
        area="Marsa Dubai",
    )

    assert max_date == date(2026, 1, 20)
    assert "property_usage_en = {property_usage:String}" in str(seen["sql"])
    assert "property_type_en = {property_type:String}" in str(seen["sql"])
    assert "area_name_en = {area_name:String}" in str(seen["sql"])
    assert seen["params"] == {
        "property_usage": "Residential",
        "property_type": "Unit",
        "area_name": "Marsa Dubai",
    }


@pytest.mark.asyncio
async def test_market_trend_artifact_anchors_to_latest_matching_transaction_date(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_resolve_area(area: str | None):
        assert area == "Dubai Marina"
        return "Marsa Dubai"

    async def fake_latest_date(
        *,
        property_usage: str | None,
        property_type: str | None,
        area: str | None,
    ):
        seen["latest_args"] = {
            "property_usage": property_usage,
            "property_type": property_type,
            "area": area,
        }
        return date(2026, 1, 20)

    async def fake_query(sql: str, params: dict[str, object]):
        seen["trend_sql"] = sql
        seen["trend_params"] = params
        return [
            {
                "period": date(2025, 1, 1),
                "transaction_count": 10,
                "avg_price": 1_000_000,
                "avg_price_sqm": 10_000,
            },
            {
                "period": date(2026, 1, 1),
                "transaction_count": 20,
                "avg_price": 1_200_000,
                "avg_price_sqm": 12_000,
            },
        ]

    monkeypatch.setattr(chat_service, "_resolve_transaction_area", fake_resolve_area)
    monkeypatch.setattr(chat_service, "_latest_transaction_date", fake_latest_date)
    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    artifact = await chat_service._fetch_market_trend_artifact(
        {
            "id": "artifact-1",
            "type": "market_trend",
            "status": "loading",
            "title": "Market trend",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        {
            "area": "Dubai Marina",
            "property_usage": "Residential",
            "property_type": "Unit",
            "days": 365,
        },
    )

    assert seen["latest_args"] == {
        "property_usage": "Residential",
        "property_type": "Unit",
        "area": "Marsa Dubai",
    }
    assert seen["trend_params"]["end_date"] == "2026-01-20"
    assert seen["trend_params"]["start_date"] == "2025-01-20"
    assert artifact["status"] == "ready"
    assert artifact["query"]["area"] == "Marsa Dubai"
    assert artifact["data"]["total_transactions"] == 30
    assert artifact["data"]["avg_price_sqm_change_pct"] == 20.0


@pytest.mark.asyncio
async def test_listing_artifact_coerces_generic_sale_tool_call_to_rent(monkeypatch):
    calls: list[dict[str, object]] = []

    async def fake_resolve_listing_area(db, mode, area):
        return "Jumeirah Village Circle" if area else None

    async def fake_list_listings_from_clickhouse(**kwargs):
        calls.append(kwargs)
        return ListingListResponse(
            listings=[],
            total=4210,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            filters=ListingFiltersResponse(),
        )

    monkeypatch.setattr(chat_service, "_resolve_listing_area", fake_resolve_listing_area)
    monkeypatch.setattr(
        chat_service, "list_listings_from_clickhouse", fake_list_listings_from_clickhouse
    )

    artifact = await chat_service._fetch_listing_artifact(
        db=object(),
        artifact={
            "id": "artifact-1",
            "type": "listing_results",
            "status": "loading",
            "title": "Sales listings",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        args={"mode": "sale", "area": "jvc", "limit": 12},
        user_message="show me listings in JVC",
    )

    assert [call["mode"] for call in calls] == ["rent"]
    assert artifact["title"] == "Rental listings"
    assert artifact["query"]["mode"] == "rent"
    assert artifact["query"]["area"] == "Jumeirah Village Circle"
    assert artifact["query"]["fallback_from_mode"] == "sale"
    assert artifact["data"]["total"] == 4210


@pytest.mark.asyncio
async def test_listing_artifact_keeps_explicit_sale_request_strict(monkeypatch):
    calls: list[dict[str, object]] = []

    async def fake_resolve_listing_area(db, mode, area):
        return "Jumeirah Village Circle" if area else None

    async def fake_list_listings_from_clickhouse(**kwargs):
        calls.append(kwargs)
        return ListingListResponse(
            listings=[],
            total=0,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            filters=ListingFiltersResponse(),
        )

    monkeypatch.setattr(chat_service, "_resolve_listing_area", fake_resolve_listing_area)
    monkeypatch.setattr(
        chat_service, "list_listings_from_clickhouse", fake_list_listings_from_clickhouse
    )

    artifact = await chat_service._fetch_listing_artifact(
        db=object(),
        artifact={
            "id": "artifact-1",
            "type": "listing_results",
            "status": "loading",
            "title": "Sales listings",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        args={"mode": "sale", "area": "jvc", "limit": 12},
        user_message="show me sales listings in JVC",
    )

    assert [call["mode"] for call in calls] == ["sale"]
    assert artifact["title"] == "Sales listings"
    assert artifact["query"]["mode"] == "sale"
    assert artifact["query"]["fallback_from_mode"] is None


@pytest.mark.asyncio
async def test_custom_sales_chart_artifact_uses_agent_selected_dimension_and_metric(
    monkeypatch,
):
    seen: dict[str, object] = {}

    async def fake_resolve_scope(area: str | None):
        assert area == "JVC"
        return {
            "label": "Jumeirah Village Circle",
            "area": None,
            "master_project": "Jumeirah Village Circle",
        }

    async def fake_latest_date(
        *,
        property_usage: str | None,
        property_type: str | None,
        area: str | None,
        master_project: str | None = None,
    ):
        seen["latest_args"] = {
            "property_usage": property_usage,
            "property_type": property_type,
            "area": area,
            "master_project": master_project,
        }
        return date(2026, 1, 31)

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [
            {"label": "Unit", "value": 1250, "record_count": 40},
            {"label": "Villa", "value": 850, "record_count": 12},
        ]

    monkeypatch.setattr(chat_service, "_resolve_transaction_scope", fake_resolve_scope)
    monkeypatch.setattr(chat_service, "_latest_transaction_date", fake_latest_date)
    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    artifact = await chat_service._fetch_custom_chart_artifact(
        {
            "id": "artifact-1",
            "type": "custom_chart",
            "status": "loading",
            "title": "Chart",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        {
            "dataset": "sales",
            "metric": "avg_price_sqm",
            "group_by": "property_type",
            "chart_type": "doughnut",
            "area": "JVC",
            "days": 90,
            "limit": 5,
        },
    )

    assert seen["latest_args"] == {
        "property_usage": "Residential",
        "property_type": None,
        "area": None,
        "master_project": "Jumeirah Village Circle",
    }
    assert "property_type_en AS label" in str(seen["sql"])
    assert "round(avg(meter_sale_price), 0) AS value" in str(seen["sql"])
    assert seen["params"]["start_date"] == "2025-11-02"
    assert seen["params"]["end_date"] == "2026-01-31"
    assert artifact["status"] == "ready"
    assert artifact["query"]["area"] == "Jumeirah Village Circle"
    assert artifact["query"]["master_project"] == "Jumeirah Village Circle"
    assert artifact["query"]["chart_type"] == "doughnut"
    assert artifact["data"]["metric_label"] == "Average price / sqm"
    assert artifact["data"]["points"][0]["label"] == "Unit"
    assert artifact["data"]["summary"]["total_records"] == 52


@pytest.mark.asyncio
async def test_custom_sales_chart_artifact_can_rank_bottom_areas_by_sqft_metric(
    monkeypatch,
):
    seen: dict[str, object] = {}

    async def fake_resolve_scope(area: str | None):
        assert area is None
        return {"label": None, "area": None, "master_project": None}

    async def fake_latest_date(
        *,
        property_usage: str | None,
        property_type: str | None,
        area: str | None,
        master_project: str | None = None,
    ):
        seen["latest_args"] = {
            "property_usage": property_usage,
            "property_type": property_type,
            "area": area,
            "master_project": master_project,
        }
        return date(2026, 1, 20)

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [
            {"label": "International City", "value": 480, "record_count": 450},
            {"label": "Dubai Investment Park", "value": 560, "record_count": 80},
        ]

    monkeypatch.setattr(chat_service, "_resolve_transaction_scope", fake_resolve_scope)
    monkeypatch.setattr(chat_service, "_latest_transaction_date", fake_latest_date)
    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    artifact = await chat_service._fetch_custom_chart_artifact(
        {
            "id": "artifact-1",
            "type": "custom_chart",
            "status": "loading",
            "title": "Chart",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        {
            "dataset": "sales",
            "metric": "avg_price_sqft",
            "group_by": "area",
            "chart_type": "horizontal_bar",
            "sort_direction": "asc",
            "days": 365,
            "limit": 2,
        },
    )

    assert f"round(avg(meter_sale_price) / {SQM_TO_SQFT}, 0) AS value" in str(seen["sql"])
    assert "ORDER BY value ASC LIMIT {limit:Int32}" in str(seen["sql"])
    assert "record_count >= {min_records:Int32}" in str(seen["sql"])
    assert seen["params"]["limit"] == 2
    assert seen["params"]["min_records"] == 25
    assert artifact["query"]["sort_direction"] == "asc"
    assert artifact["query"]["days"] == 365
    assert artifact["data"]["metric_label"] == "Average price / sqft"
    assert artifact["data"]["sort_direction"] == "asc"
    assert [point["label"] for point in artifact["data"]["points"]] == [
        "International City",
        "Dubai Investment Park",
    ]


@pytest.mark.asyncio
async def test_custom_area_yield_chart_recomputes_yield_from_sales_and_rentals(
    monkeypatch,
):
    seen: dict[str, object] = {}

    async def fake_latest_sales_date(**kwargs):
        seen["latest_sales_args"] = kwargs
        return date(2026, 1, 20)

    async def fake_latest_rental_date(**kwargs):
        seen["latest_rental_args"] = kwargs
        return date(2026, 5, 5)

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [
            {"label": "Me'Aisem First", "value": 9.14, "record_count": 3985},
            {"label": "Jabal Ali Industrial Second", "value": 8.62, "record_count": 505},
        ]

    monkeypatch.setattr(chat_service, "_latest_transaction_date", fake_latest_sales_date)
    monkeypatch.setattr(chat_service, "_latest_rental_contract_date", fake_latest_rental_date)
    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    artifact = await chat_service._fetch_custom_chart_artifact(
        {
            "id": "artifact-1",
            "type": "custom_chart",
            "status": "loading",
            "title": "Chart",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        {
            "dataset": "projects",
            "metric": "gross_yield_pct",
            "group_by": "area",
            "chart_type": "horizontal_bar",
            "days": 365,
            "limit": 2,
        },
    )

    assert seen["latest_sales_args"] == {
        "property_usage": "Residential",
        "property_type": "Unit",
        "area": None,
    }
    assert seen["latest_rental_args"] == {
        "property_usage": "Residential",
        "property_type": "Flat",
        "area": None,
    }
    assert "FROM ch_transactions" in str(seen["sql"])
    assert "FROM ch_rent_contracts" in str(seen["sql"])
    assert "FROM ch_area_fact" not in str(seen["sql"])
    assert "median_annual_rent / nullIf(s.median_sale_price, 0) * 100" in str(seen["sql"])
    assert "value BETWEEN 1 AND 25" in str(seen["sql"])
    assert seen["params"]["start_date"] == "2025-01-20"
    assert seen["params"]["end_date"] == "2026-01-20"
    assert seen["params"]["sales_property_type"] == "Unit"
    assert seen["params"]["rental_property_type"] == "Flat"
    assert seen["params"]["min_records"] == 250
    assert artifact["query"]["dataset"] == "areas"
    assert artifact["query"]["metric"] == "gross_yield_pct"
    assert artifact["query"]["property_type"] == "Flat"
    assert artifact["data"]["metric_label"] == "Gross yield"
    assert artifact["data"]["points"][0]["value"] == 9.14


@pytest.mark.asyncio
async def test_latest_rental_contract_date_ignores_future_contracts(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [{"max_date": "2026-05-13"}]

    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    max_date = await chat_service._latest_rental_contract_date(
        property_usage="Residential",
        property_type="Flat",
        area=None,
        master_project="Dubai Marina",
    )

    assert max_date == date(2026, 5, 13)
    assert "contract_start_date <= today()" in str(seen["sql"])
    assert "master_project_en = {master_project:String}" in str(seen["sql"])
    assert seen["params"] == {
        "property_usage": "Residential",
        "property_type": "Flat",
        "master_project": "Dubai Marina",
    }


@pytest.mark.asyncio
async def test_custom_rental_chart_artifact_filters_out_future_contracts(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_resolve_scope(area: str | None):
        assert area == "Dubai Marina"
        return {"label": "Dubai Marina", "area": None, "master_project": "Dubai Marina"}

    async def fake_latest_date(
        *,
        property_usage: str | None,
        property_type: str | None,
        area: str | None,
        master_project: str | None = None,
    ):
        seen["latest_args"] = {
            "property_usage": property_usage,
            "property_type": property_type,
            "area": area,
            "master_project": master_project,
        }
        return date(2026, 5, 13)

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [
            {"label": "Flat", "value": 165670, "record_count": 165670},
            {"label": "Shop", "value": 5775, "record_count": 5775},
        ]

    monkeypatch.setattr(chat_service, "_resolve_transaction_scope", fake_resolve_scope)
    monkeypatch.setattr(chat_service, "_latest_rental_contract_date", fake_latest_date)
    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    artifact = await chat_service._fetch_custom_chart_artifact(
        {
            "id": "artifact-1",
            "type": "custom_chart",
            "status": "loading",
            "title": "Chart",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        {
            "dataset": "rentals",
            "metric": "contract_count",
            "group_by": "property_type",
            "chart_type": "doughnut",
            "area": "Dubai Marina",
            "days": 365,
            "limit": 5,
        },
    )

    assert seen["latest_args"] == {
        "property_usage": "Residential",
        "property_type": None,
        "area": None,
        "master_project": "Dubai Marina",
    }
    assert "contract_start_date <= today()" in str(seen["sql"])
    assert seen["params"]["end_date"] == "2026-05-13"
    assert seen["params"]["start_date"] == "2025-05-13"
    assert artifact["status"] == "ready"
    assert artifact["query"]["area"] == "Dubai Marina"
    assert artifact["data"]["points"][0]["label"] == "Flat"
    assert artifact["data"]["summary"]["total_records"] == 171445


@pytest.mark.asyncio
async def test_custom_rental_chart_artifact_supports_multi_area_time_series(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_resolve_scope(area: str | None):
        scopes = {
            "Dubai Marina": {
                "label": "Dubai Marina",
                "area": None,
                "master_project": "Dubai Marina",
            },
            "JVC": {
                "label": "Jumeirah Village Circle",
                "area": None,
                "master_project": "Jumeirah Village Circle",
            },
        }
        return scopes[str(area)]

    async def fake_latest_date(
        *,
        property_usage: str | None,
        property_type: str | None,
        scopes: list[dict[str, str | None]],
    ):
        seen["latest_args"] = {
            "property_usage": property_usage,
            "property_type": property_type,
            "scopes": scopes,
        }
        return date(2026, 5, 13)

    async def fake_query(sql: str, params: dict[str, object]):
        seen["sql"] = sql
        seen["params"] = params
        return [
            {
                "series_label": "Dubai Marina",
                "label": date(2026, 4, 1),
                "value": 120000,
                "record_count": 25,
            },
            {
                "series_label": "Jumeirah Village Circle",
                "label": date(2026, 4, 1),
                "value": 70000,
                "record_count": 40,
            },
        ]

    monkeypatch.setattr(chat_service, "_resolve_transaction_scope", fake_resolve_scope)
    monkeypatch.setattr(chat_service, "_latest_rental_contract_date_for_scopes", fake_latest_date)
    monkeypatch.setattr(chat_service, "ch_query", fake_query)

    artifact = await chat_service._fetch_custom_chart_artifact(
        {
            "id": "artifact-1",
            "type": "custom_chart",
            "status": "loading",
            "title": "Chart",
            "created_at": "2026-05-05T00:00:00+00:00",
            "query": {},
        },
        {
            "dataset": "rentals",
            "metric": "median_rent",
            "group_by": "time",
            "chart_type": "line",
            "areas": ["Dubai Marina", "JVC"],
            "days": 90,
        },
    )

    assert [scope["label"] for scope in seen["latest_args"]["scopes"]] == [
        "Dubai Marina",
        "Jumeirah Village Circle",
    ]
    assert "GROUP BY series_label, label" in str(seen["sql"])
    assert seen["params"]["scope_0_master_project"] == "Dubai Marina"
    assert seen["params"]["scope_1_master_project"] == "Jumeirah Village Circle"
    assert artifact["query"]["areas"] == ["Dubai Marina", "Jumeirah Village Circle"]
    assert [item["label"] for item in artifact["data"]["series"]] == [
        "Dubai Marina",
        "Jumeirah Village Circle",
    ]
    assert artifact["data"]["summary"]["total_records"] == 65
