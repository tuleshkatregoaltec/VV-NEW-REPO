from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from holocron.contracts import (
    BronzeLoadResult,
    BronzeLoader,
    ClickHouseWriter,
    Extractor,
    RawFileStore,
    RawManifest,
    RawRelease,
)


def lazy_extractor(module_name: str | None) -> Extractor:
    if not module_name:
        raise ValueError("extractor module name is required")

    def extract_release(*args: Any, **kwargs: Any) -> RawRelease:
        return cast(RawRelease, import_module(module_name).extract_release(*args, **kwargs))

    return extract_release


def lazy_bronze_loader(module_name: str | None) -> BronzeLoader:
    if not module_name:
        raise ValueError("bronze module name is required")

    def load_bronze(
        *, raw_manifest: RawManifest, s3: RawFileStore, clickhouse: ClickHouseWriter
    ) -> BronzeLoadResult:
        return cast(
            BronzeLoadResult,
            import_module(module_name).load_release_to_clickhouse(
                raw_manifest=raw_manifest,
                s3=s3,
                clickhouse=clickhouse,
            ),
        )

    return load_bronze
