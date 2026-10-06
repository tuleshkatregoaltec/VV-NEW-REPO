from typing import Any

import pytest

from holocron.platform.dataset_versions import (
    DatasetVersionDescriptorModel,
    LATEST_COMPLETE_DATASET_VERSION,
    build_dataset_version_descriptor,
    dataset_version_key,
    latest_complete_dataset_version_key,
    promote_latest_complete,
    read_dataset_version,
    validate_dataset_version_descriptor,
    write_dataset_version,
)
from holocron.sources import registry
from tests.fakes import FakeS3 as _FakeS3Base


class FakeS3(_FakeS3Base):
    """FakeS3 variant that stores JSON objects in json_objects and searches there for list_keys."""

    def __init__(self, objects: dict[str, dict[str, Any]]) -> None:
        super().__init__()
        self.json_objects = dict(objects)

    def list_keys(self, *, prefix: str) -> list[str]:
        return [key for key in self.json_objects if key.startswith(prefix)]


def _manifest_key(source_name: str, run_id: str) -> str:
    return f"raw/source={source_name}/manifests/{run_id}.json"


def _manifest(source_name: str, run_id: str, *, row_count: int = 1) -> dict:
    return {
        "source": source_name,
        "run_id": run_id,
        "extract_date": "2026-05-01",
        "files": [
            {
                "path": "rows.jsonl",
                "s3_key": f"raw/source={source_name}/extract_date=2026-05-01/run_id={run_id}/rows.jsonl",
                "row_count": row_count,
            }
        ],
    }


def _source():
    return registry.get("dxbi_transactions")


def _descriptor(source_name: str = "dxbi_transactions", *, status: str = "complete") -> dict:
    source = _source()
    return {
        "source": source_name,
        "dataset_version": "2026-05-01T00-00-00Z",
        "status": status,
        "created_at": "2026-05-01T00:00:00+00:00",
        "base_manifest_keys": [_manifest_key(source.name, "run-1")],
        "incremental_manifest_keys": [_manifest_key(source.name, "run-2")],
        "manifest_keys": [_manifest_key(source.name, "run-1"), _manifest_key(source.name, "run-2")],
        "table_names": [table.name for table in source.bronze_tables],
        "replay_strategy": "truncate_then_apply_ordered_manifests",
        "coverage": {"window_start": "2026-01-01", "window_end": "2026-05-01"},
        "notes": "curated restore set",
    }


def _s3_for_descriptor(descriptor: dict) -> FakeS3:
    source_name = descriptor["source"]
    return FakeS3(
        {
            _manifest_key(source_name, "run-1"): _manifest(source_name, "run-1"),
            _manifest_key(source_name, "run-2"): _manifest(source_name, "run-2"),
        }
    )


def _s3_for_keys(source_name: str, keys: list[str]) -> FakeS3:
    objects: dict[str, dict] = {}
    for key in keys:
        run_id = key.rsplit("/", 1)[-1].removesuffix(".json")
        objects[key] = _manifest(source_name, run_id)
    return FakeS3(objects)


def test_validate_dataset_version_descriptor_accepts_valid_complete_descriptor() -> None:
    source = _source()
    descriptor = _descriptor()

    validated = validate_dataset_version_descriptor(
        descriptor=descriptor,
        source=source,
        s3=_s3_for_descriptor(descriptor),
    )

    assert validated["manifest_keys"] == [
        _manifest_key(source.name, "run-1"),
        _manifest_key(source.name, "run-2"),
    ]
    assert validated["coverage"]["window_start"] == "2026-01-01"


def test_dataset_version_descriptor_model_defaults_optional_control_fields() -> None:
    descriptor = _descriptor()
    descriptor.pop("coverage")
    descriptor.pop("notes")

    model = DatasetVersionDescriptorModel.model_validate(descriptor)
    validated = validate_dataset_version_descriptor(
        descriptor=descriptor,
        source=_source(),
        s3=_s3_for_descriptor(descriptor),
    )

    assert model.coverage == {}
    assert model.notes == ""
    assert validated["coverage"] == {}
    assert validated["notes"] == ""


def test_validate_dataset_version_descriptor_rejects_source_mismatch() -> None:
    with pytest.raises(ValueError, match="source mismatch"):
        validate_dataset_version_descriptor(
            descriptor=_descriptor(source_name="other_source"),
            source=_source(),
            s3=FakeS3({}),
        )


def test_validate_dataset_version_descriptor_rejects_empty_manifests() -> None:
    descriptor = _descriptor()
    descriptor["base_manifest_keys"] = []
    descriptor["incremental_manifest_keys"] = []
    descriptor["manifest_keys"] = []

    with pytest.raises(ValueError, match="manifest_keys must not be empty"):
        validate_dataset_version_descriptor(
            descriptor=descriptor,
            source=_source(),
            s3=FakeS3({}),
        )


def test_validate_dataset_version_descriptor_rejects_duplicate_manifests() -> None:
    descriptor = _descriptor()
    duplicate = _manifest_key("dxbi_transactions", "run-1")
    descriptor["base_manifest_keys"] = [duplicate]
    descriptor["incremental_manifest_keys"] = [duplicate]
    descriptor["manifest_keys"] = [duplicate, duplicate]

    with pytest.raises(ValueError, match="duplicates"):
        validate_dataset_version_descriptor(
            descriptor=descriptor,
            source=_source(),
            s3=FakeS3({}),
        )


