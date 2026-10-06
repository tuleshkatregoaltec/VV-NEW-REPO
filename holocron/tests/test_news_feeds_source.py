import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from holocron.platform.settings import Settings
from holocron.sources.news_feeds.extract import (
    FeedDownload,
    extract_release,
    extract_thumbnail_url_from_html,
    extract_thumbnail_url_from_raw_entry_xml,
    parse_feed_entries,
    resolve_feed_urls,
)
from holocron.sources.news_feeds.source import DEFAULT_NEWS_FEED_URLS, NewsFeedsConfig


class FakeFeedDownloader:
    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads

    def download_feed(
        self,
        url: str,
        *,
        timeout_seconds: float,
        user_agent: str,
    ) -> FeedDownload:
        return FeedDownload(
            url=url,
            text=self.payloads[url],
            final_url=url,
            content_type="application/rss+xml",
        )


class FailingFeedDownloader:
    def download_feed(
        self,
        url: str,
        *,
        timeout_seconds: float,
        user_agent: str,
    ) -> FeedDownload:
        raise RuntimeError(f"feed unavailable: {url}")


def test_news_feeds_extract_release_writes_poll_and_article_jsonl(tmp_path: Path) -> None:
    rss = """
    <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
      <channel>
        <title>Dubai Wire</title>
        <item>
          <title><![CDATA[Dubai <b>market</b> update]]></title>
          <guid>article-1</guid>
          <link>https://example.com/news/article-1?utm_source=rss</link>
          <pubDate>Tue, 28 Apr 2026 10:30:00 +0400</pubDate>
          <description>Market summary</description>
          <content:encoded><![CDATA[
            <img class="wp-post-image" src="https://images.example.com/hero.jpg" />
          ]]></content:encoded>
        </item>
      </channel>
    </rss>
    """
    atom = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Property Atom</title>
      <entry>
        <title>New launch</title>
        <id>atom-1</id>
        <link rel="alternate" href="https://example.com/news/article-2" />
        <updated>2026-04-29T06:30:00Z</updated>
        <content type="html">&lt;img src="https://images.example.com/atom.jpg" /&gt;</content>
      </entry>
    </feed>
    """

    release = extract_release(
        tmp_path,
        config=NewsFeedsConfig(
            feed_urls=("https://example.com/rss", "https://example.com/atom"),
            max_entries_per_feed=None,
        ),
        now=datetime(2026, 4, 30, 12, tzinfo=UTC),
        downloader=FakeFeedDownloader(
            {
                "https://example.com/rss": rss,
                "https://example.com/atom": atom,
            }
        ),
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert set(files_by_name) == {"news_feed_polls.jsonl", "news_feed_articles.jsonl"}
    assert files_by_name["news_feed_polls.jsonl"].row_count == 2
    assert files_by_name["news_feed_articles.jsonl"].row_count == 2

    article_rows = [
        json.loads(line)
        for line in Path(files_by_name["news_feed_articles.jsonl"].path).read_text().splitlines()
    ]
    assert article_rows[0]["source_name"] == "Dubai Wire"
    assert article_rows[0]["headline"] == "Dubai market update"
    assert article_rows[0]["canonical_url"] == "https://example.com/news/article-1"
    assert article_rows[0]["thumbnail_source_url"] == "https://images.example.com/hero.jpg"
    assert article_rows[0]["raw_entry_xml"]
    assert article_rows[1]["source_name"] == "Property Atom"
    assert release.metadata["article_count"] == 2


def test_news_feeds_extract_release_fails_when_all_feeds_fail(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="failed for every configured feed"):
        extract_release(
            tmp_path,
            config=NewsFeedsConfig(feed_urls=("https://example.com/rss",)),
            now=datetime(2026, 4, 30, 12, tzinfo=UTC),
            downloader=FailingFeedDownloader(),
        )


def test_news_feeds_parse_entry_thumbnail_from_media_tags() -> None:
    rss = """
    <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
      <channel>
        <title>Dubai Wire</title>
        <item>
          <title>Archive story</title>
          <guid>archive-1</guid>
          <link>https://example.com/news/archive-1</link>
          <media:content url="https://images.example.com/full.jpg" width="1200" />
          <media:thumbnail url="https://images.example.com/thumb.jpg" width="280" />
        </item>
      </channel>
    </rss>
    """

    entries = parse_feed_entries(rss, source_feed_url="https://example.com/rss")

    assert entries[0].thumbnail_source_url == "https://images.example.com/thumb.jpg"
    assert (
        extract_thumbnail_url_from_raw_entry_xml(entries[0].raw_entry_xml)
        == "https://images.example.com/thumb.jpg"
    )


def test_extract_thumbnail_url_from_html_prefers_page_metadata() -> None:
    html = """
    <html>
      <head>
        <meta property="og:image" content="/images/share.jpg" />
      </head>
      <body><img src="https://images.example.com/body.jpg" /></body>
    </html>
    """

    assert (
        extract_thumbnail_url_from_html(html, base_url="https://example.com/news/story")
        == "https://example.com/images/share.jpg"
    )


def test_resolve_feed_urls_uses_curated_defaults_when_unconfigured() -> None:
    urls = resolve_feed_urls(
        config=NewsFeedsConfig(),
        settings=Settings(NEWS_FEED_URLS=""),
    )

    assert urls == DEFAULT_NEWS_FEED_URLS
    assert "https://meconstructionnews.com/feed" in urls
    assert "https://www.meed.com/sector/construction/rss" in urls
    assert "https://feeds.bloomberg.com/markets/news.rss" in urls


def test_resolve_feed_urls_explicit_config_overrides_curated_defaults() -> None:
    urls = resolve_feed_urls(
        config=NewsFeedsConfig(feed_urls=("https://example.com/feed",)),
        settings=Settings(NEWS_FEED_URLS=""),
    )

    assert urls == ("https://example.com/feed",)
