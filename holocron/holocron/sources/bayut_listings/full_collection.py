"""Resumable, coverage-aware Bayut residential search-card collection.

This module is deliberately separate from the bounded source collector and the
CAPTCHA attribution probe.  It plans disjoint property-type/location shards,
persists every page checkpoint in SQLite, and can rotate a complete Playwright
browser context between top-level page loads.  It does not solve challenges.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import re
import sqlite3
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Playwright,
    Route,
)
from pydantic import Field, model_validator

from holocron.pydantic_helpers import HolocronModel, NonBlankStr
from holocron.sources.bayut_listings.extract import (
    _BLOCKED_RESOURCE_TYPES,
    _is_captcha_page,
    _listing_cards,
    _listing_rows,
    _validate_search_page,
)
from holocron.sources.bayut_listings.probe import (
    NetworkMeter,
    parse_identity_payload,
    validate_identity_result,
)
from holocron.sources.bayut_listings.source import BAYUT_BASE_URL

_DB_FILE = "collection.sqlite3"
_CONFIG_FILE = "config.sanitized.json"
_SUMMARY_FILE = "summary.json"
_LISTINGS_EXPORT = "listings.jsonl"
_SHARDS_EXPORT = "shards.jsonl"
_ATTEMPTS_EXPORT = "page_attempts.jsonl"
_PROXY_SERVER_ENV = "BAYUT_FULL_PROXY_SERVER"
_PROXY_USERNAME_ENV = "BAYUT_FULL_PROXY_USERNAME"
_PROXY_PASSWORD_ENV = "BAYUT_FULL_PROXY_PASSWORD"
_SESSION_PLACEHOLDER = "{session}"
_COUNT_SUFFIX_RE = re.compile(r"\(\s*(?P<count>[\d,]+)\s*\)\s*$")
_TITLE_COUNT_RE = re.compile(r"^\s*(?P<count>[\d,]+)\s+\S")
_PAGE_SEGMENT_RE = re.compile(r"page-\d+", re.IGNORECASE)
_RETRYABLE_OUTCOMES = frozenset(
    {"captcha", "forbidden", "rate_limited", "http_error", "navigation_error"}
)
_COLLECTABLE_SHARD_STATUSES = ("ready", "collecting")


class BayutFullRoot(HolocronModel):
    """One disjoint residential property-type root."""

    name: NonBlankStr
    purpose: Literal["sale", "rent"]
    property_type: NonBlankStr
    path: NonBlankStr


BAYUT_RESIDENTIAL_ROOTS = (
    BayutFullRoot(
        name="sale_apartments",
        purpose="sale",
        property_type="apartment",
        path="/for-sale/apartments/dubai/",
    ),
    BayutFullRoot(
        name="sale_villas",
        purpose="sale",
        property_type="villa",
        path="/for-sale/villas/dubai/",
    ),
    BayutFullRoot(
        name="sale_townhouses",
        purpose="sale",
        property_type="townhouse",
        path="/for-sale/townhouses/dubai/",
    ),
    BayutFullRoot(
        name="sale_penthouses",
        purpose="sale",
        property_type="penthouse",
        path="/for-sale/penthouse/dubai/",
    ),
    BayutFullRoot(
        name="sale_hotel_apartments",
        purpose="sale",
        property_type="hotel_apartment",
        path="/for-sale/hotel-apartments/dubai/",
    ),
    BayutFullRoot(
        name="sale_residential_plots",
        purpose="sale",
        property_type="residential_plot",
        path="/for-sale/residential-plots/dubai/",
    ),
    BayutFullRoot(
        name="sale_residential_buildings",
        purpose="sale",
        property_type="residential_building",
        path="/for-sale/residential-building/dubai/",
    ),
    BayutFullRoot(
        name="sale_villa_compounds",
        purpose="sale",
        property_type="villa_compound",
        path="/for-sale/villa-compound/dubai/",
    ),
    BayutFullRoot(
        name="sale_residential_floors",
        purpose="sale",
        property_type="residential_floor",
        path="/for-sale/residential-floors/dubai/",
    ),
    BayutFullRoot(
        name="rent_apartments",
        purpose="rent",
        property_type="apartment",
        path="/to-rent/apartments/dubai/",
    ),
    BayutFullRoot(
        name="rent_villas",
        purpose="rent",
        property_type="villa",
        path="/to-rent/villas/dubai/",
    ),
    BayutFullRoot(
        name="rent_townhouses",
        purpose="rent",
        property_type="townhouse",
        path="/to-rent/townhouses/dubai/",
    ),
    BayutFullRoot(
        name="rent_hotel_apartments",
        purpose="rent",
        property_type="hotel_apartment",
        path="/to-rent/hotel-apartments/dubai/",
    ),
    BayutFullRoot(
        name="rent_penthouses",
        purpose="rent",
        property_type="penthouse",
        path="/to-rent/penthouse/dubai/",
    ),
    BayutFullRoot(
        name="rent_villa_compounds",
        purpose="rent",
        property_type="villa_compound",
        path="/to-rent/villa-compound/dubai/",
    ),
    BayutFullRoot(
        name="rent_residential_buildings",
        purpose="rent",
        property_type="residential_building",
        path="/to-rent/residential-building/dubai/",
    ),
)


class BayutFullCollectionConfig(HolocronModel):
    """Configuration for planning and collecting a complete card inventory."""

    base_url: NonBlankStr = BAYUT_BASE_URL
    roots: tuple[BayutFullRoot, ...] = BAYUT_RESIDENTIAL_ROOTS
    max_results_per_shard: int = Field(default=1_200, ge=100, le=15_000)
    max_pages_per_shard: int = Field(default=100, ge=1, le=500)
    minimum_expected_cards_per_page: int = Field(default=12, ge=1, le=100)
    max_location_depth: int = Field(default=6, ge=1, le=12)
    minimum_child_count_coverage: float = Field(default=1.0, ge=0.8, le=1.05)
    maximum_child_count_coverage: float = Field(default=1.05, ge=0.95, le=1.25)
    minimum_observed_count_coverage: float = Field(default=1.0, ge=0.5, le=1.05)
    timeout_seconds: float = Field(default=60, ge=1, le=300)
    settle_milliseconds: int = Field(default=750, ge=0, le=30_000)
    request_pause_seconds: float = Field(default=2, ge=0, le=300)
    request_jitter_seconds: float = Field(default=1, ge=0, le=300)
    headless: bool = True
    browser: Literal["chromium", "firefox", "webkit"] = "chromium"
    chrome_path: str = ""
    storage_state_path: str = ""
    block_media_requests: bool = True
    resource_mode: Literal["browser", "document"] = "browser"
    proxy: Literal["direct", "residential"] = "direct"
    proxy_rotation: Literal["provider_default", "context"] = "provider_default"
    pages_per_context: int = Field(default=1, ge=1, le=100)
    identity_url: str = ""
    expected_country: str = ""
    require_identity_success: bool = True
    correlation_header_name: str = ""
    max_attempts_per_page: int = Field(default=3, ge=1, le=10)
    max_consecutive_failed_pages: int = Field(default=3, ge=1, le=100)
    retry_backoff_seconds: float = Field(default=5, ge=0, le=300)
    evidence: Literal["none", "challenge", "all"] = "challenge"
    random_seed: int = 20260829

    @model_validator(mode="after")
    def validate_config(self) -> "BayutFullCollectionConfig":
        if not self.roots:
            raise ValueError("roots must contain at least one residential search root")
        names = [root.name for root in self.roots]
        paths = [canonical_search_path(root.path) for root in self.roots]
        if len(names) != len(set(names)):
            raise ValueError("root names must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("root paths must be unique")
        if self.chrome_path and self.browser != "chromium":
            raise ValueError("chrome_path is only valid with browser=chromium")
        if self.proxy == "direct" and self.proxy_rotation != "provider_default":
            raise ValueError("direct collection must use proxy_rotation=provider_default")
        if self.proxy == "residential" and self.require_identity_success:
            if not self.identity_url:
                raise ValueError("identity_url is required for residential collection")
            if "REPLACE-" in self.identity_url.upper():
                raise ValueError("replace the identity_url placeholder before running")
        if self.correlation_header_name and not all(
            character.isalnum() or character == "-" for character in self.correlation_header_name
        ):
            raise ValueError("correlation_header_name may only contain letters, numbers, and -")
        if self.maximum_child_count_coverage < self.minimum_child_count_coverage:
            raise ValueError(
                "maximum_child_count_coverage must be at least minimum_child_count_coverage"
            )
        if self.max_results_per_shard > (
            self.max_pages_per_shard * self.minimum_expected_cards_per_page
        ):
            raise ValueError(
                "max_results_per_shard exceeds the conservative page capacity; "
                "increase max_pages_per_shard or lower the shard size"
            )
        return self


@dataclass(frozen=True, slots=True)
class LocationLink:
    path: str
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    title: str
    html: str
    cards: tuple[dict[str, str], ...]
    location_anchors: tuple[dict[str, str], ...]
    outcome: str
    error: str
    latency_ms: int
    network: dict[str, Any]
    identity: dict[str, Any]
    context_id: str


class FullPageFetcher(Protocol):
    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> FetchResult: ...

    def invalidate_context(self) -> None: ...


def load_full_collection_config(path: str | Path) -> BayutFullCollectionConfig:
    return BayutFullCollectionConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


def canonical_search_path(path: str) -> str:
    parts = urlsplit(path)
    value = f"/{parts.path.strip('/')}/"
    if _PAGE_SEGMENT_RE.fullmatch(value.rstrip("/").rsplit("/", 1)[-1]):
        raise ValueError(f"search path must not contain a page cursor: {path}")
    return urlunsplit(("", "", value, parts.query, ""))


def full_search_url(*, base_url: str, search_path: str, page_number: int) -> str:
    """Build Bayut's canonical `/page-N/` cursor URL."""

    if page_number < 1:
        raise ValueError("page_number must be at least 1")
    canonical = canonical_search_path(search_path)
    parts = urlsplit(canonical)
    path = parts.path if page_number == 1 else f"{parts.path}page-{page_number}/"
    return urljoin(f"{base_url.rstrip('/')}/", urlunsplit(("", "", path, parts.query, "")))


