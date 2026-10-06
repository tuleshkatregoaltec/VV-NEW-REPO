from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from holocron.contracts import RawRelease
from holocron.platform.execution import build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.platform.raw_files import write_jsonl_raw_file
from holocron.platform.settings import Settings
from holocron.sources.news_feeds.source import DEFAULT_NEWS_FEED_URLS, NewsFeedsConfig, SOURCE

logger = logging.getLogger(__name__)

ARTICLES_FILE_NAME = "news_feed_articles.jsonl"
POLLS_FILE_NAME = "news_feed_polls.jsonl"
TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
IMG_TAG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
META_TAG_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
LINK_TAG_PATTERN = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
ATTR_PATTERN = re.compile(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", re.IGNORECASE | re.DOTALL)
MEDIA_RSS_NAMESPACE = "http://search.yahoo.com/mrss/"
IMAGE_URL_SUFFIXES = (".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp")
IMAGE_META_KEYS = {
    "image",
    "og:image",
    "og:image:secure_url",
    "og:image:url",
    "thumbnail",
    "thumbnailurl",
    "twitter:image",
    "twitter:image:src",
}


@dataclass(frozen=True, slots=True)
class FeedDownload:
    url: str
    text: str
    final_url: str
    content_type: str


@dataclass(frozen=True, slots=True)
class ParsedNewsEntry:
    source_feed_url: str
    source_name: str
    guid: str
    url: str
    canonical_url: str
    headline: str
    summary: str
    publish_date: datetime | None
    thumbnail_source_url: str
    raw_entry_xml: str


class FeedDownloader(Protocol):
    def download_feed(
        self, url: str, *, timeout_seconds: float, user_agent: str
    ) -> FeedDownload: ...


class UrlLibFeedDownloader:
    def download_feed(self, url: str, *, timeout_seconds: float, user_agent: str) -> FeedDownload:
        request = Request(url, headers={"User-Agent": user_agent})
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset, errors="replace")
            return FeedDownload(
                url=url,
                text=payload,
                final_url=str(response.url),
                content_type=response.headers.get_content_type() or "",
            )


