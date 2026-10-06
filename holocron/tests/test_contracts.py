from datetime import UTC, datetime

from holocron.contracts import BronzeTable, RawFile, RawRelease, SourceSpec
from holocron.platform.clickhouse import quote_clickhouse_identifier
from holocron.platform.execution import build_raw_release


def _extract() -> RawRelease:
    return RawRelease(
        source="example_source",
        run_id="run-1",
        extract_date="2026-03-31",
        created_at="2026-03-31T12:00:00+00:00",
        files=(),
    )


def test_build_raw_release_shapes_core_manifest_fields() -> None:
    source = SourceSpec(
        name="example_source",
        provider="example",
        extractor=_extract,
        bronze_tables=(BronzeTable(name="example_bronze"),),
    )
    release = build_raw_release(
        source=source,
        files=(RawFile(path="rows.jsonl", sha256="abc", size_bytes=42),),
        now=datetime(2026, 3, 31, 12, 0, tzinfo=UTC),
    )

    assert release.source == "example_source"
    assert release.run_id == "2026-03-31T12-00-00Z"
    assert release.extract_date == "2026-03-31"
    assert release.files[0].path == "rows.jsonl"


def test_quote_clickhouse_identifier_accepts_simple_identifiers() -> None:
    assert quote_clickhouse_identifier("dda_land_plots") == "`dda_land_plots`"


def test_quote_clickhouse_identifier_rejects_unsafe_identifiers() -> None:
    try:
        quote_clickhouse_identifier("dda_land_plots; DROP TABLE users")
    except ValueError as exc:
        assert "Invalid ClickHouse identifier" in str(exc)
    else:
        raise AssertionError("unsafe identifier should be rejected")
