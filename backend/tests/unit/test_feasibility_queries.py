import pytest

from app.feasibility import queries


@pytest.mark.asyncio
async def test_land_sale_evidence_prioritizes_recent_transactions(monkeypatch):
    captured_sql: list[str] = []

    async def fake_query(sql: str, params: dict):
        captured_sql.append(sql)
        return []

    monkeypatch.setattr(queries, "query", fake_query)

    await queries.get_land_sale_evidence(
        area_name="Business Bay",
        plot_area_sqm=1000.0,
        usage="residential",
        target_far=4.0,
    )

    assert captured_sql
    assert all(
        "ORDER BY\n            instance_date DESC,\n            abs(" in sql for sql in captured_sql
    )