def extract_release(
    output_dir: str | Path,
    *,
    config: NewsFeedsConfig | Mapping[str, Any] | None = None,
    now: datetime | None = None,
    downloader: FeedDownloader | None = None,
    progress_log: Any | None = None,
) -> RawRelease:
    parsed_config = (
        config
        if isinstance(config, NewsFeedsConfig)
        else NewsFeedsConfig.model_validate(config or {})
    )
    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    log = progress_log or logger
    feed_urls = resolve_feed_urls(config=parsed_config, settings=Settings())
    if not feed_urls:
        raise RuntimeError("news_feeds extraction has no feed URLs configured")

    downloader = downloader or UrlLibFeedDownloader()
    scraped_at = current_time.isoformat()
    poll_rows: list[dict[str, Any]] = []
    article_rows: list[dict[str, Any]] = []
    failed = 0

    _log_info(log, "news_feeds: starting raw extraction run_id=%s feeds=%s", run_id, len(feed_urls))
    for index, feed_url in enumerate(feed_urls, start=1):
        try:
            download = downloader.download_feed(
                feed_url,
                timeout_seconds=parsed_config.request_timeout_seconds,
                user_agent=parsed_config.user_agent,
            )
            entries = parse_feed_entries(download.text, source_feed_url=feed_url)
            if parsed_config.max_entries_per_feed is not None:
                entries = entries[: parsed_config.max_entries_per_feed]
            poll_row = {
                "endpoint": "feed",
                "status": "fetched",
                "source_feed_url": feed_url,
                "final_url": download.final_url,
                "content_type": download.content_type,
                "fetched_at": scraped_at,
                "entry_count": len(entries),
                "raw_feed_sha256": hashlib.sha256(download.text.encode("utf-8")).hexdigest(),
                "_run_id": run_id,
                "_scraped_at": scraped_at,
            }
            if parsed_config.include_raw_feed_xml:
                poll_row["raw_feed_xml"] = download.text
            poll_rows.append(poll_row)
            for line_number, entry in enumerate(entries, start=1):
                article_rows.append(
                    _article_row(
                        entry=entry,
                        run_id=run_id,
                        scraped_at=scraped_at,
                        source_line_number=line_number,
                        include_raw_entry_xml=parsed_config.include_raw_entry_xml,
                    )
                )
            _log_info(
                log,
                "news_feeds: fetched feed index=%s/%s url=%s entries=%s",
                index,
                len(feed_urls),
                feed_url,
                len(entries),
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            poll_rows.append(
                {
                    "endpoint": "feed",
                    "status": "fetch_error",
                    "source_feed_url": feed_url,
                    "fetched_at": scraped_at,
                    "error": str(exc),
                    "_run_id": run_id,
                    "_scraped_at": scraped_at,
                }
            )
            _log_warning(
                log, "news_feeds: failed feed index=%s url=%s error=%s", index, feed_url, exc
            )

    if failed == len(feed_urls):
        raise RuntimeError("news_feeds extraction failed for every configured feed")

    files = (
        write_jsonl_raw_file(
            output_path / POLLS_FILE_NAME,
            poll_rows,
            ensure_ascii=True,
            sort_keys=True,
            default=str,
            separators=None,
        ),
        write_jsonl_raw_file(
            output_path / ARTICLES_FILE_NAME,
            article_rows,
            ensure_ascii=True,
            sort_keys=True,
            default=str,
            separators=None,
        ),
    )
    _log_info(
        log,
        "news_feeds: completed raw extraction run_id=%s feeds=%s articles=%s failed=%s",
        run_id,
        len(feed_urls),
        len(article_rows),
        failed,
    )
    return build_raw_release(
        source=SOURCE,
        files=files,
        run_id=run_id,
        now=current_time,
        metadata={
            "config": safe_config_metadata(parsed_config),
            "feed_count": len(feed_urls),
            "article_count": len(article_rows),
            "failed_feed_count": failed,
        },
    )


def resolve_feed_urls(*, config: NewsFeedsConfig, settings: Settings) -> tuple[str, ...]:
    file_urls: tuple[str, ...] = ()
    if config.feed_urls_file.strip():
        file_urls = _parse_feed_urls(Path(config.feed_urls_file).read_text(encoding="utf-8"))
    configured_urls = _parse_feed_urls(settings.news_feed_urls)
    explicit_urls = _dedupe_urls((*config.feed_urls, *file_urls, *configured_urls))
    if explicit_urls:
        return explicit_urls
    return DEFAULT_NEWS_FEED_URLS


def parse_feed_entries(xml_text: str, *, source_feed_url: str) -> list[ParsedNewsEntry]:
    root = ET.fromstring(xml_text)
    root_name = _local_name(root.tag)
    if root_name == "rss":
        return _parse_rss_feed(root, source_feed_url=source_feed_url)
    if root_name == "feed":
        return _parse_atom_feed(root, source_feed_url=source_feed_url)
    raise ValueError(f"Unsupported feed root <{root_name}> for {source_feed_url}")


def _parse_rss_feed(root: ET.Element, *, source_feed_url: str) -> list[ParsedNewsEntry]:
    channel = next((child for child in root if _local_name(child.tag) == "channel"), root)
    source_name = clean_text(_first_child_text(channel, "title")) or _host_label(source_feed_url)
    entries: list[ParsedNewsEntry] = []
    for item in channel:
        if _local_name(item.tag) != "item":
            continue
        headline = clean_text(_first_child_text(item, "title"))
        link = (_first_child_text(item, "link") or "").strip()
        guid = (_first_child_text(item, "guid") or link).strip()
        publish_date = parse_publish_date(
            _first_child_text(item, "pubDate")
            or _first_child_text(item, "published")
            or _first_child_text(item, "updated")
            or _first_child_text(item, "date")
        )
        content_html = _first_child_text(item, "encoded") or _first_child_text(item, "description")
        entries.append(
            ParsedNewsEntry(
                source_feed_url=source_feed_url,
                source_name=source_name,
                guid=guid,
                url=link,
                canonical_url=_canonical_url(link),
                headline=headline,
                summary=clean_text(_first_child_text(item, "description")),
                publish_date=publish_date,
                thumbnail_source_url=extract_entry_thumbnail_url(item, content_html=content_html)
                or "",
                raw_entry_xml=ET.tostring(item, encoding="unicode"),
            )
        )
    return entries


def _parse_atom_feed(root: ET.Element, *, source_feed_url: str) -> list[ParsedNewsEntry]:
    source_name = clean_text(_first_child_text(root, "title")) or _host_label(source_feed_url)
    entries: list[ParsedNewsEntry] = []
    for entry in root:
        if _local_name(entry.tag) != "entry":
            continue
        headline = clean_text(_first_child_text(entry, "title"))
        link = _atom_link(entry)
        guid = (_first_child_text(entry, "id") or link).strip()
        publish_date = parse_publish_date(
            _first_child_text(entry, "published") or _first_child_text(entry, "updated")
        )
        content_html = _first_child_text(entry, "content") or _first_child_text(entry, "summary")
        entries.append(
            ParsedNewsEntry(
                source_feed_url=source_feed_url,
                source_name=source_name,
                guid=guid,
                url=link,
                canonical_url=_canonical_url(link),
                headline=headline,
                summary=clean_text(_first_child_text(entry, "summary")),
                publish_date=publish_date,
                thumbnail_source_url=extract_entry_thumbnail_url(entry, content_html=content_html)
                or "",
                raw_entry_xml=ET.tostring(entry, encoding="unicode"),
            )
        )
    return entries


def _article_row(
    *,
    entry: ParsedNewsEntry,
    run_id: str,
    scraped_at: str,
    source_line_number: int,
    include_raw_entry_xml: bool,
) -> dict[str, Any]:
    row = {
        "endpoint": "feed_entry",
        "article_key": _article_key(entry),
        "source_feed_url": entry.source_feed_url,
        "source_name": entry.source_name,
        "source_line_number": source_line_number,
        "guid": entry.guid,
        "url": entry.url,
        "canonical_url": entry.canonical_url,
        "headline": entry.headline,
        "summary": entry.summary,
        "publish_date": entry.publish_date.isoformat() if entry.publish_date else None,
        "thumbnail_source_url": entry.thumbnail_source_url,
        "discovered_at": scraped_at,
        "_run_id": run_id,
        "_scraped_at": scraped_at,
    }
    if include_raw_entry_xml:
        row["raw_entry_xml"] = entry.raw_entry_xml
    return row


def _article_key(entry: ParsedNewsEntry) -> str:
    if entry.canonical_url:
        basis = entry.canonical_url
    else:
        basis = "|".join((entry.source_feed_url, entry.guid, entry.headline))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = TAG_PATTERN.sub(" ", value)
    return WHITESPACE_PATTERN.sub(" ", unescape(without_tags)).strip()


def parse_publish_date(value: str | None) -> datetime | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        parsed = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("news_feeds: could not parse publish date %r", value)
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def extract_first_image_url(content_html: str | None) -> str | None:
    if not content_html:
        return None
    first_image: str | None = None
    for tag in IMG_TAG_PATTERN.findall(content_html):
        attrs = {name.lower(): val for name, _, val in ATTR_PATTERN.findall(tag)}
        src = attrs.get("src", "").strip()
        if not src:
            continue
        if first_image is None:
            first_image = src
        css_classes = attrs.get("class", "")
        if "wp-post-image" in css_classes.split():
            return src
    return first_image


def extract_thumbnail_url_from_html(html: str | None, *, base_url: str = "") -> str | None:
    if not html:
        return None

    for tag in META_TAG_PATTERN.findall(html):
        attrs = _tag_attrs(tag)
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if key in IMAGE_META_KEYS:
            url = attrs.get("content", "").strip()
            if url:
                return _absolutize_url(url, base_url=base_url)

    for tag in LINK_TAG_PATTERN.findall(html):
        attrs = _tag_attrs(tag)
        rel_values = set(attrs.get("rel", "").lower().split())
        href = attrs.get("href", "").strip()
        if href and ("image_src" in rel_values or attrs.get("as", "").lower() == "image"):
            return _absolutize_url(href, base_url=base_url)

    embedded_image = extract_first_image_url(html)
    if embedded_image:
        return _absolutize_url(embedded_image, base_url=base_url)
    return None


def extract_entry_thumbnail_url(
    entry: ET.Element,
    *,
    content_html: str | None = None,
) -> str | None:
    media_thumbnail = _first_media_url(entry, local_names={"thumbnail"})
    if media_thumbnail:
        return media_thumbnail

    embedded_image = extract_first_image_url(content_html)
    if embedded_image:
        return embedded_image

    return _first_media_url(entry, local_names={"image", "enclosure", "content", "link"})


def extract_thumbnail_url_from_raw_entry_xml(raw_entry_xml: str | None) -> str | None:
    if not raw_entry_xml:
        return None
    try:
        entry = ET.fromstring(raw_entry_xml)
    except ET.ParseError:
        return None
    content_html = _first_child_text(entry, "encoded") or _first_child_text(
        entry, "content", "summary", "description"
    )
    return extract_entry_thumbnail_url(entry, content_html=content_html)


def _first_media_url(entry: ET.Element, *, local_names: set[str]) -> str | None:
    for element in entry.iter():
        local_name = _local_name(element.tag)
        if local_name not in local_names:
            continue
        candidate = _media_url_candidate(element, local_name=local_name)
        if candidate:
            return candidate
    return None


def _media_url_candidate(element: ET.Element, *, local_name: str) -> str | None:
    attrs = {key.lower(): value.strip() for key, value in element.attrib.items()}
    url = attrs.get("url") or attrs.get("href") or attrs.get("src")
    if url:
        if local_name in {"thumbnail", "image"}:
            return url
        if _element_describes_image(element, local_name=local_name, attrs=attrs, url=url):
            return url

    if local_name == "image":
        nested_url = _first_child_text(element, "url")
        if nested_url:
            return nested_url.strip()
    return None


def _tag_attrs(tag: str) -> dict[str, str]:
    return {name.lower(): val for name, _, val in ATTR_PATTERN.findall(tag)}


def _absolutize_url(url: str, *, base_url: str) -> str:
    if not base_url:
        return url.strip()
    return urljoin(base_url, url.strip())


def _element_describes_image(
    element: ET.Element,
    *,
    local_name: str,
    attrs: Mapping[str, str],
    url: str,
) -> bool:
    media_type = attrs.get("type", "").lower()
    if media_type.startswith("image/"):
        return True
    if attrs.get("medium", "").lower() == "image":
        return True
    if local_name == "content" and _namespace_uri(element.tag).rstrip(
        "/"
    ) == MEDIA_RSS_NAMESPACE.rstrip("/"):
        return True
    if local_name == "link" and attrs.get("rel", "").lower() in {"enclosure", "image_src"}:
        return True
    return urlparse(url).path.lower().endswith(IMAGE_URL_SUFFIXES)


def _namespace_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _first_child_text(element: ET.Element, *names: str) -> str | None:
    wanted = set(names)
    for child in element:
        if _local_name(child.tag) not in wanted:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return None


def _atom_link(entry: ET.Element) -> str:
    fallback = ""
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "alternate").strip()
        if href and rel in {"alternate", ""}:
            return href
        if href and not fallback:
            fallback = href
    return fallback


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(fragment="", query="", path=path).geturl()


def _host_label(url: str) -> str:
    return urlparse(url).netloc.lower()


def _parse_feed_urls(raw: str) -> tuple[str, ...]:
    urls = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return tuple(urls)


def _dedupe_urls(urls: Sequence[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        cleaned = url.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return tuple(deduped)


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.info(message, *args)


def _log_warning(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.warning(message, *args)
