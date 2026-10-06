from __future__ import annotations

from collections import Counter

from pydantic import TypeAdapter, ValidationError

from holocron.contracts import SourceSpec
from holocron.pydantic_helpers import NonBlankStr

_NonBlankStringAdapter = TypeAdapter(NonBlankStr)


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, SourceSpec] = {}

    def register(self, source: SourceSpec) -> None:
        _validate_source_spec(source)
        if source.name in self._sources:
            raise ValueError(f"Duplicate source: {source.name}")
        self._sources[source.name] = source

    def get(self, name: str) -> SourceSpec:
        if name not in self._sources:
            raise KeyError(f"Unknown source: {name}")
        return self._sources[name]

    def list_sources(self) -> tuple[SourceSpec, ...]:
        return tuple(self._sources.values())


def _validate_source_spec(source: SourceSpec) -> None:
    source_name = _validate_non_blank(source.name, field_name="source.name")
    _validate_non_blank(source.provider, field_name=f"{source_name}.provider")
    table_names: list[str] = []
    for table in source.bronze_tables:
        table_name = _validate_non_blank(
            table.name,
            field_name=f"{source_name}.bronze_tables.name",
        )
        table_names.append(table_name)
        if table.source_key is not None:
            _validate_non_blank(
                table.source_key,
                field_name=f"{source_name}.bronze_tables.source_key",
            )
    duplicates = sorted(name for name, count in Counter(table_names).items() if count > 1)
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(f"{source_name} bronze table names must be unique: {joined}")


def _validate_non_blank(value: str, *, field_name: str) -> str:
    try:
        return _NonBlankStringAdapter.validate_python(value)
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be a non-blank string") from exc
