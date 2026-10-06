from __future__ import annotations

from pydantic import Field

from holocron.contracts import SourceSpec
from holocron.pydantic_helpers import CsvTuple, HolocronModel, NonBlankStr
from holocron.sources.entrypoints import lazy_extractor

NEWS_FEEDS_SOURCE_NAME = "news_feeds"
NEWS_PROVIDER = "news"
DEFAULT_NEWS_FEED_URLS = (
    "https://meconstructionnews.com/feed",
    "https://www.thenationalnews.com/arc/outboundfeeds/rss/category/business/?outputType=xml",
    "https://gulfnews.com/stories.rss",
    "https://www.dubaichronicle.com/feed/",
    "https://logisticsgulf.com/category/warehousing/feed/",
    "https://www.meed.com/sector/construction/rss",
    "https://www.meed.com/countries/gcc/uae/rss/feed",
    "https://www.meed.com/countries/gcc/saudi-arabia/rss/feed",
    "https://www.meed.com/sector/transport/rss",
    "https://www.meed.com/sector/economy/tourism/rss",
    "https://www.worldpropertyjournal.com/feed.xml",
    "https://feeds.bloomberg.com/business/news.rss",
    "https://feeds.bloomberg.com/economics/news.rss",
    "https://feeds.bloomberg.com/industries/news.rss",
    "https://feeds.bloomberg.com/markets/news.rss",
)


class NewsFeedsConfig(HolocronModel):
    feed_urls: CsvTuple = ()
    feed_urls_file: str = ""
    max_entries_per_feed: int | None = Field(default=100, ge=1)
    include_raw_entry_xml: bool = True
    include_raw_feed_xml: bool = False
    request_timeout_seconds: float = Field(default=60, ge=1)
    user_agent: NonBlankStr = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )


extract_release = lazy_extractor(f"{__package__}.extract")


SOURCE = SourceSpec(
    name=NEWS_FEEDS_SOURCE_NAME,
    provider=NEWS_PROVIDER,
    extractor=extract_release,
    checkpoint_strategy="polling_snapshot",
    cadence="*/15 * * * *",
    description="RSS/Atom news feed polling into immutable raw releases.",
)
