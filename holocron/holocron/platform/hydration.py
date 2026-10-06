from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse

from holocron.contracts import BytesObjectStore, PublicUrlStore, TextObjectStore
from holocron.platform.raw_files import string_value


class PlannedHydrationAsset(Protocol):
    status: str | None
    target_key: str


PlannedHydrationAssetT = TypeVar("PlannedHydrationAssetT", bound=PlannedHydrationAsset)
HydrationRow = dict[str, Any]


def partition_hydration_assets_by_existing(
    *,
    planned_assets: Sequence[PlannedHydrationAssetT],
    object_exists: Callable[[str], bool],
    overwrite_existing: bool,
    max_assets_per_run: int,
) -> tuple[list[PlannedHydrationAssetT], list[PlannedHydrationAssetT]]:
    selected_assets: list[PlannedHydrationAssetT] = []
    skipped_existing_assets: list[PlannedHydrationAssetT] = []
    for planned_asset in planned_assets:
        if (
            not overwrite_existing
            and planned_asset.status is None
            and planned_asset.target_key
            and object_exists(planned_asset.target_key)
        ):
            skipped_existing_assets.append(planned_asset)
            continue
        selected_assets.append(planned_asset)
        if len(selected_assets) >= max_assets_per_run:
            break
    return selected_assets, skipped_existing_assets


def select_manifest_keys(
    *,
    listed_keys: Iterable[str],
    explicit_keys: Sequence[str] = (),
    latest_count: int | None = None,
) -> tuple[str, ...]:
    keys = _clean_manifest_keys(explicit_keys) or _clean_manifest_keys(listed_keys)
    if latest_count is not None:
        keys = keys[-latest_count:]
    return tuple(keys)


def _clean_manifest_keys(keys: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(str(key).strip() for key in keys if str(key).strip()))


def hydrate_assets_in_order(
    *,
    planned_assets: Sequence[PlannedHydrationAssetT],
    worker_count: int,
    thread_name_prefix: str,
    hydrate_one: Callable[[int, PlannedHydrationAssetT], HydrationRow],
    failure_row: Callable[[int, PlannedHydrationAssetT, Exception], HydrationRow],
    on_progress: Callable[[int, HydrationRow, Counter[str], int], None] | None = None,
) -> list[HydrationRow]:
    if not planned_assets:
        return []

    total_assets = len(planned_assets)
    worker_count = max(1, min(worker_count, total_assets))
    status_counts: Counter[str] = Counter()
    downloaded_bytes = 0
    rows_by_index: dict[int, HydrationRow] = {}

    def record(completed: int, row: HydrationRow) -> None:
        nonlocal downloaded_bytes
        status_counts[str(row.get("status"))] += 1
        downloaded_bytes += inventory_row_downloaded_bytes(row)
        if on_progress is not None:
            on_progress(completed, row, status_counts, downloaded_bytes)

    if worker_count == 1:
        rows: list[HydrationRow] = []
        for index, planned_asset in enumerate(planned_assets, start=1):
            try:
                row = hydrate_one(index, planned_asset)
            except Exception as exc:  # noqa: BLE001
                row = failure_row(index, planned_asset, exc)
            rows.append(row)
            record(index, row)
        return rows

    assets_by_index = dict(enumerate(planned_assets, start=1))
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix=thread_name_prefix,
    ) as executor:
        future_to_index = {
            executor.submit(hydrate_one, index, planned_asset): index
            for index, planned_asset in assets_by_index.items()
        }
        for completed_count, future in enumerate(as_completed(future_to_index), start=1):
            index = future_to_index[future]
            planned_asset = assets_by_index[index]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = failure_row(index, planned_asset, exc)
            rows_by_index[index] = row
            record(completed_count, row)

    return [rows_by_index[index] for index in range(1, total_assets + 1)]


def skipped_existing_inventory_rows(
    *,
    planned_assets: Sequence[PlannedHydrationAssetT],
    build_row: Callable[[PlannedHydrationAssetT], HydrationRow],
) -> list[HydrationRow]:
    rows: list[HydrationRow] = []
    for planned_asset in planned_assets:
        row = build_row(planned_asset)
        row["status"] = "already_exists"
        rows.append(row)
    return rows


def manifest_file_entry(
    manifest: Mapping[str, Any],
    file_name: str,
    *,
    provider_label: str,
) -> dict[str, Any] | None:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError(f"{provider_label} raw manifest files must be a list")
    for item in files:
        if not isinstance(item, dict):
            raise ValueError(f"{provider_label} raw manifest files must contain objects")
        if Path(string_value(item.get("path"))).name == file_name:
            return item
    return None


def parse_jsonl_text(
    *,
    text: str,
    source_key: str,
    row_label: str,
    strict: bool = True,
) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            if strict:
                raise
            continue
        if not isinstance(payload, dict):
            raise ValueError(f"{row_label} must be an object: {source_key}:{line_number}")
        rows.append((line_number, payload))
    return rows


