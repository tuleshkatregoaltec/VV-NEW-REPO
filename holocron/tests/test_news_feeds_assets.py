import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from holocron.sources.news_feeds.assets import (
    NewsPublishConfig,
    NewsThumbnailHydrationConfig,
    ThumbnailDownload,
    hydrate_news_thumbnail_assets,
    publish_news_to_platform,
)
from tests.fakes import FakeS3, _jsonl_bytes


class FakeThumbnailDownloader:
    def __init__(self, page_thumbnails: dict[str, str] | None = None) -> None:
        self.downloaded: list[str] = []
        self.page_thumbnails = page_thumbnails or {}

    def download_thumbnail(self, url: str, *, max_bytes: int) -> ThumbnailDownload:
        self.downloaded.append(url)
        return ThumbnailDownload(
            content=b"image-bytes",
            content_type="image/jpeg",
            final_url=url,
        )

    def resolve_article_thumbnail_url(self, url: str) -> str | None:
        return self.page_thumbnails.get(url)


class FakeNewsWriter:
    def __init__(self) -> None:
        self.articles: list[dict[str, Any]] = []
        self.ensure_schema = False
        self.dry_run = False

    def upsert_articles(
        self,
        articles,
        *,
        ensure_schema: bool,
        dry_run: bool,
    ):
        self.articles = [dict(article) for article in articles]
        self.ensure_schema = ensure_schema
        self.dry_run = dry_run
        return {
            "published": len(self.articles),
            "created": len(self.articles),
            "updated": 0,
            "failed": 0,
        }


def test_news_thumbnail_hydration_writes_inventory_for_statuses() -> None:
    hero_url = "https://images.example.com/hero.jpg"
    already_url = "https://images.example.com/already.jpg"
    existing_key = _thumbnail_target_key(already_url)
    s3 = FakeS3(
        {
            "raw/source=news_feeds/manifests/run_id=run-1/manifest.json": json.dumps(
                {
                    "run_id": "run-1",
                    "files": [
                        {
                            "path": "news_feed_articles.jsonl",
                            "s3_key": "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl",
                            "row_count": 4,
                        }
                    ],
                }
            ).encode(),
            "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl": _jsonl_bytes(
                [
                    _article_row("a1", "Dubai market update", hero_url),
                    _article_row("a2", "Already mirrored", already_url),
                    _article_row("a3", "No thumbnail", ""),
                    _article_row("a4", "Invalid thumbnail", "http://localhost/private.jpg"),
                ]
            ),
            existing_key: b"existing",
        }
    )
    downloader = FakeThumbnailDownloader()

    result = hydrate_news_thumbnail_assets(
        s3=s3,
        config=NewsThumbnailHydrationConfig(
            lookback_days=10,
            max_concurrent_downloads=1,
        ),
        now=datetime(2026, 5, 1, tzinfo=UTC),
        download_client=downloader,
    )

    inventory_key = result["inventory_manifest_key"]
    inventory_rows = [json.loads(line) for line in s3.objects[inventory_key].decode().splitlines()]
    statuses = {row["article_key"]: row["status"] for row in inventory_rows}
    assert statuses == {
        "a1": "downloaded",
        "a2": "already_exists",
        "a3": "missing_url",
        "a4": "validation_error",
    }
    assert downloader.downloaded == [hero_url]
    assert result["downloaded"] == 1
    assert result["skipped_existing"] == 1
    assert result["already_exists"] == 1
    assert result["errors"] == 2


def test_news_thumbnail_hydration_uses_raw_entry_xml_fallback() -> None:
    media_url = "https://images.example.com/archive-thumb.jpg"
    s3 = FakeS3(
        {
            "raw/source=news_feeds/manifests/run_id=run-1/manifest.json": json.dumps(
                {
                    "run_id": "run-1",
                    "files": [
                        {
                            "path": "news_feed_articles.jsonl",
                            "s3_key": "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl",
                            "row_count": 1,
                        }
                    ],
                }
            ).encode(),
            "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl": _jsonl_bytes(
                [
                    _article_row(
                        "a1",
                        "Archive thumbnail",
                        "",
                        raw_entry_xml=(
                            '<item xmlns:media="http://search.yahoo.com/mrss/">'
                            "<title>Archive thumbnail</title>"
                            f'<media:thumbnail url="{media_url}" width="280" />'
                            "</item>"
                        ),
                    )
                ]
            ),
        }
    )
    downloader = FakeThumbnailDownloader()

    result = hydrate_news_thumbnail_assets(
        s3=s3,
        config=NewsThumbnailHydrationConfig(
            lookback_days=10,
            max_concurrent_downloads=1,
        ),
        now=datetime(2026, 5, 1, tzinfo=UTC),
        download_client=downloader,
    )

    inventory_rows = [
        json.loads(line)
        for line in s3.objects[result["inventory_manifest_key"]].decode().splitlines()
    ]
    assert downloader.downloaded == [media_url]
    assert inventory_rows[0]["status"] == "downloaded"
    assert inventory_rows[0]["thumbnail_source_url"] == media_url


