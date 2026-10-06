"""Property Finder listing media hydration from raw listing manifests."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import Field, model_validator

from holocron.platform.execution import new_run_id, utc_now
from holocron.platform.hydration import (
    finalize_hydration_inventory,
    hydrate_assets_in_order,
    name_from_url_or_path,
    partition_hydration_assets_by_existing,
    public_url_for_key,
    read_manifest_jsonl_rows,
    safe_path_segment,
    select_manifest_keys,
    string_value,
)
from holocron.platform.http_download import normalize_external_url, validated_stream_get
from holocron.pydantic_helpers import CsvTuple, HolocronModel, NonBlankStr

logger = logging.getLogger(__name__)

PF_LISTING_PROPERTIES_FILE_NAME = "pf_listing_properties.jsonl"
PF_LISTING_DETAILS_FILE_NAME = "pf_listing_details.jsonl"
PF_LISTING_MEDIA_INVENTORY_FILE_NAME = "pf_listing_media_assets.jsonl"
PF_DEFAULT_ALLOWED_MEDIA_HOSTS = (
    "static.shared.propertyfinder.ae",
    "www.propertyfinder.ae",
    "new-projects-media.propertyfinder.com",
    "graph-images.propertyfinder.ae",
    "static-assets.propertyfinder.com",
)
_IMAGE_URL_KEYS = (
    "full",
    "original",
    "large",
    "medium",
    "url",
    "src",
    "small",
    "thumbnail",
)
_MEDIA_LOG_INTERVAL = 500


class PropertyFinderListingMediaHydrationConfig(HolocronModel):
    manifest_prefix: NonBlankStr = "raw/source=pf_listings/manifests/"
    manifest_keys: CsvTuple = ()
    latest_manifest_count: int | None = Field(default=None, ge=1)
    target_prefix: NonBlankStr = "media/pf_listings/listing_media"
    inventory_prefix: NonBlankStr = "raw/source=pf_listings/listing_media_asset_manifests"
    inventory_file_name: NonBlankStr = PF_LISTING_MEDIA_INVENTORY_FILE_NAME
    max_assets_per_run: int = Field(default=100000, ge=1)
    overwrite_existing: bool = False
    allowed_media_hosts: CsvTuple = PF_DEFAULT_ALLOWED_MEDIA_HOSTS
    max_media_mb: int = Field(default=25, ge=1)
    request_pause_seconds: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=60, ge=1)
    max_concurrent_downloads: int = Field(default=8, ge=1, le=32)
    include_search_listing_media: bool = True
    include_detail_media: bool = True
    asset_type_allowlist: CsvTuple = ()

    @model_validator(mode="after")
    def validate_config(self) -> "PropertyFinderListingMediaHydrationConfig":
        if not self.allowed_media_hosts:
            raise ValueError("allowed_media_hosts must include at least one host")
        if not self.include_search_listing_media and not self.include_detail_media:
            raise ValueError(
                "at least one of include_search_listing_media or include_detail_media must be true"
            )
        return self


@dataclass(frozen=True, slots=True)
class MediaDownload:
    content: bytes
    content_type: str | None
    final_url: str


class MediaTooLargeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ManifestListingRow:
    source_manifest_key: str
    source_listing_key: str
    source_file_name: str
    source_manifest_run_id: str
    line_number: int
    row: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DiscoveredMediaAsset:
    source_row: ManifestListingRow
    listing_identity: str
    listing_id: str
    property_key: str
    name: str
    source_url: str
    asset_type: str
    field_path: str
    raw: Any


@dataclass(frozen=True, slots=True)
class PlannedMediaAsset:
    source_row: ManifestListingRow
    listing_identity: str
    listing_id: str
    property_key: str
    name: str
    source_url: str
    normalized_url: str
    target_key: str
    asset_type: str
    field_path: str
    raw: Any = None
    status: str | None = None
    error: str | None = None


class MediaDownloader(Protocol):
    def download_media(self, url: str, *, max_bytes: int) -> MediaDownload: ...


class PropertyFinderMediaDownloadClient:
    def __init__(self, *, client: httpx.Client, allowed_media_hosts: Sequence[str]) -> None:
        self._client = client
        self._allowed_media_hosts = tuple(allowed_media_hosts)

    def download_media(self, url: str, *, max_bytes: int) -> MediaDownload:
        with validated_stream_get(
            self._client,
            url,
            validate_url=lambda candidate: _validate_media_url(
                candidate,
                allowed_hosts=self._allowed_media_hosts,
            ),
            headers=_headers(),
        ) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise MediaTooLargeError(f"media exceeds max size of {max_bytes} bytes")
            return MediaDownload(
                content=bytes(content),
                content_type=response.headers.get("content-type"),
                final_url=str(response.url),
            )


def hydrate_pf_listing_media_assets(
    *,
    s3: Any,
    config: PropertyFinderListingMediaHydrationConfig | Mapping[str, Any] | None = None,
    now: datetime | None = None,
    download_client: MediaDownloader | None = None,
    progress_log: Any | None = None,
) -> dict[str, Any]:
    parsed_config = (
        config
        if isinstance(config, PropertyFinderListingMediaHydrationConfig)
        else PropertyFinderListingMediaHydrationConfig.model_validate(config or {})
    )
    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    log = progress_log or logger

    source_rows = _load_manifest_listing_rows(s3=s3, config=parsed_config)
    planned_assets = _plan_media_assets(source_rows, config=parsed_config)
    selected_assets, skipped_existing_assets = partition_hydration_assets_by_existing(
        planned_assets=planned_assets,
        object_exists=lambda key: s3.object_exists(key=key),
        overwrite_existing=parsed_config.overwrite_existing,
        max_assets_per_run=parsed_config.max_assets_per_run,
    )
    skipped_existing = len(skipped_existing_assets)
    _log_info(
        log,
        (
            "pf_listings: hydrating media assets manifests=%s source_rows=%s "
            "discovered=%s selected=%s skipped_existing=%s max_concurrent_downloads=%s"
        ),
        len({row.source_manifest_key for row in source_rows}),
        len(source_rows),
        len(planned_assets),
        len(selected_assets),
        skipped_existing,
        parsed_config.max_concurrent_downloads,
    )

    with contextlib.ExitStack() as stack:
        if download_client is None:
            client = stack.enter_context(httpx.Client(timeout=parsed_config.timeout_seconds))
            download_client = PropertyFinderMediaDownloadClient(
                client=client,
                allowed_media_hosts=parsed_config.allowed_media_hosts,
            )
        hydrated_rows = _hydrate_planned_assets(
            s3=s3,
            planned_assets=selected_assets,
            config=parsed_config,
            download_client=download_client,
            run_id=run_id,
            created_at=current_time.isoformat(),
            progress_log=log,
        )
    result = finalize_hydration_inventory(
        s3=s3,
        run_id=run_id,
        created_at=current_time.isoformat(),
        manifest_prefix=parsed_config.manifest_prefix,
        target_prefix=parsed_config.target_prefix,
        inventory_prefix=parsed_config.inventory_prefix,
        inventory_file_name=parsed_config.inventory_file_name,
        source_manifest_count=len({row.source_manifest_key for row in source_rows}),
        source_row_count=len(source_rows),
        planned_assets=planned_assets,
        skipped_existing_assets=skipped_existing_assets,
        hydrated_rows=hydrated_rows,
        skipped_existing_row_builder=partial(
            _base_inventory_row,
            run_id=run_id,
            created_at=current_time.isoformat(),
            s3=s3,
        ),
        extra_result={"max_concurrent_downloads": parsed_config.max_concurrent_downloads},
    )
    _log_info(
        log,
        (
            "pf_listings: completed media hydration run_id=%s attempted=%s downloaded=%s "
            "already_exists=%s errors=%s bytes=%s inventory_key=%s"
        ),
        run_id,
        result["attempted"],
        result["downloaded"],
        result["already_exists"],
        result["errors"],
        result["total_bytes"],
        result["inventory_manifest_key"],
    )
    return result


def _load_manifest_listing_rows(
    *,
    s3: Any,
    config: PropertyFinderListingMediaHydrationConfig,
) -> list[ManifestListingRow]:
    rows: list[ManifestListingRow] = []
    manifest_keys = select_manifest_keys(
        listed_keys=s3.list_keys(prefix=config.manifest_prefix),
        explicit_keys=config.manifest_keys,
        latest_count=config.latest_manifest_count,
    )
    for manifest_key in manifest_keys:
        manifest = json.loads(s3.read_text(key=manifest_key))
        if not isinstance(manifest, dict):
            raise ValueError(f"Property Finder raw manifest must be an object: {manifest_key}")
        run_id = string_value(manifest.get("run_id"))
        if config.include_detail_media:
            rows.extend(
                _load_manifest_jsonl_rows(
                    s3=s3,
                    manifest=manifest,
                    manifest_key=manifest_key,
                    run_id=run_id,
                    file_name=PF_LISTING_DETAILS_FILE_NAME,
                    strict=True,
                )
            )
        if config.include_search_listing_media:
            rows.extend(
                _load_manifest_jsonl_rows(
                    s3=s3,
                    manifest=manifest,
                    manifest_key=manifest_key,
                    run_id=run_id,
                    file_name=PF_LISTING_PROPERTIES_FILE_NAME,
                    strict=True,
                )
            )
    return rows


def _load_manifest_jsonl_rows(
    *,
    s3: Any,
    manifest: Mapping[str, Any],
    manifest_key: str,
    run_id: str,
    file_name: str,
    strict: bool,
) -> list[ManifestListingRow]:
    source_listing_key, parsed_rows = read_manifest_jsonl_rows(
        s3=s3,
        manifest=manifest,
        manifest_key=manifest_key,
        file_name=file_name,
        provider_label="Property Finder",
        row_label="Property Finder listing media row",
        strict=strict,
    )
    if not source_listing_key:
        return []
    return [
        ManifestListingRow(
            source_manifest_key=manifest_key,
            source_listing_key=source_listing_key,
            source_file_name=file_name,
            source_manifest_run_id=run_id,
            line_number=line_number,
            row=row,
        )
        for line_number, row in parsed_rows
    ]


def _plan_media_assets(
    source_rows: Sequence[ManifestListingRow],
    *,
    config: PropertyFinderListingMediaHydrationConfig,
) -> list[PlannedMediaAsset]:
    planned_assets: list[PlannedMediaAsset] = []
    seen: set[tuple[str, str]] = set()
    asset_type_allowlist = set(config.asset_type_allowlist)
    for source_row in source_rows:
        for discovered in _discover_media_assets(source_row):
            if asset_type_allowlist and discovered.asset_type not in asset_type_allowlist:
                continue
            try:
                normalized_url = _validate_media_url(
                    discovered.source_url,
                    allowed_hosts=config.allowed_media_hosts,
                )
            except ValueError as exc:
                planned_assets.append(
                    PlannedMediaAsset(
                        source_row=source_row,
                        listing_identity=discovered.listing_identity,
                        listing_id=discovered.listing_id,
                        property_key=discovered.property_key,
                        name=discovered.name,
                        source_url=discovered.source_url,
                        normalized_url="",
                        target_key="",
                        asset_type=discovered.asset_type,
                        field_path=discovered.field_path,
                        raw=discovered.raw,
                        status="validation_error",
                        error=str(exc),
                    )
                )
                continue

            dedupe_key = (discovered.listing_identity, normalized_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            planned_assets.append(
                PlannedMediaAsset(
                    source_row=source_row,
                    listing_identity=discovered.listing_identity,
                    listing_id=discovered.listing_id,
                    property_key=discovered.property_key,
                    name=discovered.name,
                    source_url=discovered.source_url,
                    normalized_url=normalized_url,
                    target_key=_target_key(
                        target_prefix=config.target_prefix,
                        listing_identity=discovered.listing_identity,
                        normalized_url=normalized_url,
                        name=discovered.name,
                        asset_type=discovered.asset_type,
                        field_path=discovered.field_path,
                    ),
                    asset_type=discovered.asset_type,
                    field_path=discovered.field_path,
                    raw=discovered.raw,
                )
            )
    return planned_assets


def _discover_media_assets(source_row: ManifestListingRow) -> list[DiscoveredMediaAsset]:
    row = source_row.row
    property_payload = _property_payload_for_media(row)
    listing_id = _first_string(row, property_payload, keys=("listing_id", "id"))
    property_key = _first_string(row, property_payload, keys=("property_key", "property_id"))
    listing_identity = listing_id or property_key
    if not listing_identity:
        listing_identity = hashlib.sha256(
            json.dumps(row, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]

    discovered: list[DiscoveredMediaAsset] = []
    for field_name, asset_type in (
        ("images", "listing_image"),
        ("floor_plans", "floorplan"),
        ("floorplans", "floorplan"),
        ("floorplan", "floorplan"),
    ):
        if field_name in property_payload:
            discovered.extend(
                _discover_media_from_value(
                    source_row=source_row,
                    listing_identity=listing_identity,
                    listing_id=listing_id,
                    property_key=property_key,
                    value=property_payload[field_name],
                    asset_type=asset_type,
                    field_path=field_name,
                )
            )
    for field_name, asset_type in (
        ("agent", "agent_image"),
        ("broker", "broker_logo"),
        ("client", "client_logo"),
    ):
        value = property_payload.get(field_name)
        if isinstance(value, dict):
            discovered.extend(
                _discover_media_from_value(
                    source_row=source_row,
                    listing_identity=listing_identity,
                    listing_id=listing_id,
                    property_key=property_key,
                    value=value,
                    asset_type=asset_type,
                    field_path=field_name,
                    targeted=True,
                )
            )
    return discovered


def _discover_media_from_value(
    *,
    source_row: ManifestListingRow,
    listing_identity: str,
    listing_id: str,
    property_key: str,
    value: Any,
    asset_type: str,
    field_path: str,
    targeted: bool = False,
) -> list[DiscoveredMediaAsset]:
    assets: list[DiscoveredMediaAsset] = []
    if isinstance(value, str):
        if _looks_like_media_url(value):
            assets.append(
                _discovered_asset(
                    source_row=source_row,
                    listing_identity=listing_identity,
                    listing_id=listing_id,
                    property_key=property_key,
                    asset_type=asset_type,
                    field_path=field_path,
                    url=value,
                    raw=value,
                )
            )
        return assets
    if isinstance(value, list):
        for index, item in enumerate(value):
            assets.extend(
                _discover_media_from_value(
                    source_row=source_row,
                    listing_identity=listing_identity,
                    listing_id=listing_id,
                    property_key=property_key,
                    value=item,
                    asset_type=asset_type,
                    field_path=f"{field_path}.{index}",
                    targeted=targeted,
                )
            )
        return assets
    if not isinstance(value, dict):
        return assets

    grouped_assets = {
        "property": "listing_image",
        "listing": "listing_image",
        "community": "community_image",
        "tower": "tower_image",
        "building": "tower_image",
    }
    direct_url = _best_media_url(value)
    if direct_url:
        assets.append(
            _discovered_asset(
                source_row=source_row,
                listing_identity=listing_identity,
                listing_id=listing_id,
                property_key=property_key,
                asset_type=asset_type,
                field_path=field_path,
                url=direct_url,
                raw=value,
            )
        )
        return assets

    keys = value.keys()
    allowed_targeted_keys = {
        "image",
        "image_url",
        "photo",
        "photo_url",
        "avatar",
        "logo",
        "logo_url",
        "picture",
        "profile_picture",
    }
    for key in keys:
        if targeted and key not in allowed_targeted_keys:
            continue
        child_asset_type = grouped_assets.get(key, asset_type)
        assets.extend(
            _discover_media_from_value(
                source_row=source_row,
                listing_identity=listing_identity,
                listing_id=listing_id,
                property_key=property_key,
                value=value[key],
                asset_type=child_asset_type,
                field_path=f"{field_path}.{key}",
                targeted=targeted,
            )
        )
    return assets


def _discovered_asset(
    *,
    source_row: ManifestListingRow,
    listing_identity: str,
    listing_id: str,
    property_key: str,
    asset_type: str,
    field_path: str,
    url: str,
    raw: Any,
) -> DiscoveredMediaAsset:
    return DiscoveredMediaAsset(
        source_row=source_row,
        listing_identity=listing_identity,
        listing_id=listing_id,
        property_key=property_key,
        name=name_from_url_or_path(url) or field_path,
        source_url=url,
        asset_type=asset_type,
        field_path=field_path,
        raw=raw,
    )


def _hydrate_planned_assets(
    *,
    s3: Any,
    planned_assets: Sequence[PlannedMediaAsset],
    config: PropertyFinderListingMediaHydrationConfig,
    download_client: MediaDownloader,
    run_id: str,
    created_at: str,
    progress_log: Any,
) -> list[dict[str, Any]]:
    if not planned_assets:
        return []
    max_bytes = config.max_media_mb * 1024 * 1024
    worker_count = min(config.max_concurrent_downloads, len(planned_assets))
    _log_info(
        progress_log,
        "pf_listings: media hydration starting assets=%s workers=%s overwrite_existing=%s",
        len(planned_assets),
        worker_count,
        config.overwrite_existing,
    )

    def hydrate_one(index: int, planned_asset: PlannedMediaAsset) -> dict[str, Any]:
        return _hydrate_single_planned_asset(
            s3=s3,
            planned_asset=planned_asset,
            config=config,
            download_client=download_client,
            max_bytes=max_bytes,
            run_id=run_id,
            created_at=created_at,
            progress_log=progress_log,
            index=index,
            total=len(planned_assets),
        )

    def failure_row(
        index: int,
        planned_asset: PlannedMediaAsset,
        exc: Exception,
    ) -> dict[str, Any]:
        row = _base_inventory_row(
            planned_asset=planned_asset,
            run_id=run_id,
            created_at=created_at,
            s3=s3,
        )
        row.update({"status": "download_error", "error": str(exc)})
        return row

    return hydrate_assets_in_order(
        planned_assets=planned_assets,
        worker_count=worker_count,
        thread_name_prefix="pf-listing-media",
        hydrate_one=hydrate_one,
        failure_row=failure_row,
        on_progress=lambda completed, _row, status_counts, _downloaded_bytes: _log_media_progress(
            progress_log,
            completed=completed,
            total=len(planned_assets),
            status_counts=status_counts,
        ),
    )


def _log_media_progress(
    progress_log: Any,
    *,
    completed: int,
    total: int,
    status_counts: Counter[str],
) -> None:
    if completed <= 5 or completed % _MEDIA_LOG_INTERVAL == 0 or completed == total:
        _log_info(
            progress_log,
            "pf_listings: media hydration progress completed=%s/%s status_counts=%s",
            completed,
            total,
            dict(status_counts),
        )


def _hydrate_single_planned_asset(
    *,
    s3: Any,
    planned_asset: PlannedMediaAsset,
    config: PropertyFinderListingMediaHydrationConfig,
    download_client: MediaDownloader,
    max_bytes: int,
    run_id: str,
    created_at: str,
    progress_log: Any,
    index: int,
    total: int,
) -> dict[str, Any]:
    inventory_row = _base_inventory_row(
        planned_asset=planned_asset,
        run_id=run_id,
        created_at=created_at,
        s3=s3,
    )
    if planned_asset.status is not None:
        inventory_row.update({"status": planned_asset.status, "error": planned_asset.error})
        return inventory_row

    attempted_download = False
    try:
        if not config.overwrite_existing and s3.object_exists(key=planned_asset.target_key):
            inventory_row["status"] = "already_exists"
            return inventory_row

        attempted_download = True
        download = download_client.download_media(planned_asset.normalized_url, max_bytes=max_bytes)
        final_url = _validate_media_url(
            download.final_url, allowed_hosts=config.allowed_media_hosts
        )
        if len(download.content) > max_bytes:
            raise MediaTooLargeError(f"media exceeds max size of {max_bytes} bytes")
        sha256 = hashlib.sha256(download.content).hexdigest()
        s3.put_bytes(
            key=planned_asset.target_key,
            payload=download.content,
            content_type=download.content_type,
        )
        inventory_row.update(
            {
                "status": "downloaded",
                "sha256": sha256,
                "size_bytes": len(download.content),
                "content_type": download.content_type,
                "final_url": final_url,
            }
        )
        if index <= 5 or index % _MEDIA_LOG_INTERVAL == 0 or index == total:
            _log_info(
                progress_log,
                "pf_listings: hydrated media asset %s/%s listing=%s key=%s size=%s",
                index,
                total,
                planned_asset.listing_identity,
                planned_asset.target_key,
                len(download.content),
            )
    except ValueError as exc:
        inventory_row.update({"status": "validation_error", "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        status = "too_large" if isinstance(exc, MediaTooLargeError) else "download_error"
        inventory_row.update({"status": status, "error": str(exc)})
    finally:
        if attempted_download and config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)
    return inventory_row


def _base_inventory_row(
    planned_asset: PlannedMediaAsset,
    *,
    run_id: str,
    created_at: str,
    s3: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "run_id": run_id,
        "created_at": created_at,
        "source_manifest": planned_asset.source_row.source_manifest_key,
        "source_manifest_run_id": planned_asset.source_row.source_manifest_run_id,
        "source_listing_key": planned_asset.source_row.source_listing_key,
        "source_file_name": planned_asset.source_row.source_file_name,
        "source_listing_line": planned_asset.source_row.line_number,
        "source_listing_row": planned_asset.source_row.row,
        "listing_identity": planned_asset.listing_identity,
        "asset_type": planned_asset.asset_type,
        "field_path": planned_asset.field_path,
        "source_url": planned_asset.source_url,
    }
    if planned_asset.listing_id:
        row["listing_id"] = planned_asset.listing_id
    if planned_asset.property_key:
        row["property_key"] = planned_asset.property_key
    if planned_asset.name:
        row["name"] = planned_asset.name
    if planned_asset.normalized_url:
        row["normalized_url"] = planned_asset.normalized_url
    if planned_asset.target_key:
        row["target_key"] = planned_asset.target_key
        public_url = public_url_for_key(s3=s3, key=planned_asset.target_key)
        if public_url:
            row["public_url"] = public_url
    return row


def _property_payload_for_media(row: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("detail_property", "raw_property"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    raw = row.get("raw")
    if isinstance(raw, dict):
        property_value = raw.get("property")
        if isinstance(property_value, dict):
            return property_value
        property_result = raw.get("propertyResult")
        if isinstance(property_result, dict) and isinstance(property_result.get("property"), dict):
            return property_result["property"]
        return raw
    return dict(row)


def _best_media_url(value: Mapping[str, Any]) -> str:
    for key in _IMAGE_URL_KEYS:
        url = value.get(key)
        if isinstance(url, str) and _looks_like_media_url(url):
            return url
    return ""


def _looks_like_media_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def _validate_media_url(url: str, *, allowed_hosts: Sequence[str]) -> str:
    return normalize_external_url(
        url,
        allowed_hosts=tuple(allowed_hosts),
        label="media URL",
    )


def _target_key(
    *,
    target_prefix: str,
    listing_identity: str,
    normalized_url: str,
    name: str,
    asset_type: str,
    field_path: str,
) -> str:
    listing_segment = safe_path_segment(listing_identity)
    asset_segment = safe_path_segment(asset_type or "media")
    field_segment = safe_path_segment(field_path or "unknown")
    url_sha256 = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    file_name = _safe_target_file_name(name=name, normalized_url=normalized_url)
    return (
        f"{target_prefix.rstrip('/')}/listing_id={listing_segment}/"
        f"asset_type={asset_segment}/field_path={field_segment}/{url_sha256}/{file_name}"
    )


def _first_string(*containers: Mapping[str, Any], keys: Sequence[str]) -> str:
    for container in containers:
        for key in keys:
            value = container.get(key)
            if value is not None:
                return string_value(value)
    return ""


def _safe_target_file_name(*, name: str, normalized_url: str) -> str:
    parsed_suffix = Path(urlparse(normalized_url).path).suffix
    suffix = parsed_suffix if parsed_suffix and len(parsed_suffix) <= 12 else ".bin"
    stem = Path(name).stem or "media"
    safe_stem = safe_path_segment(stem) or "media"
    if len(safe_stem) > 120:
        safe_stem = safe_stem[:120]
    return f"{safe_stem}{suffix}"


def _headers() -> dict[str, str]:
    return {
        "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        ),
    }


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.info(message, *args)
