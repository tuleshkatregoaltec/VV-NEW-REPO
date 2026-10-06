from unittest.mock import AsyncMock


def _radar_stats() -> dict:
    return {
        "total_projects": 0,
        "mapped_projects": 0,
        "active_projects": 0,
        "finished_projects": 0,
        "pipeline_units": 0,
        "units_delivering_next_12_months": 0,
        "sales_transaction_count_12m": 0,
        "rental_contract_count_12m": 0,
        "total_sales_volume_12m": 0,
        "dda_plot_count": 0,
        "dda_total_plot_area_sqm": 0,
        "dda_total_gfa_sqm": 0,
    }


async def test_radar_routes_parse_supported_period_days_from_query_strings(client, monkeypatch):
    radar_mock = AsyncMock(
        return_value={"stats": _radar_stats(), "projects": [], "areas": [], "source_notes": []}
    )
    overview_mock = AsyncMock(
        return_value={"stats": _radar_stats(), "areas": [], "source_notes": []}
    )
    pins_mock = AsyncMock(return_value=[])
    building_pins_mock = AsyncMock(return_value=[])

    monkeypatch.setattr("app.core.decorators.cache.get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.core.decorators.cache.set", AsyncMock())
    monkeypatch.setattr("app.project.router.get_project_radar", radar_mock)
    monkeypatch.setattr("app.project.router.get_project_radar_overview", overview_mock)
    monkeypatch.setattr("app.project.router.get_project_radar_pins", pins_mock)
    monkeypatch.setattr("app.project.router.get_radar_building_pins", building_pins_mock)

    paths = [
        "/api/v1/projects/radar?limit=100&period_days=365",
        "/api/v1/projects/radar/overview?period_days=180",
        (
            "/api/v1/projects/radar/pins?west=55.1&south=25.1&east=55.4&north=25.3"
            "&limit=100&period_days=90"
        ),
        (
            "/api/v1/projects/radar/building-pins?west=55.1&south=25.1&east=55.4&north=25.3"
            "&limit=100&period_days=30"
        ),
    ]

    responses = [await client.get(path) for path in paths]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert int(radar_mock.await_args.kwargs["period_days"]) == 365
    assert int(overview_mock.await_args.kwargs["period_days"]) == 180
    assert int(pins_mock.await_args.kwargs["period_days"]) == 90
    assert int(building_pins_mock.await_args.kwargs["period_days"]) == 30


async def test_radar_routes_reject_unsupported_period_days(client):
    response = await client.get("/api/v1/projects/radar/overview?period_days=45")

    assert response.status_code == 422
