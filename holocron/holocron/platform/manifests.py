from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import Field, TypeAdapter

from holocron.pydantic_helpers import HolocronModel, NonBlankStr


class RawManifestFileModel(HolocronModel):
    path: NonBlankStr
    s3_key: NonBlankStr
    sha256: str = ""
    size_bytes: int | None = Field(default=None, ge=0)
    row_count: int | None = Field(default=None, ge=0)
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


RawManifestFileListAdapter = TypeAdapter(list[RawManifestFileModel])


class RawManifestModel(HolocronModel):
    source: NonBlankStr
    run_id: NonBlankStr
    extract_date: str = ""
    created_at: str = ""
    manifest_version: int = Field(default=1, ge=1)
    schema_version: int = Field(default=1, ge=1)
    files: list[RawManifestFileModel] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dataset_kind: str | None = None
    data_scope: str | None = None
    manifest_s3_key: str = ""


def raw_manifest_prefix(*, source: str) -> str:
    return f"raw/source={source}/manifests/"


def raw_file_prefix(*, source: str, extract_date: str, run_id: str) -> str:
    return f"raw/source={source}/extract_date={extract_date}/run_id={run_id}/"


def manifest_s3_key(*, source: str, run_id: str) -> str:
    return f"{raw_manifest_prefix(source=source)}{run_id}.json"


def raw_file_s3_key(*, source: str, extract_date: str, run_id: str, file_name: str) -> str:
    return f"{raw_file_prefix(source=source, extract_date=extract_date, run_id=run_id)}{file_name}"


def require_normal_raw_manifest_key(*, source: str, manifest_key: str) -> None:
    prefix = raw_manifest_prefix(source=source)
    file_name = _string_value(manifest_key).removeprefix(prefix)
    if (
        not manifest_key.startswith(prefix)
        or not manifest_key.endswith(".json")
        or not file_name
        or "/" in file_name
    ):
        raise ValueError(
            f"Normal raw manifest keys must use {prefix}<run_id>.json; got {manifest_key!r}"
        )


def require_normal_raw_manifest(
    *, source: str, manifest_key: str, manifest: Mapping[str, Any]
) -> None:
    require_normal_raw_manifest_key(source=source, manifest_key=manifest_key)
    if raw_manifest_is_smoke(manifest):
        raise ValueError(
            f"Smoke raw manifest cannot be used for normal bronze loads or dataset versions: "
            f"{manifest_key}"
        )

    run_id = _string_value(manifest.get("run_id"))
    extract_date = _string_value(manifest.get("extract_date"))
    if not run_id:
        raise ValueError(f"Raw manifest is missing run_id: {manifest_key}")
    if not extract_date:
        raise ValueError(f"Raw manifest is missing extract_date: {manifest_key}")

    file_prefix = raw_file_prefix(source=source, extract_date=extract_date, run_id=run_id)
    files = manifest.get("files")
    if not isinstance(files, list):
        return
    for index, file_entry in enumerate(files):
        if not isinstance(file_entry, dict):
            continue
        file_entry = cast(dict[str, Any], file_entry)
        s3_key = _string_value(file_entry.get("s3_key"))
        if not s3_key.startswith(file_prefix):
            raise ValueError(
                "Normal raw manifest file keys must use "
                f"{file_prefix}<file>; got {s3_key!r} at {manifest_key}#{index}"
            )


def raw_manifest_is_smoke(manifest: Mapping[str, Any]) -> bool:
    metadata = manifest.get("metadata")
    markers = [manifest.get("dataset_kind"), manifest.get("data_scope")]
    if isinstance(metadata, Mapping):
        if metadata.get("smoke") is True:
            return True
        markers.extend([metadata.get("dataset_kind"), metadata.get("data_scope")])
    return any(_string_value(marker).lower() == "smoke" for marker in markers)


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