def normalize_location_links(
    *,
    current_path: str,
    anchors: Sequence[Mapping[str, str]],
    base_url: str = BAYUT_BASE_URL,
) -> tuple[LocationLink, ...]:
    """Keep direct child geography links whose label carries a Bayut result count."""

    current = urlsplit(canonical_search_path(current_path))
    current_segments = tuple(segment for segment in current.path.split("/") if segment)
    base_host = urlsplit(base_url).netloc.lower()
    links: dict[str, LocationLink] = {}
    for anchor in anchors:
        href = str(anchor.get("href") or "").strip()
        text = " ".join(str(anchor.get("text") or "").split())
        match = _COUNT_SUFFIX_RE.search(text)
        if not href or match is None:
            continue
        absolute = urlsplit(urljoin(base_url, href))
        if absolute.netloc.lower() != base_host or absolute.query:
            continue
        segments = tuple(segment for segment in absolute.path.split("/") if segment)
        if len(segments) != len(current_segments) + 1:
            continue
        if segments[: len(current_segments)] != current_segments:
            continue
        if _PAGE_SEGMENT_RE.fullmatch(segments[-1]):
            continue
        path = f"/{'/'.join(segments)}/"
        name = text[: match.start()].strip() or segments[-1]
        links[path] = LocationLink(
            path=path,
            name=name,
            count=int(match.group("count").replace(",", "")),
        )
    return tuple(sorted(links.values(), key=lambda link: link.path))


def extract_reported_count(*, title: str, html: str) -> int | None:
    match = _TITLE_COUNT_RE.search(title)
    if match is not None:
        return int(match.group("count").replace(",", ""))
    for pattern in (
        r'"totalProperties"\s*:\s*(\d+)',
        r'"totalResults"\s*:\s*(\d+)',
        r'"hits"\s*:\s*(\d+)',
    ):
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group(1))
    return None


