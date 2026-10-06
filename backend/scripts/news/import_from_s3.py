from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import aioboto3
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.cache import RedisCache  # noqa: E402
from app.news.models import NewsArticle  # noqa: E402

DEFAULT_PREFIX = "raw/source=news_feeds/"
DEFAULT_ARTICLES_FILENAME = "news_feed_articles.jsonl"
DEFAULT_THUMBNAIL_MANIFEST_PREFIX = "raw/source=news_feeds/thumbnail_asset_manifests/"
NEWS_THUMBNAIL_PREFIX = "media/news/thumbnails/"


@dataclass
class ImportStats:
    fetched: int = 0
    normalized: int = 0
    skipped: int = 0
    existing: int = 0
    inserted: int = 0
    updated: int = 0


def load_env() -> None:
    for path in (Path.cwd() / ".env.dev", Path.cwd().parent / ".env.dev"):
        if path.exists():
            load_dotenv(path, override=False)
            return


def env_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def require_env(*names: str) -> str:
    value = env_value(*names)
    if value:
        return value
    label = " or ".join(names)
    raise RuntimeError(f"Missing required environment variable: {label}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-off importer for raw object-storage news feed articles into news_articles."
    )
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument(
        "--key",
        help="Import a specific object-storage key instead of the latest feed.",
    )
    parser.add_argument("--filename", default=DEFAULT_ARTICLES_FILENAME)
    parser.add_argument(
        "--thumbnail-manifest-key",
        help="Import thumbnail object keys from a specific manifest object.",
    )
    parser.add_argument("--thumbnail-manifest-prefix", default=DEFAULT_THUMBNAIL_MANIFEST_PREFIX)
    parser.add_argument("--skip-thumbnail-manifest", action="store_true")
    parser.add_argument("--limit", type=int, help="Maximum normalized articles to insert.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update-existing", action="store_true")
    return parser.parse_args()


