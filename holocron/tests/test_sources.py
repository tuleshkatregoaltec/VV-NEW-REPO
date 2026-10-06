import pytest

from holocron.contracts import BronzeTable, RawRelease, SourceSpec
from holocron.sources.registry import SourceRegistry


def _extract() -> RawRelease:
    return RawRelease(
        source="example_source",
        run_id="run-1",
        extract_date="2026-05-01",
        created_at="2026-05-01T00:00:00+00:00",
        files=(),
    )


def test_registry_registers_and_returns_sources() -> None:
    registry = SourceRegistry()
    source = SourceSpec(name="example_source", provider="example", extractor=_extract)

    registry.register(source)

    assert registry.get("example_source") is source
    assert registry.list_sources() == (source,)


def test_registry_rejects_duplicate_source_names() -> None:
    registry = SourceRegistry()
    source = SourceSpec(name="example_source", provider="example", extractor=_extract)

    registry.register(source)

    with pytest.raises(ValueError, match="Duplicate source"):
        registry.register(source)


def test_registry_rejects_blank_source_contract_fields() -> None:
    registry = SourceRegistry()
    source = SourceSpec(name=" ", provider="example", extractor=_extract)

    with pytest.raises(ValueError, match=r"source\.name must be a non-blank string"):
        registry.register(source)


def test_registry_rejects_duplicate_bronze_table_names() -> None:
    registry = SourceRegistry()
    source = SourceSpec(
        name="example_source",
        provider="example",
        extractor=_extract,
        bronze_tables=(BronzeTable("example_bronze"), BronzeTable("example_bronze")),
    )

    with pytest.raises(ValueError, match="bronze table names must be unique"):
        registry.register(source)