def validate_full_proxy_environment(
    config: BayutFullCollectionConfig,
    env: Mapping[str, str] | None = None,
) -> None:
    values = env if env is not None else os.environ
    if config.proxy == "direct":
        return
    server = values.get(_PROXY_SERVER_ENV, "").strip()
    if not server:
        raise ValueError(f"{_PROXY_SERVER_ENV} is required for residential collection")
    templates = (
        server,
        values.get(_PROXY_USERNAME_ENV, ""),
        values.get(_PROXY_PASSWORD_ENV, ""),
    )
    if config.proxy_rotation == "context" and not any(
        _SESSION_PLACEHOLDER in value for value in templates
    ):
        raise ValueError(
            "context proxy rotation requires {session} in the proxy server, username, "
            "or password environment value"
        )


def sanitized_full_config(config: BayutFullCollectionConfig) -> dict[str, Any]:
    payload = config.model_dump(mode="json")
    payload["proxy_environment"] = {
        "server": _PROXY_SERVER_ENV,
        "username": _PROXY_USERNAME_ENV,
        "password": _PROXY_PASSWORD_ENV,
    }
    payload["credentials_recorded"] = False
    return payload


def shard_id(path: str) -> str:
    return hashlib.sha256(canonical_search_path(path).encode()).hexdigest()[:20]


