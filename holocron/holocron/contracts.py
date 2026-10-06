from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


JsonObject = dict[str, Any]
RawManifest = dict[str, Any]
RawManifestFile = dict[str, Any]
BronzeLoadResult = dict[str, Any]
Check = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class RawFile:
    path: str
    sha256: str
    size_bytes: int
    row_count: int | None = None
    content_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawRelease:
    source: str
    run_id: str
    extract_date: str
    created_at: str
    files: tuple[RawFile, ...]
    manifest_version: int = 1
    schema_version: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)


Extractor = Callable[..., RawRelease]


class RawFileStore(Protocol):
    def download_file(self, *, key: str, path: str | Path) -> None: ...


class ObjectLister(Protocol):
    def list_keys(self, *, prefix: str) -> list[str]: ...


class JsonObjectStore(Protocol):
    def get_json(self, *, key: str) -> JsonObject | None: ...


class JsonObjectWriter(Protocol):
    def put_json(self, *, key: str, payload: JsonObject) -> None: ...


class JsonObjectReadWriter(JsonObjectStore, JsonObjectWriter, Protocol): ...


class TextObjectStore(Protocol):
    def read_text(self, *, key: str, encoding: str = "utf-8") -> str: ...


class BytesObjectStore(Protocol):
    def put_bytes(self, *, key: str, payload: bytes, content_type: str | None = None) -> None: ...


class PublicUrlStore(Protocol):
    def public_url(self, *, key: str) -> str | None: ...


class ManifestStore(JsonObjectStore, ObjectLister, Protocol): ...


class BronzeReplayStore(ManifestStore, RawFileStore, Protocol): ...


class ClickHouseCommands(Protocol):
    def command(self, sql: str) -> Any: ...


class ClickHouseInserter(ClickHouseCommands, Protocol):
    def insert_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
    ) -> None: ...


class ClickHouseReplacer(ClickHouseCommands, Protocol):
    def replace_table_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
        staging_suffix: str = "replace_rows",
    ) -> int: ...


class ClickHouseWriter(ClickHouseInserter, ClickHouseReplacer, Protocol): ...


class BronzeLoader(Protocol):
    def __call__(
        self,
        *,
        raw_manifest: RawManifest,
        s3: RawFileStore,
        clickhouse: ClickHouseWriter,
    ) -> BronzeLoadResult: ...


@dataclass(frozen=True, slots=True)
class BronzeTable:
    name: str
    source_key: str | None = None


@dataclass(frozen=True, slots=True)
class SourceSpec:
    name: str
    provider: str
    extractor: Extractor
    bronze_loader: BronzeLoader | None = None
    bronze_tables: Sequence[BronzeTable] = ()
    checks: Sequence[Check] = ()
    checkpoint_strategy: str = "full_refresh"
    cadence: str | None = None
    description: str | None = None