def pick_string(item: dict[str, Any], *field_names: str) -> str | None:
    for field_name in field_names:
        value = item.get(field_name)
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("url") or value.get("href") or value.get("src")
        if isinstance(value, list):
            value = next((entry for entry in value if entry), None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, int | float):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(text)
            except (TypeError, ValueError):
                return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clip_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def normalize_url(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().rstrip("/") or None


def normalize_article(item: dict[str, Any]) -> NewsArticle | None:
    url = pick_string(item, "canonical_url", "url", "link", "guid")
    headline = pick_string(item, "headline", "title", "name")
    if not url or not headline or len(url) > 255:
        return None

    thumbnail_url = pick_string(
        item,
        "thumbnail_url",
        "thumbnail_source_url",
        "image_url",
        "image",
        "thumbnail",
    )
    if thumbnail_url and len(thumbnail_url) > 255:
        thumbnail_url = None

    return NewsArticle(
        url=url,
        headline=clip_text(headline, 255),
        thumbnail_url=thumbnail_url,
        thumbnail_base64=pick_string(item, "thumbnail_base64"),
        publish_date=parse_datetime(
            item.get("publish_date")
            or item.get("published_at")
            or item.get("published")
            or item.get("date")
            or item.get("discovered_at")
        ),
    )


def records_from_json(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("articles", "items", "results", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        return [value]
    return []


def parse_records(data: bytes) -> tuple[list[dict[str, Any]], int]:
    text = data.decode("utf-8-sig")
    stripped = text.lstrip()
    if not stripped:
        return [], 0

    if stripped.startswith(("[", "{")):
        try:
            return records_from_json(json.loads(stripped)), 0
        except json.JSONDecodeError:
            if stripped.startswith("["):
                raise

    records: list[dict[str, Any]] = []
    malformed = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            malformed += 1
    return records, malformed


def dedupe_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
    deduped: dict[str, NewsArticle] = {}
    for article in articles:
        deduped[article.url] = article
    return list(deduped.values())


def thumbnail_target_key(item: dict[str, Any]) -> str | None:
    target_key = pick_string(item, "target_key")
    if target_key and target_key.startswith(NEWS_THUMBNAIL_PREFIX):
        return target_key
    return None


def build_thumbnail_map(records: list[dict[str, Any]]) -> dict[str, str]:
    thumbnail_map: dict[str, str] = {}
    for item in records:
        target_key = thumbnail_target_key(item)
        if not target_key:
            continue
        for field_name in ("canonical_url", "normalized_url", "url"):
            url = normalize_url(pick_string(item, field_name))
            if url:
                thumbnail_map[url] = target_key
    return thumbnail_map


def apply_thumbnail_map(articles: list[NewsArticle], thumbnail_map: dict[str, str]) -> int:
    applied = 0
    for article in articles:
        target_key = thumbnail_map.get(normalize_url(article.url) or "")
        if not target_key:
            continue
        article.thumbnail_url = target_key
        applied += 1
    return applied


def build_object_storage_config() -> dict[str, str]:
    return {
        "endpoint_url": env_value("OBJECT_STORAGE_ENDPOINT_URL") or "",
        "bucket": require_env("OBJECT_STORAGE_BUCKET"),
        "region": env_value("OBJECT_STORAGE_REGION") or "auto",
        "access_key": require_env("OBJECT_STORAGE_ACCESS_KEY_ID"),
        "secret_key": require_env("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
    }


async def get_object_storage_client():
    config = build_object_storage_config()
    session = aioboto3.Session()
    client_kwargs = {
        "aws_access_key_id": config["access_key"],
        "aws_secret_access_key": config["secret_key"],
        "region_name": config["region"],
    }
    if config["endpoint_url"]:
        client_kwargs["endpoint_url"] = config["endpoint_url"]
    return session.client("s3", **client_kwargs)


async def find_latest_articles_key(s3: Any, bucket: str, prefix: str, filename: str) -> str:
    matches: list[dict[str, Any]] = []
    paginator = s3.get_paginator("list_objects_v2")
    async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(filename) and obj.get("Size", 0) > 0:
                matches.append(obj)

    if not matches:
        raise RuntimeError(f"No non-empty {filename} objects found under {prefix}")

    latest = max(
        matches,
        key=lambda obj: obj.get("LastModified") or datetime.min.replace(tzinfo=timezone.utc),
    )
    return latest["Key"]


async def find_latest_thumbnail_manifest_key(s3: Any, bucket: str, prefix: str) -> str | None:
    matches: list[dict[str, Any]] = []
    paginator = s3.get_paginator("list_objects_v2")
    async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith("news_thumbnail_assets.jsonl") and obj.get("Size", 0) > 0:
                matches.append(obj)

    if not matches:
        return None

    latest = max(
        matches,
        key=lambda obj: obj.get("LastModified") or datetime.min.replace(tzinfo=timezone.utc),
    )
    return latest["Key"]


async def download_records_object(key: str) -> tuple[list[dict[str, Any]], int]:
    bucket = require_env("OBJECT_STORAGE_BUCKET")
    async with await get_object_storage_client() as s3:
        response = await s3.get_object(Bucket=bucket, Key=key)
        data = await response["Body"].read()
    return parse_records(data)


def get_database_url() -> str:
    return require_env("POSTGRES_URL")


async def existing_urls(db: AsyncSession, urls: list[str]) -> set[str]:
    existing: set[str] = set()
    chunk_size = 500
    for index in range(0, len(urls), chunk_size):
        chunk = urls[index : index + chunk_size]
        result = await db.exec(select(NewsArticle.url).where(NewsArticle.url.in_(chunk)))
        existing.update(result.all())
    return existing


async def upsert_articles(articles: list[NewsArticle], update_existing: bool) -> ImportStats:
    stats = ImportStats(normalized=len(articles))
    engine = create_async_engine(get_database_url(), echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
            urls = [article.url for article in articles]
            current_urls = await existing_urls(db, urls)
            stats.existing = len(current_urls)

            to_insert = [article for article in articles if article.url not in current_urls]
            db.add_all(to_insert)
            stats.inserted = len(to_insert)

            if update_existing and current_urls:
                result = await db.exec(select(NewsArticle).where(NewsArticle.url.in_(current_urls)))
                existing_by_url = {article.url: article for article in result.all()}
                incoming_by_url = {article.url: article for article in articles}
                for url, existing_article in existing_by_url.items():
                    incoming = incoming_by_url[url]
                    existing_article.headline = incoming.headline
                    existing_article.thumbnail_url = incoming.thumbnail_url
                    existing_article.thumbnail_base64 = incoming.thumbnail_base64
                    existing_article.publish_date = incoming.publish_date
                    db.add(existing_article)
                    stats.updated += 1

            await db.commit()
    finally:
        await engine.dispose()

    return stats


async def clear_news_cache() -> int:
    redis_url = env_value("REDIS_URL")
    redis_password = env_value("REDIS_PASSWORD") or ""
    if not redis_url:
        return 0
    cache = RedisCache(redis_url, redis_password)
    return await cache.clear_prefix("news")


async def main() -> int:
    load_env()
    args = parse_args()
    object_storage_config = build_object_storage_config()

    key = args.key
    if not key:
        async with await get_object_storage_client() as s3:
            key = await find_latest_articles_key(
                s3,
                object_storage_config["bucket"],
                args.prefix,
                args.filename,
            )

    records, malformed = await download_records_object(key)
    normalized = [article for item in records if (article := normalize_article(item)) is not None]
    articles = dedupe_articles(normalized)

    thumbnail_manifest_key = args.thumbnail_manifest_key
    thumbnails_applied = 0
    if not args.skip_thumbnail_manifest:
        if not thumbnail_manifest_key:
            async with await get_object_storage_client() as s3:
                thumbnail_manifest_key = await find_latest_thumbnail_manifest_key(
                    s3,
                    object_storage_config["bucket"],
                    args.thumbnail_manifest_prefix,
                )
        if thumbnail_manifest_key:
            thumbnail_records, thumbnail_malformed = await download_records_object(
                thumbnail_manifest_key
            )
            malformed += thumbnail_malformed
            thumbnails_applied = apply_thumbnail_map(
                articles,
                build_thumbnail_map(thumbnail_records),
            )

    if args.limit is not None:
        articles = articles[: args.limit]

    stats = ImportStats(
        fetched=len(records),
        normalized=len(articles),
        skipped=len(records) - len(normalized) + malformed,
    )

    print(f"source_key={key}")
    if thumbnail_manifest_key:
        print(f"thumbnail_manifest_key={thumbnail_manifest_key}")
    print(
        f"fetched={stats.fetched} normalized={stats.normalized} "
        f"skipped={stats.skipped} thumbnails_applied={thumbnails_applied} dry_run={args.dry_run}"
    )

    for article in articles[:5]:
        date = article.publish_date.isoformat() if article.publish_date else ""
        print(f"preview\t{date}\t{article.headline}\t{article.url}")

    if args.dry_run:
        return 0

    db_stats = await upsert_articles(articles, args.update_existing)
    cache_deleted = await clear_news_cache()
    print(
        f"inserted={db_stats.inserted} existing={db_stats.existing} "
        f"updated={db_stats.updated} cache_deleted={cache_deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
