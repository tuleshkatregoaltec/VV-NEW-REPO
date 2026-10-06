import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).parents[1] / "scripts" / "report_dxbi_rental_coverage.py"
    spec = importlib.util.spec_from_file_location("report_dxbi_rental_coverage", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_residuals_are_classified_without_assuming_dld_parity() -> None:
    report = _load_script()

    rows = report.classify_rows(
        [
            {
                "month": "2026-01-01",
                "market_scope": "residential_home",
                "dxbi_rows": 90,
                "dld_rows": 100,
                "registered_after_365_days": 4,
            },
            {
                "month": "2026-01-01",
                "market_scope": "bulk_or_multi",
                "dxbi_rows": 0,
                "dld_rows": 12,
                "registered_after_365_days": 0,
            },
        ],
        quarantine_rows=2,
    )

    assert rows[0]["residual_classification"] == {
        "dxbi_source_scope": 0,
        "registration_lag": 4,
        "parsing_quarantine": 2,
        "unresolved": 4,
    }
    assert rows[1]["residual_classification"]["dxbi_source_scope"] == 12
    assert rows[1]["residual_classification"]["unresolved"] == 0


def test_coverage_sql_conservatively_removes_only_cross_project_fanout() -> None:
    report = _load_script()

    sql = report.coverage_sql("dxbi_rental_events_v2")

    assert "tuple(project_name_en, master_project_en) AS project_label" in sql
    assert "area_name_en" in sql
    assert "max(project_multiplicity) AS defanned_rows_at_signature" in sql
    assert "sum(raw_rows_at_signature - defanned_rows_at_signature)" in sql
    assert "ifNull(dld.dld_raw_rows, 0) AS dld_raw_rows" in sql
    assert "ifNull(dld.dld_project_fanout_rows, 0) AS dld_project_fanout_rows" in sql
    assert "FROM all_keys" in sql
    assert "FULL OUTER JOIN" not in sql


def test_coverage_sql_supports_a_separate_shadow_benchmark_database() -> None:
    report = _load_script()

    sql = report.coverage_sql(
        "dxbi_rental_events_v2", "`vitevue`.`silver_rent_contracts`"
    )

    assert "FROM `vitevue`.`silver_rent_contracts` FINAL" in sql
