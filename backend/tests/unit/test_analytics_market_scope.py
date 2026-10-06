from app.analytics.queries import (
    area_supply_projects,
    project_price_trends,
    project_rentals_by_rooms,
    project_units_composition,
)
from app.analytics.router import _resolve_project_scope
from app.clickhouse.queries import _project_filter


def test_default_project_scope_resolves_to_dubai_market() -> None:
    assert _resolve_project_scope(
        master_project=None,
        project=None,
        filter_type="project",
    ) == ("Dubai", "market")


def test_market_scope_uses_unfiltered_project_predicate() -> None:
    assert _project_filter("market") == "1 = 1"
    assert "{project_name" not in project_price_trends(filter_type="market")
    assert "{project_name" not in project_rentals_by_rooms(filter_type="market")
    assert "{project_name" not in project_units_composition(filter_type="market")
    assert "{area_name" not in area_supply_projects(filter_by_area=False)


def test_pipeline_developer_joins_cannot_multiply_empty_names() -> None:
    sql = area_supply_projects(filter_by_area=False)

    assert sql.count("ANY LEFT JOIN ch_developers") == 4
    assert "notEmpty(trim(BOTH ' ' FROM ifNull(p.developer_name, '')))" in sql
    assert "notEmpty(trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')))" in sql
