# news_feeds

RSS/Atom news polling source for the frontend news cards.

## Raw Files

- `news_feed_polls.jsonl`: one row per feed fetch attempt, including status,
  final URL, content type, entry count, and raw feed hash.
- `news_feed_articles.jsonl`: one row per feed entry, including headline, URL,
  canonical URL, summary, publish date, feed/source metadata, thumbnail source
  URL, and raw entry XML by default.

## Runtime Flow

1. `news_feeds_raw` polls configured RSS/Atom feeds and writes immutable raw
   JSONL plus a raw manifest to R2.
2. `news_thumbnail_assets` reads recent raw manifests, mirrors discovered
   thumbnails to `media/news/thumbnails`, and writes an inventory JSONL under
   `raw/source=news_feeds/thumbnail_asset_manifests`.
3. `news_publish` reads recent raw article rows plus thumbnail inventories and
   upserts frontend-ready rows into platform Postgres `news_articles`.

The scheduled job `news_feeds_poll_and_hydrate` is defined at 15-minute cadence
and stopped by default. It polls raw feeds and hydrates missing thumbnails, but
does not publish to Postgres. Its thumbnail step is limited to the latest raw
manifest from the scheduled run. Manual publishing backfills use
`news_publish_backfill`, which defaults to a 3-day lookback and runs thumbnail
hydration before publishing. Thumbnail-only archive backfills use
`news_thumbnail_assets_backfill`, which scans the full raw news archive and
writes only mirrored thumbnails plus inventory manifests to R2. When an
archived feed row has no image URL, the thumbnail-only backfill fetches the
article page and looks for page-level image metadata.

## Configuration

Raw polling:

- Curated defaults are used when no explicit feeds are configured.
- `NEWS_FEED_URLS`: newline-separated feed URLs.
- `feed_urls`: explicit feed URLs passed in Dagster config.
- `feed_urls_file`: optional newline-separated feed URL file.
- Explicit URLs from those inputs are combined and deduped for the run. The
  curated defaults are used only when the combined explicit set is empty.
- `max_entries_per_feed`: default `100`.

Current curated defaults:

- `https://meconstructionnews.com/feed`
- `https://www.thenationalnews.com/arc/outboundfeeds/rss/category/business/?outputType=xml`
- `https://gulfnews.com/stories.rss`
- `https://www.dubaichronicle.com/feed/`
- `https://logisticsgulf.com/category/warehousing/feed/`
- `https://www.meed.com/sector/construction/rss`
- `https://www.meed.com/countries/gcc/uae/rss/feed`
- `https://www.meed.com/countries/gcc/saudi-arabia/rss/feed`
- `https://www.meed.com/sector/transport/rss`
- `https://www.meed.com/sector/economy/tourism/rss`
- `https://www.worldpropertyjournal.com/feed.xml`
- `https://feeds.bloomberg.com/business/news.rss`
- `https://feeds.bloomberg.com/economics/news.rss`
- `https://feeds.bloomberg.com/industries/news.rss`
- `https://feeds.bloomberg.com/markets/news.rss`

Thumbnail hydration:

- `lookback_days`: default `3`.
- `manifest_keys`: optional exact raw manifest keys to hydrate.
- `latest_manifest_count`: optional latest-manifest limit; scheduled
  poll-and-hydrate defaults this to `1`.
- `target_prefix`: default `media/news/thumbnails`.
- `max_assets_per_run`: default `1000`.
- `max_concurrent_downloads`: default `8`.
- `allowed_thumbnail_hosts`: optional host allowlist; empty permits public
  HTTP/HTTPS hosts and blocks localhost/private IP literals.
- `resolve_missing_from_article_pages`: fetch article HTML and inspect
  `og:image`, `twitter:image`, `image_src`, and the first image when feed rows
  do not expose a thumbnail URL; default `false` on the asset.

Platform publish:

- `PLATFORM_POSTGRES_URL`: platform Postgres connection string.
- `lookback_days`: default `3`.
- `max_articles_per_run`: default `1000`.
- `ensure_schema`: default `false` on the asset; the manual publish backfill
  defaults this to `true` for first-run hydration.
- `dry_run`: build publish payloads without writing to Postgres.

`news_thumbnail_assets_backfill` overrides the thumbnail defaults to
`lookback_days=0`, `max_assets_per_run=100000`, and
`resolve_missing_from_article_pages=true` so archived raw news rows are included
without selecting `news_publish`.

## R2 Layout

```text
raw/source=news_feeds/extract_date=<YYYY-MM-DD>/run_id=<run_id>/news_feed_polls.jsonl
raw/source=news_feeds/extract_date=<YYYY-MM-DD>/run_id=<run_id>/news_feed_articles.jsonl
raw/source=news_feeds/manifests/<run_id>.json
media/news/thumbnails/<url_sha256>/<safe_file_name>
raw/source=news_feeds/thumbnail_asset_manifests/run_id=<run_id>/news_thumbnail_assets.jsonl
```

## Notes

The source stores topic tags with simple keyword rules for frontend filtering.
Those tags are intentionally lightweight; richer classification can be layered
on later from the raw article archive.