def open_collection_database(
    *, config: BayutFullCollectionConfig, output_dir: str | Path
) -> sqlite3.Connection:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output / _DB_FILE, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    _create_schema(connection)
    serialized = json.dumps(sanitized_full_config(config), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    existing = connection.execute("SELECT value FROM metadata WHERE key='config_sha256'").fetchone()
    legacy_payload = sanitized_full_config(config)
    legacy_payload.pop("resource_mode")
    legacy_payload.pop("max_consecutive_failed_pages")
    legacy_digest = hashlib.sha256(
        json.dumps(legacy_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    compatible_legacy = (
        config.resource_mode == "browser"
        and config.max_consecutive_failed_pages == 3
        and (existing["value"] if existing is not None else None) == legacy_digest
    )
    if existing is not None and existing["value"] != digest and not compatible_legacy:
        connection.close()
        raise ValueError(
            "existing collection database was created with a different config; "
            "use the original config or a new output directory"
        )
    with connection:
        connection.execute(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES('schema_version', '1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES('config_sha256', ?)", (digest,)
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('updated_at', ?)", (_now(),)
        )
    (output / _CONFIG_FILE).write_text(
        json.dumps(sanitized_full_config(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return connection


def initialize_roots(connection: sqlite3.Connection, config: BayutFullCollectionConfig) -> None:
    with connection:
        for root in config.roots:
            path = canonical_search_path(root.path)
            connection.execute(
                """
                INSERT OR IGNORE INTO shards(
                    shard_id, root_name, purpose, property_type, path, parent_id, depth,
                    name, reported_count, status, next_page, updated_at
                ) VALUES(?, ?, ?, ?, ?, NULL, 0, ?, NULL, 'plan_pending', 1, ?)
                """,
                (
                    shard_id(path),
                    root.name,
                    root.purpose,
                    root.property_type,
                    path,
                    root.name,
                    _now(),
                ),
            )


def plan_collection(
    *,
    connection: sqlite3.Connection,
    config: BayutFullCollectionConfig,
    fetcher: FullPageFetcher,
    max_nodes: int = 0,
) -> dict[str, Any]:
    """Recursively turn property roots into count-bounded location shards."""

    initialize_roots(connection, config)
    processed = 0
    consecutive_failures = 0
    while not max_nodes or processed < max_nodes:
        row = connection.execute(
            "SELECT * FROM shards WHERE status='plan_pending' ORDER BY depth, path LIMIT 1"
        ).fetchone()
        if row is None:
            break
        processed += 1
        if (
            row["reported_count"] is not None
            and row["reported_count"] <= config.max_results_per_shard
        ):
            _update_shard_status(connection, row["shard_id"], "ready", "within_result_capacity")
            continue
        result = _fetch_with_retries(
            connection=connection,
            config=config,
            fetcher=fetcher,
            phase="plan",
            shard=row,
            page_number=1,
        )
        if result is None or result.outcome != "ok":
            _update_shard_status(
                connection,
                row["shard_id"],
                "plan_error",
                result.outcome if result is not None else "no_result",
            )
            consecutive_failures += 1
            if consecutive_failures >= config.max_consecutive_failed_pages:
                break
            continue
        consecutive_failures = 0
        reported_count = extract_reported_count(title=result.title, html=result.html)
        if reported_count is None:
            reported_count = row["reported_count"]
        children = normalize_location_links(
            current_path=row["path"],
            anchors=result.location_anchors,
            base_url=config.base_url,
        )
        child_total = sum(child.count for child in children)
        with connection:
            connection.execute(
                "UPDATE shards SET reported_count=?, child_count=?, child_reported_total=?, "
                "updated_at=? WHERE shard_id=?",
                (reported_count, len(children), child_total, _now(), row["shard_id"]),
            )
        if reported_count is None:
            _update_shard_status(connection, row["shard_id"], "unresolved", "missing_parent_count")
            continue
        if reported_count is not None and reported_count <= config.max_results_per_shard:
            _update_shard_status(connection, row["shard_id"], "ready", "within_result_capacity")
            continue
        if row["depth"] >= config.max_location_depth:
            _update_shard_status(connection, row["shard_id"], "unresolved", "max_location_depth")
            continue
        if not children:
            _update_shard_status(connection, row["shard_id"], "unresolved", "no_child_locations")
            continue
        coverage_ratio = child_total / reported_count if reported_count else 1.0
        if reported_count and not (
            config.minimum_child_count_coverage
            <= coverage_ratio
            <= config.maximum_child_count_coverage
        ):
            _update_shard_status(
                connection,
                row["shard_id"],
                "unresolved",
                f"child_count_coverage={coverage_ratio:.6f}",
            )
            continue
        with connection:
            connection.execute(
                "UPDATE shards SET status='split', stop_reason='child_locations', updated_at=? "
                "WHERE shard_id=?",
                (_now(), row["shard_id"]),
            )
            for child in children:
                child_status = (
                    "ready" if child.count <= config.max_results_per_shard else "plan_pending"
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO shards(
                        shard_id, root_name, purpose, property_type, path, parent_id, depth,
                        name, reported_count, status, next_page, stop_reason, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        shard_id(child.path),
                        row["root_name"],
                        row["purpose"],
                        row["property_type"],
                        child.path,
                        row["shard_id"],
                        row["depth"] + 1,
                        child.name,
                        child.count,
                        child_status,
                        "within_result_capacity" if child_status == "ready" else "",
                        _now(),
                    ),
                )
    return collection_status(connection)


def collect_shards(
    *,
    connection: sqlite3.Connection,
    config: BayutFullCollectionConfig,
    fetcher: FullPageFetcher,
    max_pages: int = 0,
) -> dict[str, Any]:
    """Collect every ready shard, checkpointing listings and the next page atomically."""

    blockers = connection.execute(
        "SELECT status, COUNT(*) AS count FROM shards "
        "WHERE status IN ('plan_pending', 'plan_error', 'unresolved') GROUP BY status"
    ).fetchall()
    if blockers:
        details = ", ".join(f"{row['status']}={row['count']}" for row in blockers)
        raise RuntimeError(f"coverage plan is incomplete ({details}); resolve it before collection")

    page_budget = max_pages
    processed_pages = 0
    consecutive_failures = 0
    while not page_budget or processed_pages < page_budget:
        shard = connection.execute(
            "SELECT * FROM shards WHERE status IN ('ready', 'collecting') "
            "ORDER BY purpose, property_type, path LIMIT 1"
        ).fetchone()
        if shard is None:
            break
        page_number = int(shard["next_page"])
        if page_number > config.max_pages_per_shard:
            _update_shard_status(connection, shard["shard_id"], "capped", "page_cap")
            continue
        processed_pages += 1
        result = _fetch_with_retries(
            connection=connection,
            config=config,
            fetcher=fetcher,
            phase="collect",
            shard=shard,
            page_number=page_number,
        )
        if result is None or result.outcome != "ok":
            _update_shard_status(
                connection,
                shard["shard_id"],
                "collect_error",
                result.outcome if result is not None else "no_result",
            )
            consecutive_failures += 1
            if consecutive_failures >= config.max_consecutive_failed_pages:
                break
            continue
        consecutive_failures = 0
        scraped_at = _now()
        listing_rows = _listing_rows(
            cards=result.cards,
            search_path=shard["path"],
            page=page_number,
            scraped_at=scraped_at,
        )
        ids = {str(row["listing_id"]) for row in listing_rows}
        prior_ids = {
            row["listing_id"]
            for row in connection.execute(
                "SELECT listing_id FROM listing_shards WHERE shard_id=?", (shard["shard_id"],)
            )
        }
        new_for_shard = ids - prior_ids
        with connection:
            for listing in listing_rows:
                payload = dict(listing)
                payload.update(
                    {
                        "root_name": shard["root_name"],
                        "purpose": shard["purpose"],
                        "property_type": shard["property_type"],
                        "shard_id": shard["shard_id"],
                    }
                )
                connection.execute(
                    """
                    INSERT INTO listings(listing_id, payload_json, first_seen_at, last_seen_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(listing_id) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        listing["listing_id"],
                        json.dumps(payload, separators=(",", ":"), sort_keys=True),
                        scraped_at,
                        scraped_at,
                    ),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO listing_shards(listing_id, shard_id, first_page) "
                    "VALUES(?, ?, ?)",
                    (listing["listing_id"], shard["shard_id"], page_number),
                )
            next_page = page_number + 1
            status = "collecting"
            stop_reason = ""
            if not ids:
                status, stop_reason = _terminal_collection_status(
                    observed_count=len(prior_ids),
                    reported_count=shard["reported_count"],
                    minimum_coverage=config.minimum_observed_count_coverage,
                    natural_reason="empty_page",
                )
            elif not new_for_shard:
                status, stop_reason = _terminal_collection_status(
                    observed_count=len(prior_ids | ids),
                    reported_count=shard["reported_count"],
                    minimum_coverage=config.minimum_observed_count_coverage,
                    natural_reason="duplicate_only_page",
                )
            elif page_number >= config.max_pages_per_shard:
                status = "capped"
                stop_reason = "page_cap"
            connection.execute(
                "UPDATE shards SET status=?, next_page=?, observed_unique_count=("
                "SELECT COUNT(*) FROM listing_shards WHERE shard_id=?), stop_reason=?, updated_at=? "
                "WHERE shard_id=?",
                (
                    status,
                    next_page,
                    shard["shard_id"],
                    stop_reason,
                    _now(),
                    shard["shard_id"],
                ),
            )
    return collection_status(connection)


def reset_retryable_errors(connection: sqlite3.Connection) -> None:
    """Put interrupted planner/collector shards back into their resumable states."""

    with connection:
        connection.execute(
            "UPDATE shards SET status='plan_pending', stop_reason='', updated_at=? "
            "WHERE status='plan_error'",
            (_now(),),
        )
        connection.execute(
            "UPDATE shards SET status=CASE WHEN next_page > 1 THEN 'collecting' ELSE 'ready' END, "
            "stop_reason='', updated_at=? WHERE status='collect_error'",
            (_now(),),
        )


def collection_status(connection: sqlite3.Connection) -> dict[str, Any]:
    statuses = {
        row["status"]: row["count"]
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM shards GROUP BY status ORDER BY status"
        )
    }
    terminal = connection.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(reported_count), 0) AS reported, "
        "COALESCE(SUM(observed_unique_count), 0) AS observed FROM shards "
        "WHERE status <> 'split'"
    ).fetchone()
    attempts = connection.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(response_bytes), 0) AS bytes, "
        "COALESCE(SUM(request_count), 0) AS requests, "
        "COALESCE(SUM(CASE WHEN phase='collect' AND outcome='ok' THEN card_count ELSE 0 END), 0) "
        "AS cards, "
        "COALESCE(AVG(latency_ms), 0) AS mean_latency FROM page_attempts"
    ).fetchone()
    outcomes = {
        row["outcome"]: row["count"]
        for row in connection.execute(
            "SELECT outcome, COUNT(*) AS count FROM page_attempts GROUP BY outcome ORDER BY outcome"
        )
    }
    identities = connection.execute(
        "SELECT COUNT(DISTINCT ip) AS unique_ips, COUNT(*) AS samples "
        "FROM identities WHERE ip <> ''"
    ).fetchone()
    countries = {
        row["country"]: row["count"]
        for row in connection.execute(
            "SELECT country, COUNT(*) AS count FROM identities WHERE country <> '' "
            "GROUP BY country ORDER BY country"
        )
    }
    purposes: dict[str, dict[str, int]] = {}
    for purpose in ("sale", "rent"):
        leaf = connection.execute(
            "SELECT COUNT(*) AS shards, COALESCE(SUM(reported_count), 0) AS reported, "
            "COALESCE(SUM(observed_unique_count), 0) AS observed_sum FROM shards "
            "WHERE purpose=? AND status <> 'split'",
            (purpose,),
        ).fetchone()
        unique = connection.execute(
            "SELECT COUNT(DISTINCT listing_shards.listing_id) AS count FROM listing_shards "
            "JOIN shards USING(shard_id) WHERE shards.purpose=?",
            (purpose,),
        ).fetchone()
        purposes[purpose] = {
            "terminal_shards": int(leaf["shards"]),
            "reported_listing_sum": int(leaf["reported"]),
            "observed_shard_listing_sum": int(leaf["observed_sum"]),
            "unique_listings": int(unique["count"]),
        }
    shard_count = sum(statuses.values())
    unresolved = sum(
        statuses.get(status, 0)
        for status in (
            "plan_pending",
            "plan_error",
            "unresolved",
            "collect_error",
            "count_mismatch",
            "capped",
        )
    )
    remaining = sum(statuses.get(status, 0) for status in _COLLECTABLE_SHARD_STATUSES)
    global_unique = int(
        connection.execute("SELECT COUNT(*) AS count FROM listings").fetchone()["count"]
    )
    observed_cards = int(attempts["cards"])
    root_coverage = {
        row["root_name"]: {
            "reported_count": row["reported_count"],
            "unique_listings": row["observed"],
            "missing_from_reported_count": (
                max(0, row["reported_count"] - row["observed"])
                if row["reported_count"] is not None
                else None
            ),
        }
        for row in connection.execute(
            "SELECT root.root_name, root.reported_count, "
            "COUNT(DISTINCT ls.listing_id) AS observed FROM shards root "
            "LEFT JOIN shards child ON child.root_name=root.root_name "
            "LEFT JOIN listing_shards ls ON ls.shard_id=child.shard_id "
            "WHERE root.parent_id IS NULL GROUP BY root.shard_id"
        )
    }
    count_shortfall = any(row["missing_from_reported_count"] != 0 for row in root_coverage.values())
    tolerated = statuses.get("complete_with_tolerance", 0) > 0
    if count_shortfall:
        unresolved = max(unresolved, 1)
    if set(statuses) - {"split", "complete", "complete_with_tolerance", "ready", "collecting"}:
        unresolved = max(unresolved, 1)
    request_bytes = connection.execute(
        "SELECT COALESCE(SUM(json_extract(network_json, '$.request_bytes')), 0) FROM page_attempts"
    ).fetchone()[0]
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "shard_statuses": statuses,
        "terminal_shards": int(terminal["count"]),
        "terminal_reported_listing_sum": int(terminal["reported"]),
        "terminal_observed_listing_sum": int(terminal["observed"]),
        "global_unique_listings": global_unique,
        "page_attempts": int(attempts["count"]),
        "page_attempt_outcomes": outcomes,
        "mean_page_attempt_latency_ms": round(float(attempts["mean_latency"]), 3),
        "network_request_count": int(attempts["requests"]),
        "network_response_megabytes": round(int(attempts["bytes"]) / 1_000_000, 3),
        "network_request_megabytes": round(request_bytes / 1_000_000, 6),
        "measured_response_bytes_per_listing": (
            round(int(attempts["bytes"]) / global_unique, 1) if global_unique else None
        ),
        "projected_response_gb_per_250k_listings": (
            round(int(attempts["bytes"]) / global_unique * 250_000 / 1_000_000_000, 3)
            if global_unique
            else None
        ),
        "bandwidth_note": (
            "Measured browser requests only; excludes identity checks and unmeasured "
            "partial/failed transfers. Use the provider dashboard for billed traffic."
        ),
        "root_coverage": root_coverage,
        "coverage_basis": "Observed listing IDs reconciled against planning-time counts",
        "observed_cards": observed_cards,
        "card_duplicate_rate_estimate": (
            round(max(0, observed_cards - global_unique) / observed_cards, 6)
            if observed_cards
            else None
        ),
        "identity_samples": int(identities["samples"]),
        "unique_observed_ips": int(identities["unique_ips"]),
        "observed_countries": countries,
        "remaining_collectable_shards": remaining,
        "purposes": purposes,
        "coverage_status": (
            "not_started"
            if shard_count == 0
            else ("complete_with_tolerance" if tolerated else "complete")
            if unresolved == 0 and remaining == 0
            else "not_complete"
        ),
    }


def export_collection(connection: sqlite3.Connection, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    _export_query(
        connection,
        output / _LISTINGS_EXPORT,
        "SELECT payload_json FROM listings ORDER BY listing_id",
        lambda row: json.loads(row["payload_json"]),
    )
    _export_query(
        connection,
        output / _SHARDS_EXPORT,
        "SELECT * FROM shards ORDER BY purpose, property_type, path",
        lambda row: dict(row),
    )
    _export_query(
        connection,
        output / _ATTEMPTS_EXPORT,
        "SELECT * FROM page_attempts ORDER BY attempt_id",
        lambda row: dict(row),
    )
    summary = collection_status(connection)
    _atomic_json(output / _SUMMARY_FILE, summary)
    return summary


class BrowserPageFetcher:
    """Playwright fetcher whose proxy/session boundary is an entire browser context."""

    def __init__(
        self,
        *,
        playwright: Playwright,
        config: BayutFullCollectionConfig,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config
        self._env = env if env is not None else os.environ
        self._browser = self._launch_browser(playwright)
        self._context: BrowserContext | None = None
        self._context_id = ""
        self._context_page_count = 0
        self._identity: dict[str, Any] = {}
        self._observation_id = ""
        self._meter: NetworkMeter | None = None

    def __enter__(self) -> "BrowserPageFetcher":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self.invalidate_context()
        self._browser.close()

    def invalidate_context(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except PlaywrightError:
                pass
        self._context = None
        self._context_id = ""
        self._context_page_count = 0
        self._identity = {}

    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> FetchResult:
        requested_url = full_search_url(
            base_url=self._config.base_url,
            search_path=search_path,
            page_number=page_number,
        )
        started = time.monotonic()
        try:
            self._ensure_context()
        except Exception as error:
            identity = dict(self._identity)
            context_id = self._context_id
            error_message = self._safe_error(error)
            self.invalidate_context()
            return _failed_fetch_result(
                requested_url=requested_url,
                outcome="navigation_error",
                error=f"identity/context setup failed: {error_message}",
                latency_ms=_elapsed_ms(started),
                identity=identity,
                context_id=context_id,
            )
        if self._context is None:
            raise RuntimeError("browser context creation failed")
        page = self._context.new_page()
        meter = NetworkMeter()
        self._meter = meter
        page.on("request", lambda request: meter.on_request(request))
        page.on("requestfinished", lambda request: meter.on_finished(request))
        page.on("requestfailed", lambda request: meter.on_failed(request))
        try:
            self._observation_id = observation_id
            response = page.goto(
                requested_url,
                wait_until="domcontentloaded",
                timeout=int(self._config.timeout_seconds * 1000),
            )
            if self._config.resource_mode == "browser" and self._config.settle_milliseconds:
                page.wait_for_timeout(self._config.settle_milliseconds)
            html = page.content()
            final_url = page.url
            status_code = response.status if response is not None else 0
            cards = tuple(_listing_cards(page))
            anchors = tuple(
                page.locator("a[href]").evaluate_all(
                    "anchors => anchors.map(anchor => ({"
                    "href: anchor.href, text: (anchor.innerText || anchor.textContent || '').trim()"
                    "}))"
                )
            )
            outcome = _transport_outcome(
                final_url=final_url,
                html=html,
                status_code=status_code,
            )
            if outcome == "ok":
                outcome = _validate_search_page(
                    requested_url=requested_url,
                    final_url=final_url,
                    cards=cards,
                    body_text=page.locator("body").inner_text(),
                    title=page.title(),
                )
            return FetchResult(
                requested_url=requested_url,
                final_url=final_url,
                status_code=status_code,
                title=page.title(),
                html=html,
                cards=cards,
                location_anchors=anchors,
                outcome=outcome,
                error="",
                latency_ms=_elapsed_ms(started),
                network=meter.as_dict(),
                identity=dict(self._identity),
                context_id=self._context_id,
            )
        except PlaywrightError as error:
            return _failed_fetch_result(
                requested_url=requested_url,
                outcome="navigation_error",
                error=self._safe_error(error),
                latency_ms=_elapsed_ms(started),
                network=meter.as_dict(),
                identity=self._identity,
                context_id=self._context_id,
            )
        finally:
            self._context_page_count += 1
            try:
                page.close()
            except PlaywrightError:
                pass
            self._meter = None

    def _launch_browser(self, playwright: Playwright) -> Browser:
        browser_type = getattr(playwright, self._config.browser)
        kwargs: dict[str, Any] = {"headless": self._config.headless}
        if self._config.chrome_path:
            kwargs["executable_path"] = self._config.chrome_path
        return browser_type.launch(**kwargs)

    def _ensure_context(self) -> None:
        if self._context is not None and self._context_page_count < self._config.pages_per_context:
            return
        self.invalidate_context()
        self._context_id = uuid.uuid4().hex[:16]
        kwargs: dict[str, Any] = {
            "service_workers": "block",
            "java_script_enabled": self._config.resource_mode != "document",
        }
        proxy = _proxy_settings(
            config=self._config,
            session_id=self._context_id,
            env=self._env,
        )
        if proxy:
            kwargs["proxy"] = proxy
        if self._config.storage_state_path:
            kwargs["storage_state"] = self._config.storage_state_path
        self._context = self._browser.new_context(**kwargs)
        if (
            self._config.resource_mode == "document"
            or self._config.block_media_requests
            or self._config.correlation_header_name
        ):
            self._context.route(
                "**/*",
                self._route_request,
            )
        if self._config.identity_url:
            self._identity = _check_identity(
                context=self._context,
                url=self._config.identity_url,
                timeout_seconds=self._config.timeout_seconds,
                context_id=self._context_id,
            )
            if self._identity.get("error"):
                self._identity["error"] = self._safe_error(self._identity["error"])
            if self._config.require_identity_success:
                validate_identity_result(
                    self._identity,
                    expected_country=self._config.expected_country,
                )

    def _safe_error(self, error: object) -> str:
        message = str(error)
        for key in (_PROXY_USERNAME_ENV, _PROXY_PASSWORD_ENV):
            value = self._env.get(key, "").replace(_SESSION_PLACEHOLDER, self._context_id)
            if value:
                message = message.replace(value, "[redacted]")
        return re.sub(r"(https?|socks5)://[^/\s@]+@", r"\1://[redacted]@", message)

    def _route_request(self, route: Route) -> None:
        request = route.request
        if self._config.resource_mode == "document" and (
            request.resource_type != "document" or request.frame.parent_frame is not None
        ):
            if self._meter is not None:
                self._meter.blocked[request.resource_type] += 1
            route.abort()
            return
        if (
            self._config.block_media_requests
            and route.request.resource_type in _BLOCKED_RESOURCE_TYPES
        ):
            if self._meter is not None:
                self._meter.blocked[request.resource_type] += 1
            route.abort()
            return
        if (
            self._config.correlation_header_name
            and urlsplit(route.request.url).netloc.lower()
            == urlsplit(self._config.base_url).netloc.lower()
        ):
            route.continue_(
                headers={
                    **route.request.headers,
                    self._config.correlation_header_name: self._observation_id,
                }
            )
            return
        route.continue_()


def _fetch_with_retries(
    *,
    connection: sqlite3.Connection,
    config: BayutFullCollectionConfig,
    fetcher: FullPageFetcher,
    phase: str,
    shard: sqlite3.Row,
    page_number: int,
) -> FetchResult | None:
    last: FetchResult | None = None
    for attempt in range(1, config.max_attempts_per_page + 1):
        observation_id = f"{phase}-{shard['shard_id']}-{page_number}-{uuid.uuid4().hex[:8]}"
        result = fetcher.fetch(
            search_path=shard["path"],
            page_number=page_number,
            observation_id=observation_id,
        )
        # Apply cadence to every fetch, including planner leaves and failed attempts.
        _pause(config, observation_id)
        last = result
        evidence_path = _write_evidence(
            connection=connection,
            config=config,
            phase=phase,
            shard=shard,
            page_number=page_number,
            attempt=attempt,
            result=result,
        )
        _record_attempt(
            connection=connection,
            phase=phase,
            shard=shard,
            page_number=page_number,
            attempt=attempt,
            observation_id=observation_id,
            result=result,
            evidence_path=evidence_path,
        )
        if result.outcome == "ok":
            return result
        if result.outcome not in _RETRYABLE_OUTCOMES:
            return result
        fetcher.invalidate_context()
        if attempt < config.max_attempts_per_page and config.retry_backoff_seconds:
            time.sleep(config.retry_backoff_seconds * attempt)
    return last


def _record_attempt(
    *,
    connection: sqlite3.Connection,
    phase: str,
    shard: sqlite3.Row,
    page_number: int,
    attempt: int,
    observation_id: str,
    result: FetchResult,
    evidence_path: str,
) -> None:
    network = result.network
    identity = result.identity
    with connection:
        connection.execute(
            """
            INSERT INTO page_attempts(
                observed_at, phase, shard_id, page_number, attempt_number, observation_id,
                requested_url, final_url, status_code, outcome, error, latency_ms, card_count,
                request_count, response_bytes, html_sha256, evidence_path, context_id,
                identity_ip, identity_country, identity_asn, network_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                phase,
                shard["shard_id"],
                page_number,
                attempt,
                observation_id,
                result.requested_url,
                result.final_url,
                result.status_code,
                result.outcome,
                result.error,
                result.latency_ms,
                len(result.cards),
                int(network.get("request_count") or 0),
                int(network.get("response_bytes") or 0),
                hashlib.sha256(result.html.encode()).hexdigest() if result.html else "",
                evidence_path,
                result.context_id,
                str(identity.get("ip") or ""),
                str(identity.get("country") or ""),
                str(identity.get("asn") or ""),
                json.dumps(network, separators=(",", ":"), sort_keys=True),
            ),
        )
        if identity.get("sample_id"):
            connection.execute(
                "INSERT OR IGNORE INTO identities(sample_id, observed_at, context_id, ip, "
                "country, asn, org, error) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identity["sample_id"],
                    identity.get("observed_at") or _now(),
                    result.context_id,
                    identity.get("ip") or "",
                    identity.get("country") or "",
                    identity.get("asn") or "",
                    identity.get("org") or "",
                    identity.get("error") or "",
                ),
            )


def _write_evidence(
    *,
    connection: sqlite3.Connection,
    config: BayutFullCollectionConfig,
    phase: str,
    shard: sqlite3.Row,
    page_number: int,
    attempt: int,
    result: FetchResult,
) -> str:
    if not result.html:
        return ""
    if config.evidence == "none":
        return ""
    if config.evidence == "challenge" and result.outcome == "ok":
        return ""
    database_path = Path(connection.execute("PRAGMA database_list").fetchone()["file"])
    evidence_dir = database_path.parent / "evidence" / phase
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_id = uuid.uuid4().hex[:8]
    path = evidence_dir / (
        f"{shard['shard_id']}-p{page_number:04d}-a{attempt}-{evidence_id}.html.gz"
    )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(result.html)
    return str(path.relative_to(database_path.parent))


def _check_identity(
    *,
    context: BrowserContext,
    url: str,
    timeout_seconds: float,
    context_id: str,
) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "sample_id": uuid.uuid4().hex,
        "observed_at": _now(),
        "context_id": context_id,
        "ip": "",
        "country": "",
        "asn": "",
        "org": "",
        "error": "",
    }
    try:
        response = context.request.get(url, timeout=int(timeout_seconds * 1000))
        if not response.ok:
            sample["error"] = f"identity endpoint returned HTTP {response.status}"
            return sample
        payload = response.json()
        if not isinstance(payload, Mapping):
            sample["error"] = "identity endpoint did not return a JSON object"
            return sample
        sample.update(parse_identity_payload(payload))
    except Exception as error:
        sample["error"] = str(error)
    return sample


def _proxy_settings(
    *,
    config: BayutFullCollectionConfig,
    session_id: str,
    env: Mapping[str, str],
) -> dict[str, str] | None:
    if config.proxy == "direct":
        return None
    values = {
        "server": env.get(_PROXY_SERVER_ENV, ""),
        "username": env.get(_PROXY_USERNAME_ENV, ""),
        "password": env.get(_PROXY_PASSWORD_ENV, ""),
    }
    if config.proxy_rotation == "context":
        values = {
            key: value.replace(_SESSION_PLACEHOLDER, session_id) for key, value in values.items()
        }
    return {key: value for key, value in values.items() if value}


def _terminal_collection_status(
    *,
    observed_count: int,
    reported_count: int | None,
    minimum_coverage: float,
    natural_reason: str,
) -> tuple[str, str]:
    if reported_count is None:
        return "count_mismatch", f"{natural_reason};missing_reported_count"
    if reported_count and observed_count / reported_count < minimum_coverage:
        return (
            "count_mismatch",
            f"{natural_reason};observed_coverage={observed_count / reported_count:.6f}",
        )
    if observed_count < reported_count:
        return "complete_with_tolerance", natural_reason
    return "complete", natural_reason


def _transport_outcome(*, final_url: str, html: str, status_code: int) -> str:
    if _is_captcha_page(final_url=final_url, html=html):
        return "captcha"
    if status_code == 403:
        return "forbidden"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 400 or status_code == 0:
        return "http_error"
    return "ok"


def _failed_fetch_result(
    *,
    requested_url: str,
    outcome: str,
    error: str,
    latency_ms: int,
    network: Mapping[str, Any] | None = None,
    identity: Mapping[str, Any] | None = None,
    context_id: str = "",
) -> FetchResult:
    return FetchResult(
        requested_url=requested_url,
        final_url="",
        status_code=0,
        title="",
        html="",
        cards=(),
        location_anchors=(),
        outcome=outcome,
        error=error,
        latency_ms=latency_ms,
        network=dict(network or {}),
        identity=dict(identity or {}),
        context_id=context_id,
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shards (
            shard_id TEXT PRIMARY KEY,
            root_name TEXT NOT NULL,
            purpose TEXT NOT NULL,
            property_type TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            parent_id TEXT REFERENCES shards(shard_id),
            depth INTEGER NOT NULL,
            name TEXT NOT NULL,
            reported_count INTEGER,
            child_count INTEGER NOT NULL DEFAULT 0,
            child_reported_total INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            next_page INTEGER NOT NULL DEFAULT 1,
            observed_unique_count INTEGER NOT NULL DEFAULT 0,
            stop_reason TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS shards_status_idx ON shards(status, depth, path);
        CREATE TABLE IF NOT EXISTS listings (
            listing_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS listing_shards (
            listing_id TEXT NOT NULL REFERENCES listings(listing_id),
            shard_id TEXT NOT NULL REFERENCES shards(shard_id),
            first_page INTEGER NOT NULL,
            PRIMARY KEY(listing_id, shard_id)
        );
        CREATE INDEX IF NOT EXISTS listing_shards_shard_idx ON listing_shards(shard_id);
        CREATE TABLE IF NOT EXISTS page_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            phase TEXT NOT NULL,
            shard_id TEXT NOT NULL REFERENCES shards(shard_id),
            page_number INTEGER NOT NULL,
            attempt_number INTEGER NOT NULL,
            observation_id TEXT NOT NULL,
            requested_url TEXT NOT NULL,
            final_url TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            outcome TEXT NOT NULL,
            error TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            card_count INTEGER NOT NULL,
            request_count INTEGER NOT NULL,
            response_bytes INTEGER NOT NULL,
            html_sha256 TEXT NOT NULL,
            evidence_path TEXT NOT NULL,
            context_id TEXT NOT NULL,
            identity_ip TEXT NOT NULL,
            identity_country TEXT NOT NULL,
            identity_asn TEXT NOT NULL,
            network_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS identities (
            sample_id TEXT PRIMARY KEY,
            observed_at TEXT NOT NULL,
            context_id TEXT NOT NULL,
            ip TEXT NOT NULL,
            country TEXT NOT NULL,
            asn TEXT NOT NULL,
            org TEXT NOT NULL,
            error TEXT NOT NULL
        );
        """
    )
    # Existing checkpoints remain readable after adding request-level metrics.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(page_attempts)")}
    if "network_json" not in columns:
        connection.execute(
            "ALTER TABLE page_attempts ADD COLUMN network_json TEXT NOT NULL DEFAULT '{}'"
        )


def _update_shard_status(
    connection: sqlite3.Connection, shard_identifier: str, status: str, stop_reason: str
) -> None:
    with connection:
        connection.execute(
            "UPDATE shards SET status=?, stop_reason=?, updated_at=? WHERE shard_id=?",
            (status, stop_reason, _now(), shard_identifier),
        )


def _pause(config: BayutFullCollectionConfig, seed: str) -> None:
    if not config.request_pause_seconds and not config.request_jitter_seconds:
        return
    jitter = random.Random(f"{config.random_seed}:{seed}").uniform(0, config.request_jitter_seconds)
    time.sleep(config.request_pause_seconds + jitter)


def _export_query(
    connection: sqlite3.Connection,
    path: Path,
    query: str,
    transform: Any,
) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in connection.execute(query):
            handle.write(json.dumps(transform(row), separators=(",", ":"), sort_keys=True) + "\n")
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def database_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / _DB_FILE


__all__ = [
    "BAYUT_RESIDENTIAL_ROOTS",
    "BayutFullCollectionConfig",
    "BayutFullRoot",
    "BrowserPageFetcher",
    "FetchResult",
    "FullPageFetcher",
    "LocationLink",
    "canonical_search_path",
    "collect_shards",
    "collection_status",
    "database_path",
    "export_collection",
    "extract_reported_count",
    "full_search_url",
    "initialize_roots",
    "load_full_collection_config",
    "normalize_location_links",
    "open_collection_database",
    "plan_collection",
    "reset_retryable_errors",
    "sanitized_full_config",
    "shard_id",
    "validate_full_proxy_environment",
]
