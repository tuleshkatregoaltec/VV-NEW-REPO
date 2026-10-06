from unittest.mock import AsyncMock

from fastapi.encoders import jsonable_encoder

from app.analytics.models import (
    ProjectAnalyticsResponse,
    ProjectRentalSummary,
    ProjectSalesSummary,
)


def _summary_response(transaction_count: int = 10) -> ProjectAnalyticsResponse:
    return ProjectAnalyticsResponse(
        sales=ProjectSalesSummary(
            transaction_count=transaction_count,
            total_volume=1_000_000,
            avg_price=100_000,
            avg_price_sqm=1_000,
            median_price=90_000,
        ),
        rentals=ProjectRentalSummary(
            contract_count=5,
            total_annual_value=250_000,
            median_annual_rent=50_000,
            median_rent_sqm=500,
        ),
        overall_gross_yield_pct=5.5,
        by_rooms=[],
        by_property_type=[],
        by_reg_type=[],
        unit_composition=[],
        configuration_analysis=[],
    )


async def test_project_summary_endpoint_uses_cache(client, monkeypatch):
    fresh_response = _summary_response(transaction_count=10)
    cached_response = jsonable_encoder(_summary_response(transaction_count=99))
    get_mock = AsyncMock(side_effect=[None, cached_response])
    set_mock = AsyncMock()
    summary_mock = AsyncMock(return_value=fresh_response)

    monkeypatch.setattr("app.core.decorators.cache.get", get_mock)
    monkeypatch.setattr("app.core.decorators.cache.set", set_mock)
    monkeypatch.setattr("app.analytics.router.get_project_summary", summary_mock)

    first_response = await client.get("/api/v1/analytics/project/summary")
    second_response = await client.get("/api/v1/analytics/project/summary")

    assert first_response.status_code == 200
    assert first_response.json()["sales"]["transaction_count"] == 10
    assert second_response.status_code == 200
    assert second_response.json()["sales"]["transaction_count"] == 99
    summary_mock.assert_awaited_once()
    assert get_mock.await_count == 2
    set_mock.assert_awaited_once()
