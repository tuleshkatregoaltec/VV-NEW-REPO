from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field, TypeAdapter, ValidationError, field_validator, model_validator

from holocron.contracts import JsonObjectReadWriter, JsonObjectStore, ManifestStore, SourceSpec
from holocron.platform.manifests import (
    manifest_s3_key,
    raw_manifest_prefix,
    require_normal_raw_manifest,
    require_normal_raw_manifest_key,
)
from holocron.platform.raw_files import read_and_validate_manifest, string_value
from holocron.pydantic_helpers import HolocronModel, NonBlankStr
from holocron.platform.object_storage import ObjectStorageClient
from holocron.platform.settings import settings
from holocron.sources import registry

LATEST_COMPLETE_DATASET_VERSION = "latest_complete"
DATASET_VERSION_REPLAY_STRATEGY = "truncate_then_apply_ordered_manifests"
_NON_BLANK_SEQUENCE_ADAPTER = TypeAdapter(tuple[NonBlankStr, ...])


class DatasetVersionDescriptorModel(HolocronModel):
    source: NonBlankStr
    dataset_version: NonBlankStr
    status: NonBlankStr
    created_at: NonBlankStr
    base_manifest_keys: tuple[NonBlankStr, ...]
    incremental_manifest_keys: tuple[NonBlankStr, ...]
    manifest_keys: tuple[NonBlankStr, ...]
    table_names: tuple[NonBlankStr, ...]
    replay_strategy: NonBlankStr
    coverage: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""

    @field_validator("coverage", mode="before")
    @classmethod
    def default_coverage(cls, value: object) -> object:
        if value is None:
            return {}
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def default_notes(cls, value: object) -> object:
        if value is None:
            return ""
        return value

    @model_validator(mode="after")
    def validate_descriptor(self) -> "DatasetVersionDescriptorModel":
        if not self.manifest_keys:
            raise ValueError("Dataset version descriptor manifest_keys must not be empty")
        if len(set(self.manifest_keys)) != len(self.manifest_keys):
            raise ValueError("Dataset version descriptor manifest_keys must not contain duplicates")
        expected_order = (*self.base_manifest_keys, *self.incremental_manifest_keys)
        if self.manifest_keys != expected_order:
            raise ValueError(
                "Dataset version descriptor manifest_keys must equal "
                "base_manifest_keys plus incremental_manifest_keys in order"
            )
        if len(set(self.table_names)) != len(self.table_names):
            raise ValueError("Dataset version descriptor table_names must not contain duplicates")
        return self


@dataclass(frozen=True, slots=True)
class DatasetVersionSelection:
    key: str
    descriptor: dict[str, Any]

    @property
    def dataset_version(self) -> str:
        return str(self.descriptor["dataset_version"])

    @property
    def manifest_keys(self) -> tuple[str, ...]:
        return tuple(self.descriptor["manifest_keys"])


def dataset_version_key(*, source: str, dataset_version: str) -> str:
    version = string_value(dataset_version)
    if not version:
        raise ValueError("dataset_version must not be blank")
    if version == LATEST_COMPLETE_DATASET_VERSION:
        raise ValueError(f"{LATEST_COMPLETE_DATASET_VERSION!r} is a reserved dataset version alias")
    return f"raw/source={source}/dataset_versions/{version}.json"


def latest_complete_dataset_version_key(*, source: str) -> str:
    return f"raw/source={source}/dataset_versions/{LATEST_COMPLETE_DATASET_VERSION}.json"


def resolve_dataset_version_key(*, source: str, identifier: str) -> str:
    value = string_value(identifier)
    if not value:
        raise ValueError("dataset version identifier must not be blank")
    if value == LATEST_COMPLETE_DATASET_VERSION:
        return latest_complete_dataset_version_key(source=source)
    if value.startswith("raw/source="):
        return value
    return dataset_version_key(source=source, dataset_version=value)


def build_dataset_version_descriptor(
    *,
    source: SourceSpec,
    dataset_version: str,
    manifest_keys: Sequence[str] = (),
    base_manifest_keys: Sequence[str] = (),
    incremental_manifest_keys: Sequence[str] = (),
    coverage: dict[str, Any] | None = None,
    notes: str = "",
    status: str = "complete",
    created_at: str | None = None,
) -> dict[str, Any]:
    if manifest_keys:
        if base_manifest_keys or incremental_manifest_keys:
            raise ValueError(
                "manifest_keys cannot be combined with base_manifest_keys or "
                "incremental_manifest_keys"
            )
        base_manifest_keys = tuple(manifest_keys)

    base_keys = tuple(_clean_string_sequence(base_manifest_keys, "base_manifest_keys"))
    incremental_keys = tuple(
        _clean_string_sequence(incremental_manifest_keys, "incremental_manifest_keys")
    )
    ordered_manifest_keys = [*base_keys, *incremental_keys]
    table_names = [table.name for table in source.bronze_tables]
    descriptor = {
        "source": source.name,
        "dataset_version": string_value(dataset_version),
        "status": string_value(status) or "complete",
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "base_manifest_keys": list(base_keys),
        "incremental_manifest_keys": list(incremental_keys),
        "manifest_keys": ordered_manifest_keys,
        "table_names": table_names,
        "replay_strategy": DATASET_VERSION_REPLAY_STRATEGY,
        "coverage": coverage or {},
        "notes": notes,
    }
    return DatasetVersionDescriptorModel.model_validate(descriptor).model_dump(mode="json")