def test_validate_dataset_version_descriptor_rejects_smoke_manifest_keys() -> None:
    source = _source()
    smoke_key = f"smoke/raw/source={source.name}/manifests/run-1.json"
    descriptor = _descriptor()
    descriptor["base_manifest_keys"] = [smoke_key]
    descriptor["incremental_manifest_keys"] = []
    descriptor["manifest_keys"] = [smoke_key]

    with pytest.raises(ValueError, match="Normal raw manifest keys"):
        validate_dataset_version_descriptor(
            descriptor=descriptor,
            source=source,
            s3=FakeS3({smoke_key: _manifest(source.name, "run-1")}),
        )


def test_validate_dataset_version_descriptor_rejects_smoke_marked_manifests() -> None:
    source = _source()
    key = _manifest_key(source.name, "run-1")
    descriptor = _descriptor()
    descriptor["base_manifest_keys"] = [key]
    descriptor["incremental_manifest_keys"] = []
    descriptor["manifest_keys"] = [key]
    manifest = _manifest(source.name, "run-1")
    manifest["metadata"] = {"data_scope": "smoke"}

    with pytest.raises(ValueError, match="Smoke raw manifest"):
        validate_dataset_version_descriptor(
            descriptor=descriptor,
            source=source,
            s3=FakeS3({key: manifest}),
        )


def test_validate_dataset_version_descriptor_rejects_unknown_bronze_table() -> None:
    descriptor = _descriptor()
    descriptor["table_names"] = ["unknown_bronze"]

    with pytest.raises(ValueError, match="bronze_tables"):
        validate_dataset_version_descriptor(
            descriptor=descriptor,
            source=_source(),
            s3=FakeS3({}),
        )


def test_validate_dataset_version_descriptor_rejects_duplicate_table_names() -> None:
    descriptor = _descriptor()
    descriptor["table_names"] = [descriptor["table_names"][0], descriptor["table_names"][0]]

    with pytest.raises(ValueError, match="table_names must not contain duplicates"):
        validate_dataset_version_descriptor(
            descriptor=descriptor,
            source=_source(),
            s3=FakeS3({}),
        )


def test_validate_dataset_version_descriptor_rejects_non_complete_for_replay() -> None:
    with pytest.raises(ValueError, match="status must be complete"):
        validate_dataset_version_descriptor(
            descriptor=_descriptor(status="draft"),
            source=_source(),
            s3=FakeS3({}),
            require_complete=True,
        )


def test_write_promote_and_read_dataset_version_resolve_keys_preserving_order() -> None:
    source = _source()
    descriptor = build_dataset_version_descriptor(
        source=source,
        dataset_version="2026-05-01T00-00-00Z",
        base_manifest_keys=[_manifest_key(source.name, "run-1")],
        incremental_manifest_keys=[_manifest_key(source.name, "run-2")],
        coverage={"shape": "base-plus-incrementals"},
    )
    s3 = _s3_for_descriptor(descriptor)

    key = write_dataset_version(s3=s3, source=source, descriptor=descriptor)
    assert key == dataset_version_key(source=source.name, dataset_version="2026-05-01T00-00-00Z")

    explicit = read_dataset_version(s3=s3, source=source, identifier=key)
    assert explicit.key == key
    assert explicit.manifest_keys == (
        _manifest_key(source.name, "run-1"),
        _manifest_key(source.name, "run-2"),
    )

    latest_key = promote_latest_complete(s3=s3, source=source, identifier=key)
    assert latest_key == latest_complete_dataset_version_key(source=source.name)

    latest = read_dataset_version(
        s3=s3,
        source=source,
        identifier=LATEST_COMPLETE_DATASET_VERSION,
    )
    assert latest.key == latest_key
    assert latest.dataset_version == "2026-05-01T00-00-00Z"
    assert latest.manifest_keys == explicit.manifest_keys


@pytest.mark.parametrize(
    ("source_name", "base_run_ids", "incremental_run_ids"),
    [
        ("pf_locations", ["full-refresh"], []),
        ("pf_listings", ["snapshot-plan", "snapshot-search"], ["detail-delta", "latest-delta"]),
        ("dld_od_transactions", ["chunk-1", "chunk-2", "chunk-3"], []),
    ],
)
def test_validate_dataset_version_descriptor_accepts_representative_shapes(
    source_name: str,
    base_run_ids: list[str],
    incremental_run_ids: list[str],
) -> None:
    source = registry.get(source_name)
    base_keys = [_manifest_key(source_name, run_id) for run_id in base_run_ids]
    incremental_keys = [_manifest_key(source_name, run_id) for run_id in incremental_run_ids]

    descriptor = build_dataset_version_descriptor(
        source=source,
        dataset_version="2026-05-01T00-00-00Z",
        base_manifest_keys=base_keys,
        incremental_manifest_keys=incremental_keys,
    )
    validated = validate_dataset_version_descriptor(
        descriptor=descriptor,
        source=source,
        s3=_s3_for_keys(source_name, [*base_keys, *incremental_keys]),
    )

    assert validated["manifest_keys"] == [*base_keys, *incremental_keys]
    assert validated["table_names"] == [table.name for table in source.bronze_tables]