def test_news_thumbnail_hydration_resolves_missing_thumbnail_from_article_page() -> None:
    page_url = "https://example.com/news/a1"
    media_url = "https://images.example.com/page-thumb.jpg"
    s3 = FakeS3(
        {
            "raw/source=news_feeds/manifests/run_id=run-1/manifest.json": json.dumps(
                {
                    "run_id": "run-1",
                    "files": [
                        {
                            "path": "news_feed_articles.jsonl",
                            "s3_key": "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl",
                            "row_count": 1,
                        }
                    ],
                }
            ).encode(),
            "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl": _jsonl_bytes(
                [_article_row("a1", "Page thumbnail", "", url=page_url)]
            ),
        }
    )
    downloader = FakeThumbnailDownloader(page_thumbnails={page_url: media_url})

    result = hydrate_news_thumbnail_assets(
        s3=s3,
        config=NewsThumbnailHydrationConfig(
            lookback_days=10,
            max_concurrent_downloads=1,
            resolve_missing_from_article_pages=True,
        ),
        now=datetime(2026, 5, 1, tzinfo=UTC),
        download_client=downloader,
    )

    inventory_rows = [
        json.loads(line)
        for line in s3.objects[result["inventory_manifest_key"]].decode().splitlines()
    ]
    assert downloader.downloaded == [media_url]
    assert inventory_rows[0]["status"] == "downloaded"
    assert inventory_rows[0]["resolved_from_article_url"] == page_url
    assert inventory_rows[0]["thumbnail_source_url"] == media_url


def test_news_publish_reads_raw_and_thumbnail_inventory() -> None:
    hero_url = "https://images.example.com/hero.jpg"
    thumbnail_key = _thumbnail_target_key(hero_url)
    s3 = FakeS3(
        {
            "raw/source=news_feeds/manifests/run_id=run-1/manifest.json": json.dumps(
                {
                    "run_id": "run-1",
                    "files": [
                        {
                            "path": "news_feed_articles.jsonl",
                            "s3_key": "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl",
                            "row_count": 1,
                        }
                    ],
                }
            ).encode(),
            "raw/source=news_feeds/date=2026-04-30/run-1/news_feed_articles.jsonl": _jsonl_bytes(
                [_article_row("a1", "Dubai market prices rise", hero_url)]
            ),
            "raw/source=news_feeds/thumbnail_asset_manifests/run_id=t-1/news_thumbnail_assets.jsonl": _jsonl_bytes(
                [
                    {
                        "article_key": "a1",
                        "normalized_url": hero_url,
                        "target_key": thumbnail_key,
                        "public_url": f"https://cdn.example.com/{thumbnail_key}",
                        "status": "downloaded",
                    }
                ]
            ),
        }
    )
    writer = FakeNewsWriter()

    result = publish_news_to_platform(
        s3=s3,
        config=NewsPublishConfig(lookback_days=10, ensure_schema=True),
        now=datetime(2026, 5, 1, tzinfo=UTC),
        writer=writer,
    )

    assert result["published"] == 1
    assert writer.ensure_schema is True
    assert writer.articles[0]["article_key"] == "a1"
    assert writer.articles[0]["thumbnail_url"] == f"https://cdn.example.com/{thumbnail_key}"
    assert {"dubai", "market"} <= set(writer.articles[0]["topic_tags"])
    assert writer.articles[0]["raw_manifest_key"].endswith("manifest.json")


def _article_row(
    article_key: str,
    headline: str,
    thumbnail_source_url: str,
    *,
    raw_entry_xml: str = "",
    url: str | None = None,
) -> dict[str, Any]:
    article_url = url or f"https://example.com/news/{article_key}"
    return {
        "endpoint": "feed_entry",
        "article_key": article_key,
        "source_feed_url": "https://example.com/feed",
        "source_name": "Example News",
        "source_line_number": 1,
        "guid": article_key,
        "url": article_url,
        "canonical_url": article_url,
        "headline": headline,
        "summary": "Dubai real estate market summary",
        "publish_date": "2026-04-30T08:00:00+00:00",
        "thumbnail_source_url": thumbnail_source_url,
        "raw_entry_xml": raw_entry_xml,
        "discovered_at": "2026-04-30T08:01:00+00:00",
        "_run_id": "run-1",
        "_scraped_at": "2026-04-30T08:01:00+00:00",
    }


def _thumbnail_target_key(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()
    return f"media/news/thumbnails/{digest}/{url.rsplit('/', 1)[-1]}"