def validate_dataset_version_descriptor(
    *,
    descriptor: dict[str, Any],
    source: SourceSpec,
    s3: JsonObjectStore | None = None,
    require_complete: bool = True,
) -> dict[str, Any]:
    if not isinstance(descriptor, dict):
        raise TypeError("Dataset version descriptor must be an object")

    descriptor_model = DatasetVersionDescriptorModel.model_validate(descriptor)

    descriptor_source = descriptor_model.source
    if descriptor_source != source.name:
        raise ValueError(
            f"Dataset version source mismatch: expected {source.name}, got {descriptor_source!r}"
        )

    dataset_version = descriptor_model.dataset_version

    status = descriptor_model.status
    if require_complete and status != "complete":
        raise ValueError(
            f"Dataset version status must be complete for replay: "
            f"dataset_version={dataset_version} status={status!r}"
        )

    created_at = descriptor_model.created_at
    base_manifest_keys = list(descriptor_model.base_manifest_keys)
    incremental_manifest_keys = list(descriptor_model.incremental_manifest_keys)
    manifest_keys = list(descriptor_model.manifest_keys)
    for manifest_key in manifest_keys:
        require_normal_raw_manifest_key(source=source.name, manifest_key=manifest_key)

    table_names = list(descriptor_model.table_names)
    expected_table_names = [table.name for table in source.bronze_tables]
    if set(table_names) != set(expected_table_names):
        raise ValueError(
            "Dataset version table_names must match source bronze_tables: "
            f"expected={expected_table_names!r} got={table_names!r}"
        )

    replay_strategy = descriptor_model.replay_strategy
    if replay_strategy != DATASET_VERSION_REPLAY_STRATEGY:
        raise ValueError(
            "Dataset version replay_strategy must be "
            f"{DATASET_VERSION_REPLAY_STRATEGY!r}, got {replay_strategy!r}"
        )

    coverage = descriptor_model.coverage
    notes = descriptor_model.notes

    if s3 is not None:
        for manifest_key in manifest_keys:
            manifest = read_and_validate_manifest(
                s3=s3,
                source_name=source.name,
                manifest_key=manifest_key,
            )
            require_normal_raw_manifest(
                source=source.name,
                manifest_key=manifest_key,
                manifest=manifest,
            )

    return {
        "source": source.name,
        "dataset_version": dataset_version,
        "status": status,
        "created_at": created_at,
        "base_manifest_keys": base_manifest_keys,
        "incremental_manifest_keys": incremental_manifest_keys,
        "manifest_keys": manifest_keys,
        "table_names": table_names,
        "replay_strategy": replay_strategy,
        "coverage": coverage,
        "notes": notes,
    }


def read_dataset_version(
    *,
    s3: JsonObjectStore,
    source: SourceSpec,
    identifier: str,
    require_complete: bool = True,
) -> DatasetVersionSelection:
    key = resolve_dataset_version_key(source=source.name, identifier=identifier)
    descriptor = s3.get_json(key=key)
    if descriptor is None:
        raise FileNotFoundError(f"Dataset version descriptor not found: {key}")
    validated = validate_dataset_version_descriptor(
        descriptor=descriptor,
        source=source,
        s3=s3,
        require_complete=require_complete,
    )
    return DatasetVersionSelection(key=key, descriptor=validated)


def write_dataset_version(
    *,
    s3: JsonObjectReadWriter,
    source: SourceSpec,
    descriptor: dict[str, Any],
) -> str:
    validated = validate_dataset_version_descriptor(
        descriptor=descriptor,
        source=source,
        s3=s3,
        require_complete=False,
    )
    key = dataset_version_key(source=source.name, dataset_version=validated["dataset_version"])
    s3.put_json(key=key, payload=validated)
    return key


def promote_latest_complete(
    *, s3: JsonObjectReadWriter, source: SourceSpec, identifier: str
) -> str:
    selection = read_dataset_version(
        s3=s3,
        source=source,
        identifier=identifier,
        require_complete=True,
    )
    latest_key = latest_complete_dataset_version_key(source=source.name)
    s3.put_json(key=latest_key, payload=selection.descriptor)
    return latest_key


