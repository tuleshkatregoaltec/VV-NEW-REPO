from holocron.platform.clickhouse_schema import iter_sql_statements
from pathlib import Path


def test_schema_parser_ignores_semicolons_in_comments_and_string_literals() -> None:
    sql = """
    -- This comment contains a semicolon; it is not a query.
    CREATE TABLE example (value String DEFAULT 'one;two');
    -- Another comment.
    CREATE VIEW example_view AS SELECT 'it''s;valid' AS value;
    """

    statements = iter_sql_statements(sql)

    assert statements == [
        "CREATE TABLE example (value String DEFAULT 'one;two')",
        "CREATE VIEW example_view AS SELECT 'it''s;valid' AS value",
    ]


def test_rental_v2_schema_uses_contract_identity_and_exposes_health() -> None:
    schema = (
        Path(__file__).parents[1] / "holocron" / "lib" / "sql" / "clickhouse_schema.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS dxbi_rental_events_v2" in schema
    assert "event_key          String ALIAS contract_key" in schema
    assert "ORDER BY (lease_start, contract_key)" in schema
    assert "CREATE TABLE IF NOT EXISTS dxbi_rental_run_reconciliation" in schema
    assert "CREATE OR REPLACE VIEW dxbi_rental_ingestion_health" in schema