def read_manifest_jsonl_rows(
    *,
    s3: TextObjectStore,
    manifest: Mapping[str, Any],
    manifest_key: str,
    file_name: str,
    provider_label: str,
    row_label: str,
    strict: bool = True,
) -> tuple[str, list[tuple[int, dict[str, Any]]]]:
    file_entry = manifest_file_entry(manifest, file_name, provider_label=provider_label)
    if file_entry is None:
        return "", []
    source_key = string_value(file_entry.get("s3_key"))
    if not source_key:
        raise ValueError(
            f"{provider_label} file entry is missing s3_key: {manifest_key} {file_name}"
        )
    rows = parse_jsonl_text(
        text=s3.read_text(key=source_key),
        source_key=source_key,
        row_label=row_label,
        strict=strict,
    )
    expected_count = file_entry.get("row_count")
    if strict and expected_count is not None and int(expected_count) != len(rows):
        raise ValueError(
            f"{provider_label} row_count mismatch for {source_key}: "
            f"manifest={expected_count} actual={len(rows)}"
        )
    return source_key, rows


def inventory_key(
    *,
    prefix: str,
    run_id: str,
    file_name: str,
    sanitize_run_id: bool = True,
) -> str:
    run_segment = safe_path_segment(run_id) if sanitize_run_id else run_id
    return f"{prefix.rstrip('/')}/run_id={run_segment}/{file_name}"


def write_jsonl_inventory_manifest(
    *,
    s3: BytesObjectStore,
    prefix: str,
    run_id: str,
    file_name: str,
    rows: Iterable[Mapping[str, Any]],
    sanitize_run_id: bool = True,
    default: Callable[[Any], Any] | None = None,
) -> str:
    key = inventory_key(
        prefix=prefix,
        run_id=run_id,
        file_name=file_name,
        sanitize_run_id=sanitize_run_id,
    )
    s3.put_bytes(
        key=key,
        payload=jsonl_bytes(rows, default=default),
        content_type="application/x-ndjson",
    )
    return key


def finalize_hydration_inventory(
    *,
    s3: BytesObjectStore,
    run_id: str,
    created_at: str,
    manifest_prefix: str,
    target_prefix: str,
    inventory_prefix: str,
    inventory_file_name: str,
    source_manifest_count: int,
    source_row_count: int,
    planned_assets: Sequence[PlannedHydrationAssetT],
    skipped_existing_assets: Sequence[PlannedHydrationAssetT],
    hydrated_rows: Sequence[HydrationRow],
    skipped_existing_row_builder: Callable[[PlannedHydrationAssetT], HydrationRow],
    sanitize_run_id: bool = True,
    default: Callable[[Any], Any] | None = None,
    extra_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    skipped_existing_rows = skipped_existing_inventory_rows(
        planned_assets=skipped_existing_assets,
        build_row=skipped_existing_row_builder,
    )
    inventory_rows = [*skipped_existing_rows, *hydrated_rows]
    inventory_manifest_key = write_jsonl_inventory_manifest(
        s3=s3,
        prefix=inventory_prefix,
        run_id=run_id,
        file_name=inventory_file_name,
        rows=inventory_rows,
        sanitize_run_id=sanitize_run_id,
        default=default,
    )
    summary = hydration_inventory_summary(inventory_rows)
    return {
        "run_id": run_id,
        "created_at": created_at,
        "manifest_prefix": manifest_prefix,
        "target_prefix": target_prefix,
        "inventory_prefix": inventory_prefix,
        "inventory_manifest_key": inventory_manifest_key,
        "source_manifest_count": source_manifest_count,
        "source_row_count": source_row_count,
        "discovered": len(planned_assets),
        "skipped_existing": len(skipped_existing_assets),
        "attempted": len(hydrated_rows),
        "inventory_row_count": len(inventory_rows),
        **summary,
        **dict(extra_result or {}),
    }


def jsonl_bytes(
    rows: Iterable[Mapping[str, Any]], *, default: Callable[[Any], Any] | None = None
) -> bytes:
    row_list = list(rows)
    if not row_list:
        return b""
    return (
        "\n".join(
            json.dumps(row, ensure_ascii=False, default=default, separators=(",", ":"))
            for row in row_list
        )
        + "\n"
    ).encode("utf-8")


def name_from_url_or_path(value: str) -> str:
    parsed = urlparse(value)
    candidate = Path(parsed.path).name
    return candidate or hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def safe_path_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._=-]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned or "unknown"


def public_url_for_key(*, s3: PublicUrlStore, key: str) -> str:
    public_url = s3.public_url(key=key)
    return string_value(public_url)


def inventory_row_downloaded_bytes(inventory_row: Mapping[str, Any]) -> int:
    if inventory_row.get("status") != "downloaded":
        return 0
    return int(inventory_row.get("size_bytes") or 0)


def hydration_inventory_summary(inventory_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    total_bytes = 0
    for row in inventory_rows:
        status_counts[str(row.get("status"))] += 1
        total_bytes += inventory_row_downloaded_bytes(row)
    return {
        "downloaded": status_counts["downloaded"],
        "already_exists": status_counts["already_exists"],
        "errors": sum(
            status_counts[status]
            for status in ("download_error", "validation_error", "too_large", "missing_url")
        ),
        "total_bytes": total_bytes,
        "status_counts": dict(status_counts),
    }


def format_bytes(size_bytes: float | int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"
