"""News feed thumbnail hydration and platform publishing from raw manifests."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import mimetypes
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import Field

from holocron.platform.execution import new_run_id, utc_now
from holocron.platform.hydration import (
    finalize_hydration_inventory,
    format_bytes,
    hydrate_assets_in_order,
    name_from_url_or_path,
    partition_hydration_assets_by_existing,
    public_url_for_key,
    read_manifest_jsonl_rows,
    parse_jsonl_text,
    safe_path_segment,
    select_manifest_keys,
    string_value,
)
from holocron.platform.http_download import normalize_external_url, validated_stream_get
from holocron.platform.settings import Settings
from holocron.pydantic_helpers import CsvTuple, HolocronModel, NonBlankStr
from holocron.sources.news_feeds.extract import (
    ARTICLES_FILE_NAME,
    clean_text,
    extract_thumbnail_url_from_html,
    extract_thumbnail_url_from_raw_entry_xml,
)

logger = logging.getLogger(__name__)

NEWS_THUMBNAIL_INVENTORY_FILE_NAME = "news_thumbnail_assets.jsonl"
_THUMBNAIL_LOG_INTERVAL = 25
_PUBLIC_NEWS_URL_SCHEMES = {"http", "https"}
_STATUS_DOWNLOADED = "downloaded"
_STATUS_ALREADY_EXISTS = "already_exists"
_STATUS_MISSING_URL = "missing_url"
_STATUS_TOO_LARGE = "too_large"
_STATUS_DOWNLOAD_ERROR = "download_error"
_STATUS_VALIDATION_ERROR = "validation_error"


class NewsThumbnailHydrationConfig(HolocronModel):
    manifest_prefix: NonBlankStr = "raw/source=news_feeds/manifests/"
    manifest_keys: CsvTuple = ()
    latest_manifest_count: int | None = Field(default=None, ge=1)
    target_prefix: NonBlankStr = "media/news/thumbnails"
    inventory_prefix: NonBlankStr = "raw/source=news_feeds/thumbnail_asset_manifests"
    inventory_file_name: NonBlankStr = NEWS_THUMBNAIL_INVENTORY_FILE_NAME
    lookback_days: int = Field(default=3, ge=0)
    max_assets_per_run: int = Field(default=1000, ge=1)
    overwrite_existing: bool = False
    allowed_thumbnail_hosts: CsvTuple = ()
    max_thumbnail_mb: int = Field(default=5, ge=1)
    request_pause_seconds: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=30, ge=1)
    max_concurrent_downloads: int = Field(default=8, ge=1, le=32)
    resolve_missing_from_article_pages: bool = False


class NewsPublishConfig(HolocronModel):
    manifest_prefix: NonBlankStr = "raw/source=news_feeds/manifests/"
    thumbnail_inventory_prefix: NonBlankStr = "raw/source=news_feeds/thumbnail_asset_manifests"
    lookback_days: int = Field(default=3, ge=0)
    max_articles_per_run: int = Field(default=1000, ge=1)
    platform_postgres_url: str = ""
    ensure_schema: bool = False
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class ManifestArticleRow:
    source_manifest_key: str
    source_article_key: str
    source_file_name: str
    source_manifest_run_id: str
    line_number: int
    row: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ThumbnailDownload:
    content: bytes
    content_type: str | None
    final_url: str


class ThumbnailTooLargeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlannedThumbnailAsset:
    source_row: ManifestArticleRow
    article_key: str
    source_url: str
    normalized_url: str
    target_key: str
    article_url: str = ""
    status: str | None = None
    error: str | None = None


class ThumbnailDownloader(Protocol):
    def download_thumbnail(self, url: str, *, max_bytes: int) -> ThumbnailDownload: ...

    def resolve_article_thumbnail_url(self, url: str) -> str | None: ...


class NewsArticleWriter(Protocol):
    def upsert_articles(
        self,
        articles: Sequence[Mapping[str, Any]],
        *,
        ensure_schema: bool,
        dry_run: bool,
    ) -> Mapping[str, Any]: ...


class NewsThumbnailDownloadClient:
    def __init__(self, *, client: httpx.Client, allowed_thumbnail_hosts: Sequence[str]) -> None:
        self._client = client
        self._allowed_thumbnail_hosts = tuple(allowed_thumbnail_hosts)

    def download_thumbnail(self, url: str, *, max_bytes: int) -> ThumbnailDownload:
        with validated_stream_get(
            self._client,
            url,
            validate_url=lambda candidate: _validate_thumbnail_url(
                candidate,
                allowed_hosts=self._allowed_thumbnail_hosts,
            ),
            headers=_thumbnail_headers(),
        ) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ThumbnailTooLargeError(f"thumbnail exceeds max size of {max_bytes} bytes")
            return ThumbnailDownload(
                content=bytes(content),
                content_type=response.headers.get("content-type"),
                final_url=str(response.url),
            )

    def resolve_article_thumbnail_url(self, url: str) -> str | None:
        with validated_stream_get(
            self._client,
            url,
            validate_url=_validate_public_url,
            headers=_article_headers(),
        ) as response:
            response.raise_for_status()
            response.read()
            return extract_thumbnail_url_from_html(response.text, base_url=str(response.url))


def hydrate_news_thumbnail_assets(
    *,
    s3: Any,
    config: NewsThumbnailHydrationConfig | Mapping[str, Any] | None = None,
    now: datetime | None = None,
    download_client: ThumbnailDownloader | None = None,
    progress_log: Any | None = None,
) -> dict[str, Any]:
    parsed_config = (
        config
        if isinstance(config, NewsThumbnailHydrationConfig)
        else NewsThumbnailHydrationConfig.model_validate(config or {})
    )
    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    log = progress_log or logger

    source_rows = _load_manifest_article_rows(
        s3=s3,
        manifest_prefix=parsed_config.manifest_prefix,
        manifest_keys=parsed_config.manifest_keys,
        latest_manifest_count=parsed_config.latest_manifest_count,
        lookback_days=parsed_config.lookback_days,
        now=current_time,
    )
    planned_assets = _plan_thumbnail_assets(source_rows, config=parsed_config)
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
            "news_feeds: hydrating thumbnails manifests=%s source_rows=%s discovered=%s "
            "selected=%s skipped_existing=%s lookback_days=%s workers=%s"
        ),
        len({row.source_manifest_key for row in source_rows}),
        len(source_rows),
        len(planned_assets),
        len(selected_assets),
        skipped_existing,
        parsed_config.lookback_days,
        parsed_config.max_concurrent_downloads,
    )

    with contextlib.ExitStack() as stack:
        if download_client is None:
            client = stack.enter_context(httpx.Client(timeout=parsed_config.timeout_seconds))
            download_client = NewsThumbnailDownloadClient(
                client=client,
                allowed_thumbnail_hosts=parsed_config.allowed_thumbnail_hosts,
            )
        hydrated_rows = _hydrate_planned_thumbnail_assets(
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
            _base_thumbnail_inventory_row,
            run_id=run_id,
            created_at=current_time.isoformat(),
            s3=s3,
        ),
        default=str,
        extra_result={"max_concurrent_downloads": parsed_config.max_concurrent_downloads},
    )
    _log_info(
        log,
        (
            "news_feeds: completed thumbnail hydration run_id=%s attempted=%s "
            "downloaded=%s already_exists=%s errors=%s bytes=%s inventory_key=%s"
        ),
        run_id,
        result["attempted"],
        result["downloaded"],
        result["already_exists"],
        result["errors"],
        format_bytes(result["total_bytes"]),
        result["inventory_manifest_key"],
    )
    return result


def publish_news_to_platform(
    *,
    s3: Any,
    config: NewsPublishConfig | Mapping[str, Any] | None = None,
    writer: NewsArticleWriter | None = None,
    now: datetime | None = None,
    progress_log: Any | None = None,
) -> dict[str, Any]:
    parsed_config = (
        config
        if isinstance(config, NewsPublishConfig)
        else NewsPublishConfig.model_validate(config or {})
    )
    current_time = now or utc_now()
    log = progress_log or logger
    source_rows = _load_manifest_article_rows(
        s3=s3,
        manifest_prefix=parsed_config.manifest_prefix,
        lookback_days=parsed_config.lookback_days,
        now=current_time,
    )
    deduped_rows = _dedupe_article_rows(source_rows)[: parsed_config.max_articles_per_run]
    thumbnail_map = _load_thumbnail_inventory_map(
        s3=s3,
        inventory_prefix=parsed_config.thumbnail_inventory_prefix,
    )
    articles = [
        _article_payload(
            source_row=source_row,
            thumbnail_map=thumbnail_map,
            updated_at=current_time,
        )
        for source_row in deduped_rows
    ]
    selected_articles = [article for article in articles if article["url"] and article["headline"]]
    skipped = len(articles) - len(selected_articles)
    _log_info(
        log,
        (
            "news_feeds: publishing articles manifests=%s source_rows=%s selected=%s "
            "skipped=%s lookback_days=%s dry_run=%s"
        ),
        len({row.source_manifest_key for row in source_rows}),
        len(source_rows),
        len(selected_articles),
        skipped,
        parsed_config.lookback_days,
        parsed_config.dry_run,
    )

    if writer is None:
        postgres_url = (
            parsed_config.platform_postgres_url.strip() or Settings().platform_postgres_url
        )
        writer = PlatformNewsArticleWriter(postgres_url)

    writer_result = dict(
        writer.upsert_articles(
            selected_articles,
            ensure_schema=parsed_config.ensure_schema,
            dry_run=parsed_config.dry_run,
        )
    )
    result = {
        "source_manifest_count": len({row.source_manifest_key for row in source_rows}),
        "source_row_count": len(source_rows),
        "selected": len(selected_articles),
        "skipped": skipped,
        "published": int(writer_result.get("published") or 0),
        "created": int(writer_result.get("created") or 0),
        "updated": int(writer_result.get("updated") or 0),
        "failed": int(writer_result.get("failed") or 0),
        "dry_run": bool(parsed_config.dry_run),
        "writer_result": writer_result,
    }
    _log_info(
        log,
        (
            "news_feeds: completed platform publish selected=%s published=%s "
            "created=%s updated=%s failed=%s dry_run=%s"
        ),
        result["selected"],
        result["published"],
        result["created"],
        result["updated"],
        result["failed"],
        result["dry_run"],
    )
    return result


class PlatformNewsArticleWriter:
    def __init__(self, postgres_url: str) -> None:
        self._postgres_url = postgres_url.strip()
        if not self._postgres_url:
            raise ValueError("PLATFORM_POSTGRES_URL is required for news publish")

    def upsert_articles(
        self,
        articles: Sequence[Mapping[str, Any]],
        *,
        ensure_schema: bool,
        dry_run: bool,
    ) -> Mapping[str, Any]:
        if dry_run:
            return {
                "published": len(articles),
                "created": 0,
                "updated": 0,
                "failed": 0,
                "dry_run": True,
            }

        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for platform news writes. Run `uv sync`."
            ) from exc

        created = 0
        updated = 0
        failed = 0
        with psycopg.connect(self._postgres_url) as connection:
            with connection.cursor() as cursor:
                if ensure_schema:
                    _ensure_news_articles_schema(cursor)
                for article in articles:
                    try:
                        cursor.execute(
                            """
                            UPDATE news_articles
                            SET
                                url = %s,
                                canonical_url = %s,
                                headline = %s,
                                summary = %s,
                                source_name = %s,
                                source_feed_url = %s,
                                thumbnail_url = %s,
                                thumbnail_base64 = %s,
                                publish_date = %s,
                                discovered_at = %s,
                                topic_tags = %s,
                                raw_manifest_key = %s,
                                raw_run_id = %s,
                                is_active = %s,
                                updated_at = %s
                            WHERE article_key = %s OR url = %s
                            """,
                            _article_update_params(article),
                        )
                        if cursor.rowcount:
                            updated += cursor.rowcount
                            continue
                        cursor.execute(
                            """
                            INSERT INTO news_articles (
                                article_key,
                                url,
                                canonical_url,
                                headline,
                                summary,
                                source_name,
                                source_feed_url,
                                thumbnail_url,
                                thumbnail_base64,
                                publish_date,
                                discovered_at,
                                topic_tags,
                                raw_manifest_key,
                                raw_run_id,
                                is_active,
                                updated_at
                            )
                            VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s
                            )
                            """,
                            _article_insert_params(article),
                        )
                        created += 1
                    except Exception:
                        failed += 1
                        logger.exception(
                            "news_feeds: failed to upsert article url=%s",
                            article.get("url"),
                        )
                connection.commit()
        return {
            "published": created + updated,
            "created": created,
            "updated": updated,
            "failed": failed,
            "dry_run": False,
        }


def _ensure_news_articles_schema(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS news_articles (
            id bigserial PRIMARY KEY,
            article_key text,
            url text NOT NULL,
            canonical_url text,
            headline text NOT NULL,
            summary text,
            source_name text,
            source_feed_url text,
            thumbnail_url text,
            thumbnail_base64 text,
            publish_date timestamptz,
            discovered_at timestamptz,
            topic_tags text[],
            raw_manifest_key text,
            raw_run_id text,
            is_active boolean NOT NULL DEFAULT true,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for statement in (
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS url text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS headline text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS thumbnail_url text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS thumbnail_base64 text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS publish_date timestamptz",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS article_key text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS canonical_url text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS summary text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS source_name text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS source_feed_url text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS discovered_at timestamptz",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS topic_tags text[]",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS raw_manifest_key text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS raw_run_id text",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true",
        "ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
        "ALTER TABLE news_articles ALTER COLUMN url TYPE text",
        "ALTER TABLE news_articles ALTER COLUMN headline TYPE text",
        "ALTER TABLE news_articles ALTER COLUMN thumbnail_url TYPE text",
        "CREATE INDEX IF NOT EXISTS news_articles_article_key_lookup_idx ON news_articles(article_key)",
        "CREATE INDEX IF NOT EXISTS news_articles_url_lookup_idx ON news_articles(url)",
        "CREATE INDEX IF NOT EXISTS news_articles_publish_date_idx ON news_articles(publish_date)",
    ):
        cursor.execute(statement)


def _load_manifest_article_rows(
    *,
    s3: Any,
    manifest_prefix: str,
    lookback_days: int,
    now: datetime,
    manifest_keys: Sequence[str] = (),
    latest_manifest_count: int | None = None,
) -> list[ManifestArticleRow]:
    should_apply_lookback = not manifest_keys and latest_manifest_count is None
    cutoff = (
        _lookback_cutoff(now=now, lookback_days=lookback_days) if should_apply_lookback else None
    )
    rows: list[ManifestArticleRow] = []
    selected_manifest_keys = select_manifest_keys(
        listed_keys=s3.list_keys(prefix=manifest_prefix),
        explicit_keys=manifest_keys,
        latest_count=latest_manifest_count,
    )
    for manifest_key in selected_manifest_keys:
        manifest = json.loads(s3.read_text(key=manifest_key))
        if not isinstance(manifest, dict):
            raise ValueError(f"News raw manifest must be an object: {manifest_key}")
        run_id = string_value(manifest.get("run_id"))
        source_article_key, parsed_rows = read_manifest_jsonl_rows(
            s3=s3,
            manifest=manifest,
            manifest_key=manifest_key,
            file_name=ARTICLES_FILE_NAME,
            provider_label="News",
            row_label="News row",
        )
        if not source_article_key:
            continue
        for line_number, row in parsed_rows:
            if cutoff is not None and not _row_within_lookback(row, cutoff=cutoff):
                continue
            rows.append(
                ManifestArticleRow(
                    source_manifest_key=manifest_key,
                    source_article_key=source_article_key,
                    source_file_name=ARTICLES_FILE_NAME,
                    source_manifest_run_id=run_id,
                    line_number=line_number,
                    row=row,
                )
            )
    return rows


def _plan_thumbnail_assets(
    source_rows: Sequence[ManifestArticleRow],
    *,
    config: NewsThumbnailHydrationConfig,
) -> list[PlannedThumbnailAsset]:
    planned_assets: list[PlannedThumbnailAsset] = []
    seen: set[str] = set()
    for source_row in source_rows:
        article_key = _article_key(source_row.row)
        source_url = _thumbnail_source_url(source_row.row)
        if not source_url:
            article_url = _article_url(source_row.row)
            if config.resolve_missing_from_article_pages and article_url:
                try:
                    normalized_article_url = _validate_public_url(article_url)
                except ValueError as exc:
                    planned_assets.append(
                        PlannedThumbnailAsset(
                            source_row=source_row,
                            article_key=article_key,
                            source_url="",
                            normalized_url="",
                            target_key="",
                            article_url=article_url,
                            status=_STATUS_VALIDATION_ERROR,
                            error=str(exc),
                        )
                    )
                    continue
                seen_key = f"article:{normalized_article_url}"
                if seen_key in seen:
                    continue
                seen.add(seen_key)
                planned_assets.append(
                    PlannedThumbnailAsset(
                        source_row=source_row,
                        article_key=article_key,
                        source_url="",
                        normalized_url="",
                        target_key="",
                        article_url=normalized_article_url,
                    )
                )
                continue
            planned_assets.append(
                PlannedThumbnailAsset(
                    source_row=source_row,
                    article_key=article_key,
                    source_url="",
                    normalized_url="",
                    target_key="",
                    status=_STATUS_MISSING_URL,
                    error="article row does not include thumbnail_source_url",
                )
            )
            continue
        try:
            normalized_url = _validate_thumbnail_url(
                source_url,
                allowed_hosts=config.allowed_thumbnail_hosts,
            )
        except ValueError as exc:
            planned_assets.append(
                PlannedThumbnailAsset(
                    source_row=source_row,
                    article_key=article_key,
                    source_url=source_url,
                    normalized_url="",
                    target_key="",
                    status=_STATUS_VALIDATION_ERROR,
                    error=str(exc),
                )
            )
            continue
        seen_key = f"thumbnail:{normalized_url}"
        if seen_key in seen:
            continue
        seen.add(seen_key)
        planned_assets.append(
            PlannedThumbnailAsset(
                source_row=source_row,
                article_key=article_key,
                source_url=source_url,
                normalized_url=normalized_url,
                target_key=_thumbnail_target_key(
                    target_prefix=config.target_prefix,
                    normalized_url=normalized_url,
                    name=name_from_url_or_path(normalized_url),
                ),
            )
        )
    return planned_assets


def _hydrate_planned_thumbnail_assets(
    *,
    s3: Any,
    planned_assets: Sequence[PlannedThumbnailAsset],
    config: NewsThumbnailHydrationConfig,
    download_client: ThumbnailDownloader,
    run_id: str,
    created_at: str,
    progress_log: Any,
) -> list[dict[str, Any]]:
    if not planned_assets:
        return []
    max_bytes = config.max_thumbnail_mb * 1024 * 1024
    worker_count = min(config.max_concurrent_downloads, len(planned_assets))
    if worker_count > 1:
        _log_info(
            progress_log,
            "news_feeds: thumbnail hydration starting assets=%s workers=%s overwrite_existing=%s",
            len(planned_assets),
            worker_count,
            config.overwrite_existing,
        )

    def hydrate_one(index: int, planned_asset: PlannedThumbnailAsset) -> dict[str, Any]:
        return _hydrate_single_thumbnail_asset(
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
        planned_asset: PlannedThumbnailAsset,
        exc: Exception,
    ) -> dict[str, Any]:
        row = _base_thumbnail_inventory_row(
            planned_asset=planned_asset,
            run_id=run_id,
            created_at=created_at,
            s3=s3,
        )
        row.update({"status": _STATUS_DOWNLOAD_ERROR, "error": str(exc)})
        return row

    return hydrate_assets_in_order(
        planned_assets=planned_assets,
        worker_count=worker_count,
        thread_name_prefix="news-thumbnails",
        hydrate_one=hydrate_one,
        failure_row=failure_row,
        on_progress=lambda completed, _row, status_counts, downloaded_bytes: (
            _log_thumbnail_progress(
                progress_log,
                completed=completed,
                total=len(planned_assets),
                status_counts=status_counts,
                downloaded_bytes=downloaded_bytes,
            )
        ),
    )


def _hydrate_single_thumbnail_asset(
    *,
    s3: Any,
    planned_asset: PlannedThumbnailAsset,
    config: NewsThumbnailHydrationConfig,
    download_client: ThumbnailDownloader,
    max_bytes: int,
    run_id: str,
    created_at: str,
    progress_log: Any,
    index: int,
    total: int,
) -> dict[str, Any]:
    effective_asset = planned_asset
    resolved_from_article_url = False
    if (
        planned_asset.status is None
        and not planned_asset.normalized_url
        and planned_asset.article_url
    ):
        try:
            resolved_url = _resolve_article_thumbnail_url(
                download_client=download_client,
                article_url=planned_asset.article_url,
            )
            if not resolved_url:
                inventory_row = _base_thumbnail_inventory_row(
                    planned_asset=planned_asset,
                    run_id=run_id,
                    created_at=created_at,
                    s3=s3,
                )
                inventory_row.update(
                    {
                        "status": _STATUS_MISSING_URL,
                        "error": "article page did not include a thumbnail URL",
                    }
                )
                return inventory_row
            normalized_url = _validate_thumbnail_url(
                resolved_url,
                allowed_hosts=config.allowed_thumbnail_hosts,
            )
            effective_asset = replace(
                planned_asset,
                source_url=resolved_url,
                normalized_url=normalized_url,
                target_key=_thumbnail_target_key(
                    target_prefix=config.target_prefix,
                    normalized_url=normalized_url,
                    name=name_from_url_or_path(normalized_url),
                ),
            )
            resolved_from_article_url = True
        except ValueError as exc:
            inventory_row = _base_thumbnail_inventory_row(
                planned_asset=planned_asset,
                run_id=run_id,
                created_at=created_at,
                s3=s3,
            )
            inventory_row.update({"status": _STATUS_VALIDATION_ERROR, "error": str(exc)})
            return inventory_row
        except Exception as exc:  # noqa: BLE001
            inventory_row = _base_thumbnail_inventory_row(
                planned_asset=planned_asset,
                run_id=run_id,
                created_at=created_at,
                s3=s3,
            )
            inventory_row.update({"status": _STATUS_DOWNLOAD_ERROR, "error": str(exc)})
            return inventory_row

    inventory_row = _base_thumbnail_inventory_row(
        planned_asset=effective_asset,
        run_id=run_id,
        created_at=created_at,
        s3=s3,
    )
    if resolved_from_article_url:
        inventory_row["resolved_from_article_url"] = planned_asset.article_url
    if effective_asset.status is not None:
        inventory_row.update({"status": effective_asset.status, "error": effective_asset.error})
        return inventory_row
    if not effective_asset.normalized_url or not effective_asset.target_key:
        inventory_row.update(
            {
                "status": _STATUS_MISSING_URL,
                "error": "article row does not include thumbnail_source_url",
            }
        )
        return inventory_row

    attempted_download = False
    try:
        if not config.overwrite_existing and s3.object_exists(key=effective_asset.target_key):
            inventory_row["status"] = _STATUS_ALREADY_EXISTS
            return inventory_row

        attempted_download = True
        download = download_client.download_thumbnail(
            effective_asset.normalized_url, max_bytes=max_bytes
        )
        final_url = _validate_thumbnail_url(
            download.final_url,
            allowed_hosts=config.allowed_thumbnail_hosts,
        )
        if len(download.content) > max_bytes:
            raise ThumbnailTooLargeError(f"thumbnail exceeds max size of {max_bytes} bytes")
        sha256 = hashlib.sha256(download.content).hexdigest()
        s3.put_bytes(
            key=effective_asset.target_key,
            payload=download.content,
            content_type=download.content_type,
        )
        inventory_row.update(
            {
                "status": _STATUS_DOWNLOADED,
                "sha256": sha256,
                "size_bytes": len(download.content),
                "content_type": download.content_type,
                "final_url": final_url,
            }
        )
        if index <= 5 or index % _THUMBNAIL_LOG_INTERVAL == 0 or index == total:
            _log_info(
                progress_log,
                "news_feeds: hydrated thumbnail %s/%s article_key=%s key=%s size=%s",
                index,
                total,
                effective_asset.article_key,
                effective_asset.target_key,
                len(download.content),
            )
    except ValueError as exc:
        inventory_row.update({"status": _STATUS_VALIDATION_ERROR, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        status = (
            _STATUS_TOO_LARGE if isinstance(exc, ThumbnailTooLargeError) else _STATUS_DOWNLOAD_ERROR
        )
        inventory_row.update({"status": status, "error": str(exc)})
    finally:
        if attempted_download and config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)
    return inventory_row


def _base_thumbnail_inventory_row(
    planned_asset: PlannedThumbnailAsset,
    *,
    run_id: str,
    created_at: str,
    s3: Any,
) -> dict[str, Any]:
    source_row = planned_asset.source_row
    row: dict[str, Any] = {
        "run_id": run_id,
        "created_at": created_at,
        "source_manifest": source_row.source_manifest_key,
        "source_manifest_run_id": source_row.source_manifest_run_id,
        "source_article_key": source_row.source_article_key,
        "source_file_name": source_row.source_file_name,
        "source_article_line": source_row.line_number,
        "source_article_row": source_row.row,
        "article_key": planned_asset.article_key,
        "url": string_value(source_row.row.get("url")),
        "canonical_url": string_value(source_row.row.get("canonical_url")),
        "headline": string_value(source_row.row.get("headline")),
        "source_feed_url": string_value(source_row.row.get("source_feed_url")),
        "source_name": string_value(source_row.row.get("source_name")),
    }
    if planned_asset.source_url:
        row["thumbnail_source_url"] = planned_asset.source_url
    if planned_asset.article_url:
        row["article_url"] = planned_asset.article_url
    if planned_asset.normalized_url:
        row["normalized_url"] = planned_asset.normalized_url
    if planned_asset.target_key:
        row["target_key"] = planned_asset.target_key
        public_url = public_url_for_key(s3=s3, key=planned_asset.target_key)
        if public_url:
            row["public_url"] = public_url
    return row


def _load_thumbnail_inventory_map(*, s3: Any, inventory_prefix: str) -> dict[str, dict[str, Any]]:
    inventory_rows: dict[str, dict[str, Any]] = {}
    for candidate_inventory_key in sorted(s3.list_keys(prefix=inventory_prefix)):
        if not candidate_inventory_key.endswith(".jsonl"):
            continue
        for _, row in parse_jsonl_text(
            text=s3.read_text(key=candidate_inventory_key),
            source_key=candidate_inventory_key,
            row_label="News row",
        ):
            normalized_url = string_value(row.get("normalized_url"))
            if not normalized_url:
                continue
            status = string_value(row.get("status"))
            if status not in {_STATUS_DOWNLOADED, _STATUS_ALREADY_EXISTS}:
                continue
            inventory_rows[normalized_url] = row
            article_key = string_value(row.get("article_key"))
            if article_key:
                inventory_rows[f"article:{article_key}"] = row
    return inventory_rows


def _dedupe_article_rows(source_rows: Sequence[ManifestArticleRow]) -> list[ManifestArticleRow]:
    by_key: dict[str, ManifestArticleRow] = {}
    for source_row in source_rows:
        key = _article_key(source_row.row)
        existing = by_key.get(key)
        if existing is None or _row_sort_datetime(source_row.row) >= _row_sort_datetime(
            existing.row
        ):
            by_key[key] = source_row
    return sorted(by_key.values(), key=lambda row: _row_sort_datetime(row.row), reverse=True)


def _article_payload(
    *,
    source_row: ManifestArticleRow,
    thumbnail_map: Mapping[str, Mapping[str, Any]],
    updated_at: datetime,
) -> dict[str, Any]:
    row = source_row.row
    thumbnail_source_url = _thumbnail_source_url(row)
    normalized_thumbnail_url = ""
    if thumbnail_source_url:
        try:
            normalized_thumbnail_url = _validate_thumbnail_url(
                thumbnail_source_url,
                allowed_hosts=(),
            )
        except ValueError:
            normalized_thumbnail_url = ""
    thumbnail_inventory = (
        thumbnail_map.get(normalized_thumbnail_url) if normalized_thumbnail_url else None
    )
    if thumbnail_inventory is None:
        thumbnail_inventory = thumbnail_map.get(f"article:{_article_key(row)}")
    if not thumbnail_source_url and thumbnail_inventory:
        thumbnail_source_url = string_value(thumbnail_inventory.get("thumbnail_source_url"))
    thumbnail_url = (
        string_value(thumbnail_inventory.get("public_url")) if thumbnail_inventory else ""
    )
    if not thumbnail_url:
        thumbnail_url = thumbnail_source_url
    headline = clean_text(string_value(row.get("headline")))
    summary = clean_text(string_value(row.get("summary")))
    return {
        "article_key": _article_key(row),
        "url": string_value(row.get("url")),
        "canonical_url": string_value(row.get("canonical_url")),
        "headline": headline,
        "summary": summary,
        "source_name": string_value(row.get("source_name")),
        "source_feed_url": string_value(row.get("source_feed_url")),
        "thumbnail_url": thumbnail_url or None,
        "thumbnail_asset_key": (
            string_value(thumbnail_inventory.get("target_key")) if thumbnail_inventory else None
        ),
        "thumbnail_source_url": thumbnail_source_url or None,
        "publish_date": _parse_datetime(row.get("publish_date")),
        "discovered_at": _parse_datetime(row.get("discovered_at") or row.get("_scraped_at")),
        "topic_tags": _infer_topic_tags(headline=headline, summary=summary, row=row),
        "raw_manifest_key": source_row.source_manifest_key,
        "raw_run_id": source_row.source_manifest_run_id,
        "is_active": True,
        "updated_at": updated_at,
    }


def _thumbnail_source_url(row: Mapping[str, Any]) -> str:
    explicit_url = string_value(row.get("thumbnail_source_url"))
    if explicit_url:
        return explicit_url
    return string_value(
        extract_thumbnail_url_from_raw_entry_xml(string_value(row.get("raw_entry_xml")))
    )


def _article_url(row: Mapping[str, Any]) -> str:
    return string_value(row.get("canonical_url")) or string_value(row.get("url"))


def _resolve_article_thumbnail_url(
    *,
    download_client: ThumbnailDownloader,
    article_url: str,
) -> str | None:
    resolver = getattr(download_client, "resolve_article_thumbnail_url", None)
    if not callable(resolver):
        return None
    return string_value(resolver(article_url)) or None


def _article_update_params(article: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        article["url"],
        article["canonical_url"] or None,
        _trim_text(article["headline"], 1000),
        _trim_text(article["summary"], 4000) or None,
        article["source_name"] or None,
        article["source_feed_url"] or None,
        article["thumbnail_url"],
        None,
        article["publish_date"],
        article["discovered_at"],
        article["topic_tags"],
        article["raw_manifest_key"],
        article["raw_run_id"],
        article["is_active"],
        article["updated_at"],
        article["article_key"],
        article["url"],
    )


def _article_insert_params(article: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        article["article_key"],
        article["url"],
        article["canonical_url"] or None,
        _trim_text(article["headline"], 1000),
        _trim_text(article["summary"], 4000) or None,
        article["source_name"] or None,
        article["source_feed_url"] or None,
        article["thumbnail_url"],
        None,
        article["publish_date"],
        article["discovered_at"],
        article["topic_tags"],
        article["raw_manifest_key"],
        article["raw_run_id"],
        article["is_active"],
        article["updated_at"],
    )


def _infer_topic_tags(*, headline: str, summary: str, row: Mapping[str, Any]) -> list[str]:
    text = " ".join(
        (
            headline,
            summary,
            string_value(row.get("source_name")),
            string_value(row.get("source_feed_url")),
        )
    ).lower()
    rules = {
        "dubai": ("dubai", "dxb"),
        "abu_dhabi": ("abu dhabi",),
        "uae": ("uae", "emirates"),
        "offplan": ("off-plan", "off plan", "new launch", "launches"),
        "rentals": ("rent", "rental", "tenant", "lease"),
        "sales": ("sale", "sales", "sold", "transaction"),
        "mortgages": ("mortgage", "interest rate"),
        "developers": ("developer", "aldar", "emaar", "nakheel", "damac", "sobha"),
        "market": ("market", "price", "prices", "yield", "demand"),
        "policy": ("law", "regulation", "policy", "visa", "tax"),
        "infrastructure": ("metro", "airport", "road", "transport", "infrastructure"),
        "commercial": ("office", "retail", "commercial"),
        "luxury": ("luxury", "prime", "branded residence"),
    }
    tags = [tag for tag, needles in rules.items() if any(needle in text for needle in needles)]
    return sorted(set(tags))


def _validate_thumbnail_url(url: str, *, allowed_hosts: Sequence[str]) -> str:
    return normalize_external_url(
        url,
        allowed_schemes=tuple(sorted(_PUBLIC_NEWS_URL_SCHEMES)),
        allowed_hosts=tuple(allowed_hosts) if allowed_hosts else None,
        label="thumbnail URL",
    )


def _validate_public_url(url: str) -> str:
    return normalize_external_url(
        url,
        allowed_schemes=tuple(sorted(_PUBLIC_NEWS_URL_SCHEMES)),
        label="URL",
    )


def _thumbnail_target_key(*, target_prefix: str, normalized_url: str, name: str) -> str:
    url_sha256 = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    return f"{target_prefix.rstrip('/')}/{url_sha256}/{_safe_target_file_name(name=name, normalized_url=normalized_url)}"


def _safe_target_file_name(*, name: str, normalized_url: str) -> str:
    parsed_suffix = Path(urlparse(normalized_url).path).suffix
    content_suffix = mimetypes.guess_extension(mimetypes.guess_type(normalized_url)[0] or "")
    suffix = (
        parsed_suffix if parsed_suffix and len(parsed_suffix) <= 12 else content_suffix or ".bin"
    )
    stem = Path(name).stem or "thumbnail"
    safe_stem = safe_path_segment(stem) or "thumbnail"
    if len(safe_stem) > 120:
        safe_stem = safe_stem[:120]
    return f"{safe_stem}{suffix}"


def _lookback_cutoff(*, now: datetime, lookback_days: int) -> datetime | None:
    if lookback_days <= 0:
        return None
    current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return current.astimezone(UTC) - timedelta(days=lookback_days)


def _row_within_lookback(row: Mapping[str, Any], *, cutoff: datetime) -> bool:
    candidates = (
        _parse_datetime(row.get("publish_date")),
        _parse_datetime(row.get("discovered_at")),
        _parse_datetime(row.get("_scraped_at")),
    )
    parsed_candidates = [candidate for candidate in candidates if candidate is not None]
    if not parsed_candidates:
        return True
    return any(candidate >= cutoff for candidate in parsed_candidates)


def _row_sort_datetime(row: Mapping[str, Any]) -> datetime:
    return (
        _parse_datetime(row.get("publish_date"))
        or _parse_datetime(row.get("discovered_at"))
        or _parse_datetime(row.get("_scraped_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _article_key(row: Mapping[str, Any]) -> str:
    key = string_value(row.get("article_key"))
    if key:
        return key
    basis = string_value(row.get("canonical_url")) or string_value(row.get("url"))
    if not basis:
        basis = "|".join(
            (
                string_value(row.get("source_feed_url")),
                string_value(row.get("guid")),
                string_value(row.get("headline")),
            )
        )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


def _thumbnail_headers() -> dict[str, str]:
    return {
        "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "user-agent": _USER_AGENT,
    }


def _article_headers() -> dict[str, str]:
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "user-agent": _USER_AGENT,
    }


def _trim_text(value: Any, limit: int) -> str:
    text = string_value(value)
    return text[:limit]


def _log_thumbnail_progress(
    progress_log: Any,
    *,
    completed: int,
    total: int,
    status_counts: Counter[str],
    downloaded_bytes: int,
) -> None:
    if completed <= 5 or completed % _THUMBNAIL_LOG_INTERVAL == 0 or completed == total:
        _log_info(
            progress_log,
            (
                "news_feeds: thumbnail progress completed=%s/%s downloaded=%s "
                "already_exists=%s missing_url=%s validation_error=%s download_error=%s "
                "too_large=%s bytes=%s"
            ),
            completed,
            total,
            status_counts[_STATUS_DOWNLOADED],
            status_counts[_STATUS_ALREADY_EXISTS],
            status_counts[_STATUS_MISSING_URL],
            status_counts[_STATUS_VALIDATION_ERROR],
            status_counts[_STATUS_DOWNLOAD_ERROR],
            status_counts[_STATUS_TOO_LARGE],
            format_bytes(downloaded_bytes),
        )


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.info(message, *args)