def summarize_dataset_versions(*, s3: ManifestStore, source: SourceSpec) -> dict[str, Any]:
    manifest_prefix = raw_manifest_prefix(source=source.name)
    manifest_keys = sorted(
        key for key in s3.list_keys(prefix=manifest_prefix) if key.endswith(".json")
    )
    latest_manifest_key = manifest_keys[-1] if manifest_keys else None
    latest_manifest = s3.get_json(key=latest_manifest_key) if latest_manifest_key else None

    latest_complete_key = latest_complete_dataset_version_key(source=source.name)
    latest_complete: dict[str, Any] | None = None
    latest_complete_error = ""
    try:
        latest_complete = read_dataset_version(
            s3=s3,
            source=source,
            identifier=LATEST_COMPLETE_DATASET_VERSION,
            require_complete=True,
        ).descriptor
    except FileNotFoundError:
        latest_complete = None
    except Exception as exc:  # noqa: BLE001 - operator summary should report descriptor issues.
        latest_complete_error = str(exc)

    descriptor_manifest_rows = 0
    if latest_complete is not None:
        for manifest_key in latest_complete["manifest_keys"]:
            manifest = read_and_validate_manifest(
                s3=s3,
                source_name=source.name,
                manifest_key=manifest_key,
            )
            descriptor_manifest_rows += _manifest_row_count(manifest)

    return {
        "source": source.name,
        "latest_manifest_key": latest_manifest_key,
        "latest_manifest_run_id": latest_manifest.get("run_id") if latest_manifest else None,
        "latest_complete_key": latest_complete_key,
        "latest_complete_dataset_version": (
            latest_complete.get("dataset_version") if latest_complete else None
        ),
        "latest_complete_error": latest_complete_error,
        "manifest_count": len(latest_complete["manifest_keys"]) if latest_complete else 0,
        "manifest_row_count": descriptor_manifest_rows,
        "coverage": latest_complete.get("coverage", {}) if latest_complete else {},
    }


def _manifest_row_count(manifest: dict[str, Any]) -> int:
    return sum(int(file_entry.get("row_count") or 0) for file_entry in manifest.get("files", []))


def _clean_string_sequence(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"Dataset version descriptor {field_name} must be a list")
    try:
        values = list(_NON_BLANK_SEQUENCE_ADAPTER.validate_python(value))
    except ValidationError as exc:
        raise ValueError(
            f"Dataset version descriptor {field_name} must not contain blank values"
        ) from exc
    return values


def _load_coverage(*, coverage_json: str, coverage_file: str) -> dict[str, Any]:
    if coverage_json and coverage_file:
        raise ValueError("--coverage-json and --coverage-file cannot be combined")
    if coverage_file:
        payload = Path(coverage_file).read_text(encoding="utf-8")
    elif coverage_json:
        payload = coverage_json
    else:
        return {}
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("coverage must decode to a JSON object")
    return value


def _manifest_keys_from_run_ids(*, source_name: str, run_ids: Sequence[str]) -> list[str]:
    return [manifest_s3_key(source=source_name, run_id=run_id) for run_id in run_ids]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage raw dataset version descriptors in object storage."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create",
        help="Create a dataset version descriptor from explicit manifest keys.",
    )
    create_parser.add_argument("source")
    create_parser.add_argument("--dataset-version", required=True)
    create_parser.add_argument("--manifest-key", action="append", default=[])
    create_parser.add_argument("--run-id", action="append", default=[])
    create_parser.add_argument("--base-manifest-key", action="append", default=[])
    create_parser.add_argument("--incremental-manifest-key", action="append", default=[])
    create_parser.add_argument("--coverage-json", default="")
    create_parser.add_argument("--coverage-file", default="")
    create_parser.add_argument("--notes", default="")
    create_parser.add_argument("--status", default="complete")

    promote_parser = subparsers.add_parser(
        "promote",
        help="Promote a complete descriptor to latest_complete.",
    )
    promote_parser.add_argument("source")
    promote_parser.add_argument("dataset_version")

    summary_parser = subparsers.add_parser(
        "summary",
        help="Show latest raw manifest and latest complete dataset version summary.",
    )
    summary_parser.add_argument("source")

    args = parser.parse_args(argv)
    source = registry.get(args.source)
    s3 = ObjectStorageClient(settings)

    if args.command == "create":
        coverage = _load_coverage(
            coverage_json=args.coverage_json,
            coverage_file=args.coverage_file,
        )
        manifest_keys = [
            *args.manifest_key,
            *_manifest_keys_from_run_ids(source_name=source.name, run_ids=args.run_id),
        ]
        descriptor = build_dataset_version_descriptor(
            source=source,
            dataset_version=args.dataset_version,
            manifest_keys=manifest_keys,
            base_manifest_keys=args.base_manifest_key,
            incremental_manifest_keys=args.incremental_manifest_key,
            coverage=coverage,
            notes=args.notes,
            status=args.status,
        )
        key = write_dataset_version(s3=s3, source=source, descriptor=descriptor)
        print(
            json.dumps(
                {
                    "source": source.name,
                    "dataset_version": descriptor["dataset_version"],
                    "key": key,
                    "manifest_count": len(descriptor["manifest_keys"]),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "promote":
        key = promote_latest_complete(
            s3=s3,
            source=source,
            identifier=args.dataset_version,
        )
        print(json.dumps({"source": source.name, "latest_complete_key": key}, indent=2))
        return 0

    if args.command == "summary":
        print(
            json.dumps(summarize_dataset_versions(s3=s3, source=source), indent=2, sort_keys=True)
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
