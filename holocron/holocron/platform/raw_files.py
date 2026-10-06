from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from holocron.contracts import JsonObjectStore, RawFile, RawFileStore, RawManifest, RawManifestFile
from holocron.platform.execution import build_raw_file
from holocron.platform.manifests import RawManifestFileListAdapter, RawManifestModel

_NDJSON_CONTENT_TYPE = "application/x-ndjson"
_HASH_CHUNK_SIZE_BYTES = 8 * 1024 * 1024


def string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def manifest_files_by_name(raw_manifest: RawManifest) -> dict[str, RawManifestFile]:
    files = raw_manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("raw_manifest.files must be a list")
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("raw_manifest.files must only contain objects")
    try:
        file_models = RawManifestFileListAdapter.validate_python(files)
    except ValidationError as exc:
        raise ValueError(f"raw_manifest.files are invalid: {exc}") from exc

    mapped: dict[str, RawManifestFile] = {}
    for file_model in file_models:
        file_entry = cast(
            RawManifestFile,
            file_model.model_dump(mode="json", exclude_unset=True),
        )
        mapped[Path(file_model.path).name] = file_entry
    return mapped


def require_manifest_file(
    files_by_name: Mapping[str, RawManifestFile], file_name: str
) -> RawManifestFile:
    file_entry = files_by_name.get(file_name)
    if file_entry is None:
        raise KeyError(f"raw_manifest is missing expected file: {file_name}")
    return file_entry


def download_manifest_file(
    *,
    file_name: str,
    file_entry: RawManifestFile,
    s3: RawFileStore,
    scratch_path: Path,
    source_label: str,
) -> Path:
    s3_key = string_value(file_entry.get("s3_key"))
    if not s3_key:
        raise ValueError(f"raw_manifest entry for {file_name} is missing s3_key")
    local_path = scratch_path / file_name
    s3.download_file(key=s3_key, path=local_path)
    validate_file_sha256(path=local_path, file_entry=file_entry, source_label=source_label)
    return local_path


def validate_file_sha256(
    *,
    path: Path,
    file_entry: RawManifestFile,
    source_label: str,
) -> None:
    expected_sha = string_value(file_entry.get("sha256"))
    if not expected_sha:
        return
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE_BYTES), b""):
            hasher.update(chunk)
    actual_sha = hasher.hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(f"{source_label} raw file checksum mismatch: {path.name}")


def build_raw_file_from_path(
    path: str | Path,
    *,
    row_count: int | None = None,
    content_type: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RawFile:
    raw_path = Path(path)
    content = raw_path.read_bytes()
    return build_raw_file(
        path=raw_path,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        row_count=row_count,
        content_type=content_type,
        metadata=metadata,
    )


def write_jsonl_raw_file(
    path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    default: Any = None,
    separators: tuple[str, str] | None = (",", ":"),
    metadata: Mapping[str, Any] | None = None,
) -> RawFile:
    raw_path = Path(path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    row_count = 0
    size_bytes = 0
    dump_kwargs: dict[str, Any] = {
        "ensure_ascii": ensure_ascii,
        "sort_keys": sort_keys,
    }
    if default is not None:
        dump_kwargs["default"] = default
    if separators is not None:
        dump_kwargs["separators"] = separators
    with raw_path.open("wb") as handle:
        for row in rows:
            line = (json.dumps(row, **dump_kwargs) + "\n").encode("utf-8")
            handle.write(line)
            hasher.update(line)
            size_bytes += len(line)
            row_count += 1
    return build_raw_file(
        path=raw_path,
        sha256=hasher.hexdigest(),
        size_bytes=size_bytes,
        row_count=row_count,
        content_type=_NDJSON_CONTENT_TYPE,
        metadata=metadata,
    )


def read_jsonl_manifest_rows(
    *,
    path: Path,
    file_entry: RawManifestFile,
    source_label: str,
) -> list[dict[str, Any]]:
    rows = read_jsonl_file(path=path, source_label=source_label)
    validate_manifest_row_count(
        file_name=path.name,
        file_entry=file_entry,
        actual_row_count=len(rows),
        source_label=source_label,
    )
    return rows


def read_jsonl_file(*, path: Path, source_label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{source_label} raw row must be an object in {path.name}")
            rows.append(payload)
    return rows


def read_csv_manifest_rows(
    *,
    path: Path,
    file_entry: RawManifestFile,
    source_label: str,
) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    validate_manifest_row_count(
        file_name=path.name,
        file_entry=file_entry,
        actual_row_count=len(rows),
        source_label=source_label,
    )
    return rows


def count_csv_rows(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_allow_large_csv_fields()


def read_and_validate_manifest(
    *, s3: JsonObjectStore, source_name: str, manifest_key: str
) -> RawManifest:
    manifest = s3.get_json(key=manifest_key)
    if manifest is None:
        raise FileNotFoundError(f"Raw manifest not found: {manifest_key}")
    if not isinstance(manifest, dict):
        raise TypeError(f"Raw manifest must be an object: {manifest_key}")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError(f"Raw manifest files must be a list: {manifest_key}")
    if not files:
        raise ValueError(f"Raw manifest has no files: {manifest_key}")
    for index, file_entry in enumerate(files):
        if not isinstance(file_entry, dict):
            raise ValueError(f"Raw manifest file entry must be an object: {manifest_key}#{index}")

    try:
        manifest_model = RawManifestModel.model_validate(manifest)
    except ValidationError as exc:
        raise ValueError(f"Raw manifest is invalid: {manifest_key}: {exc}") from exc

    actual_source = manifest_model.source
    if actual_source != source_name:
        raise ValueError(
            f"Raw manifest source mismatch for {manifest_key}: "
            f"expected {source_name}, got {actual_source!r}"
        )
    normalized = manifest_model.model_dump(mode="json", exclude_unset=True)
    return {**manifest, **normalized, "manifest_s3_key": manifest_key}


def validate_manifest_row_count(
    *,
    file_name: str,
    file_entry: RawManifestFile,
    actual_row_count: int,
    source_label: str,
) -> None:
    expected = file_entry.get("row_count")
    if expected is None:
        return
    expected_count = int(expected)
    if expected_count != actual_row_count:
        raise ValueError(
            f"{source_label} raw file row_count mismatch for {file_name}: "
            f"manifest={expected_count} actual={actual_row_count}"
        )
