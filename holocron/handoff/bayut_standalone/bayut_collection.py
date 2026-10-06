"""Standalone, resumable Bayut search-card collection.

Only Playwright is required outside the Python standard library.  This module
does not import Holocron or any other repository package.
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
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Playwright,
    Request,
    Route,
)

BAYUT_BASE_URL = "https://www.bayut.com"
PROXY_SERVER_ENV = "BAYUT_PROXY_SERVER"
PROXY_USERNAME_ENV = "BAYUT_PROXY_USERNAME"
PROXY_PASSWORD_ENV = "BAYUT_PROXY_PASSWORD"
SESSION_PLACEHOLDER = "{session}"

DB_FILE = "collection.sqlite3"
CONFIG_FILE = "config.sanitized.json"
SUMMARY_FILE = "summary.json"
LISTINGS_EXPORT = "listings.jsonl"
SHARDS_EXPORT = "shards.jsonl"
ATTEMPTS_EXPORT = "page_attempts.jsonl"

DETAIL_URL_RE = re.compile(r"/property/details-(?P<listing_id>\d+)\.html", re.IGNORECASE)
PRICE_RE = re.compile(r"AED\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
SIZE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*sq\.?\s*ft", re.IGNORECASE)
CAPTCHA_MARKERS = ("captchachallenge", "hcaptcha", "captcha challenge", "security check | bayut")
BLOCKED_RESOURCE_TYPES = frozenset({"font", "image", "media"})
COUNT_SUFFIX_RE = re.compile(r"\(\s*(?P<count>[\d,]+)\s*\)\s*$")
TITLE_COUNT_RE = re.compile(r"^\s*(?P<count>[\d,]+)\s+\S")
PAGE_SEGMENT_RE = re.compile(r"page-\d+", re.IGNORECASE)
RETRYABLE_OUTCOMES = frozenset(
    {"captcha", "forbidden", "rate_limited", "http_error", "navigation_error"}
)
COLLECTABLE_SHARD_STATUSES = ("ready", "collecting")


@dataclass(frozen=True, slots=True)
class SearchRoot:
    name: str
    purpose: Literal["sale", "rent"]
    property_type: str
    path: str


RESIDENTIAL_ROOTS = (
    SearchRoot("sale_apartments", "sale", "apartment", "/for-sale/apartments/dubai/"),
    SearchRoot("sale_villas", "sale", "villa", "/for-sale/villas/dubai/"),
    SearchRoot("sale_townhouses", "sale", "townhouse", "/for-sale/townhouses/dubai/"),
    SearchRoot("sale_penthouses", "sale", "penthouse", "/for-sale/penthouse/dubai/"),
    SearchRoot(
        "sale_hotel_apartments",
        "sale",
        "hotel_apartment",
        "/for-sale/hotel-apartments/dubai/",
    ),
    SearchRoot(
        "sale_residential_plots",
        "sale",
        "residential_plot",
        "/for-sale/residential-plots/dubai/",
    ),
    SearchRoot(
        "sale_residential_buildings",
        "sale",
        "residential_building",
        "/for-sale/residential-building/dubai/",
    ),
    SearchRoot(
        "sale_villa_compounds",
        "sale",
        "villa_compound",
        "/for-sale/villa-compound/dubai/",
    ),
    SearchRoot(
        "sale_residential_floors",
        "sale",
        "residential_floor",
        "/for-sale/residential-floors/dubai/",
    ),
    SearchRoot("rent_apartments", "rent", "apartment", "/to-rent/apartments/dubai/"),
    SearchRoot("rent_villas", "rent", "villa", "/to-rent/villas/dubai/"),
    SearchRoot("rent_townhouses", "rent", "townhouse", "/to-rent/townhouses/dubai/"),
    SearchRoot(
        "rent_hotel_apartments",
        "rent",
        "hotel_apartment",
        "/to-rent/hotel-apartments/dubai/",
    ),
    SearchRoot("rent_penthouses", "rent", "penthouse", "/to-rent/penthouse/dubai/"),
    SearchRoot(
        "rent_villa_compounds",
        "rent",
        "villa_compound",
        "/to-rent/villa-compound/dubai/",
    ),
    SearchRoot(
        "rent_residential_buildings",
        "rent",
        "residential_building",
        "/to-rent/residential-building/dubai/",
    ),
)

PRACTICE_ROOTS = (
    SearchRoot("practice_sale", "sale", "property", "/for-sale/property/dubai/"),
    SearchRoot("practice_rent", "rent", "property", "/to-rent/property/dubai/"),
)


@dataclass(frozen=True, slots=True)
class CollectionConfig:
    base_url: str = BAYUT_BASE_URL
    roots: tuple[SearchRoot, ...] = RESIDENTIAL_ROOTS
    practice_pages_per_root: int = 3
    max_results_per_shard: int = 1_200
    max_pages_per_shard: int = 100
    minimum_expected_cards_per_page: int = 12
    max_location_depth: int = 6
    minimum_child_count_coverage: float = 1.0
    maximum_child_count_coverage: float = 1.05
    minimum_observed_count_coverage: float = 1.0
    timeout_seconds: float = 60
    settle_milliseconds: int = 750
    request_pause_seconds: float = 2
    request_jitter_seconds: float = 1
    headless: bool = True
    browser: Literal["chromium", "firefox", "webkit"] = "chromium"
    chrome_path: str = ""
    storage_state_path: str = ""
    block_media_requests: bool = True
    resource_mode: Literal["browser", "document"] = "browser"
    proxy: Literal["direct", "residential"] = "direct"
    proxy_rotation: Literal["provider_default", "context"] = "provider_default"
    pages_per_context: int = 1
    identity_url: str = ""
    expected_country: str = ""
    require_identity_success: bool = True
    correlation_header_name: str = ""
    max_attempts_per_page: int = 3
    max_consecutive_failed_pages: int = 3
    retry_backoff_seconds: float = 5
    evidence: Literal["none", "challenge", "all"] = "challenge"
    random_seed: int = 20260901

    @classmethod
    def from_json(cls, path: str | Path) -> "CollectionConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, value: Any) -> "CollectionConfig":
        payload = dict(value) if isinstance(value, Mapping) else value
        if not isinstance(payload, dict):
            raise ValueError("configuration must be a JSON object")
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"unknown configuration fields: {', '.join(unknown)}")
        roots_payload = payload.pop("roots", None)
        if roots_payload is not None:
            if not isinstance(roots_payload, list):
                raise ValueError("roots must be a JSON array")
            payload["roots"] = tuple(_root_from_payload(item) for item in roots_payload)
        config = cls(**payload)
        config.validate()
        return config

    def validate(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url cannot be blank")
        if not self.roots:
            raise ValueError("roots must contain at least one search root")
        if len({root.name for root in self.roots}) != len(self.roots):
            raise ValueError("root names must be unique")
        paths = [canonical_search_path(root.path) for root in self.roots]
        if len(set(paths)) != len(paths):
            raise ValueError("root paths must be unique")
        for root in self.roots:
            if root.purpose not in {"sale", "rent"}:
                raise ValueError(f"invalid root purpose: {root.purpose}")
            if not root.name.strip() or not root.property_type.strip():
                raise ValueError("root names and property types cannot be blank")
        _bounded_int("practice_pages_per_root", self.practice_pages_per_root, 1, 500)
        _bounded_int("max_results_per_shard", self.max_results_per_shard, 100, 15_000)
        _bounded_int("max_pages_per_shard", self.max_pages_per_shard, 1, 500)
        _bounded_int(
            "minimum_expected_cards_per_page", self.minimum_expected_cards_per_page, 1, 100
        )
        _bounded_int("max_location_depth", self.max_location_depth, 1, 12)
        _bounded_int("settle_milliseconds", self.settle_milliseconds, 0, 30_000)
        _bounded_int("pages_per_context", self.pages_per_context, 1, 100)
        _bounded_int("max_attempts_per_page", self.max_attempts_per_page, 1, 10)
        _bounded_int("max_consecutive_failed_pages", self.max_consecutive_failed_pages, 1, 100)
        _bounded_float("minimum_child_count_coverage", self.minimum_child_count_coverage, 0.8, 1.05)
        _bounded_float(
            "maximum_child_count_coverage", self.maximum_child_count_coverage, 0.95, 1.25
        )
        _bounded_float(
            "minimum_observed_count_coverage", self.minimum_observed_count_coverage, 0.5, 1.05
        )
        _bounded_float("timeout_seconds", self.timeout_seconds, 1, 300)
        _bounded_float("request_pause_seconds", self.request_pause_seconds, 0, 300)
        _bounded_float("request_jitter_seconds", self.request_jitter_seconds, 0, 300)
        _bounded_float("retry_backoff_seconds", self.retry_backoff_seconds, 0, 300)
        if self.browser not in {"chromium", "firefox", "webkit"}:
            raise ValueError(f"unsupported browser: {self.browser}")
        if self.resource_mode not in {"browser", "document"}:
            raise ValueError(f"unsupported resource mode: {self.resource_mode}")
        if self.chrome_path and self.browser != "chromium":
            raise ValueError("chrome_path is only valid with browser=chromium")
        if self.proxy not in {"direct", "residential"}:
            raise ValueError(f"unsupported proxy mode: {self.proxy}")
        if self.proxy_rotation not in {"provider_default", "context"}:
            raise ValueError(f"unsupported proxy rotation: {self.proxy_rotation}")
        if self.proxy == "direct" and self.proxy_rotation != "provider_default":
            raise ValueError("direct runs must use proxy_rotation=provider_default")
        if self.proxy == "residential" and self.require_identity_success:
            if not self.identity_url:
                raise ValueError("identity_url is required for residential collection")
            if "REPLACE-" in self.identity_url.upper():
                raise ValueError("replace the identity_url placeholder before running")
        if self.evidence not in {"none", "challenge", "all"}:
            raise ValueError(f"unsupported evidence mode: {self.evidence}")
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
                "max_results_per_shard exceeds conservative page capacity; "
                "increase max_pages_per_shard or lower the shard size"
            )


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


class PageFetcher(Protocol):
    def fetch(self, *, search_path: str, page_number: int, observation_id: str) -> FetchResult: ...

    def invalidate_context(self) -> None: ...


@dataclass(slots=True)
class NetworkMeter:
    requested: Counter[str]
    finished: Counter[str]
    failed: Counter[str]
    blocked: Counter[str]
    request_bytes: int = 0
    response_bytes: int = 0

    @classmethod
    def create(cls) -> "NetworkMeter":
        return cls(requested=Counter(), finished=Counter(), failed=Counter(), blocked=Counter())

    def on_request(self, request: Request) -> None:
        self.requested[request.resource_type] += 1

    def on_finished(self, request: Request) -> None:
        self.finished[request.resource_type] += 1
        try:
            sizes = request.sizes()
        except PlaywrightError:
            return
        self.request_bytes += int(sizes.get("requestHeadersSize", 0)) + int(
            sizes.get("requestBodySize", 0)
        )
        self.response_bytes += int(sizes.get("responseHeadersSize", 0)) + int(
            sizes.get("responseBodySize", 0)
        )

    def on_failed(self, request: Request) -> None:
        self.failed[request.resource_type] += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_count": sum(self.requested.values()),
            "finished_count": sum(self.finished.values()),
            "failed_count": sum(self.failed.values()),
            "blocked_count": sum(self.blocked.values()),
            "request_bytes": self.request_bytes,
            "response_bytes": self.response_bytes,
            "unfinished_count": max(
                0,
                sum(self.requested.values())
                - sum(self.finished.values())
                - sum(self.failed.values()),
            ),
            "requested_by_type": dict(sorted(self.requested.items())),
            "failed_by_type": dict(sorted(self.failed.items())),
            "blocked_by_type": dict(sorted(self.blocked.items())),
        }


def _root_from_payload(value: Any) -> SearchRoot:
    if not isinstance(value, dict):
        raise ValueError("every root must be a JSON object")
    required = {"name", "purpose", "property_type", "path"}
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise ValueError(f"root is missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"root has unknown fields: {', '.join(unknown)}")
    return SearchRoot(
        name=str(value["name"]),
        purpose=cast(Literal["sale", "rent"], str(value["purpose"])),
        property_type=str(value["property_type"]),
        path=str(value["path"]),
    )


def _bounded_int(name: str, value: Any, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} through {maximum}")


def _bounded_float(name: str, value: Any, minimum: float, maximum: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number from {minimum} through {maximum}")
    if not minimum <= float(value) <= maximum:
        raise ValueError(f"{name} must be a number from {minimum} through {maximum}")


def canonical_search_path(path: str) -> str:
    parts = urlsplit(path)
    stripped = parts.path.strip("/")
    value = f"/{stripped}/" if stripped else "/"
    if PAGE_SEGMENT_RE.fullmatch(value.rstrip("/").rsplit("/", 1)[-1]):
        raise ValueError(f"search path must not contain a page cursor: {path}")
    return urlunsplit(("", "", value, parts.query, ""))


def search_url(*, base_url: str, search_path: str, page_number: int) -> str:
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
    current = urlsplit(canonical_search_path(current_path))
    current_segments = tuple(segment for segment in current.path.split("/") if segment)
    base_host = urlsplit(base_url).netloc.lower()
    links: dict[str, LocationLink] = {}
    for anchor in anchors:
        href = str(anchor.get("href") or "").strip()
        text = " ".join(str(anchor.get("text") or "").split())
        match = COUNT_SUFFIX_RE.search(text)
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
        if PAGE_SEGMENT_RE.fullmatch(segments[-1]):
            continue
        path = f"/{'/'.join(segments)}/"
        links[path] = LocationLink(
            path=path,
            name=text[: match.start()].strip() or segments[-1],
            count=int(match.group("count").replace(",", "")),
        )
    return tuple(sorted(links.values(), key=lambda link: link.path))


def extract_reported_count(*, title: str, html: str) -> int | None:
    match = TITLE_COUNT_RE.search(title)
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


def shard_id(path: str) -> str:
    return hashlib.sha256(canonical_search_path(path).encode()).hexdigest()[:20]


def sanitized_config(config: CollectionConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["proxy_environment"] = {
        "server": PROXY_SERVER_ENV,
        "username": PROXY_USERNAME_ENV,
        "password": PROXY_PASSWORD_ENV,
    }
    payload["credentials_recorded"] = False
    return payload


def validate_proxy_environment(
    config: CollectionConfig, env: Mapping[str, str] | None = None
) -> None:
    values = env if env is not None else os.environ
    if config.proxy == "direct":
        return
    server = values.get(PROXY_SERVER_ENV, "").strip()
    if not server:
        raise ValueError(f"{PROXY_SERVER_ENV} is required for residential collection")
    templates = (
        server,
        values.get(PROXY_USERNAME_ENV, ""),
        values.get(PROXY_PASSWORD_ENV, ""),
    )
    if config.proxy_rotation == "context" and not any(
        SESSION_PLACEHOLDER in value for value in templates
    ):
        raise ValueError(
            "context proxy rotation requires {session} in the proxy server, username, "
            "or password environment value"
        )


def open_database(
    *,
    config: CollectionConfig,
    output_dir: str | Path,
    requested_kind: Literal["practice", "full"] | None,
) -> sqlite3.Connection:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output / DB_FILE, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    _create_schema(connection)

    serialized = json.dumps(sanitized_config(config), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    existing_digest = _metadata_value(connection, "config_sha256")
    legacy_payload = sanitized_config(config)
    legacy_payload.pop("resource_mode")
    legacy_payload.pop("max_consecutive_failed_pages")
    legacy_digest = hashlib.sha256(
        json.dumps(legacy_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    compatible_legacy = (
        config.resource_mode == "browser"
        and config.max_consecutive_failed_pages == 3
        and existing_digest == legacy_digest
    )
    if existing_digest is not None and existing_digest != digest and not compatible_legacy:
        connection.close()
        raise ValueError(
            "existing collection database was created with a different config; "
            "use its original config or a new output directory"
        )
    existing_kind = _metadata_value(connection, "run_kind")
    run_kind = requested_kind or existing_kind or "full"
    if existing_kind is not None and requested_kind is not None and existing_kind != requested_kind:
        connection.close()
        raise ValueError(
            f"output directory contains a {existing_kind} run, not a {requested_kind} run"
        )
    with connection:
        connection.execute(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES('schema_version', '1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES('config_sha256', ?)", (digest,)
        )
        connection.execute(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES('run_kind', ?)", (run_kind,)
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('updated_at', ?)", (_now(),)
        )
    (output / CONFIG_FILE).write_text(
        json.dumps(sanitized_config(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return connection


def initialize_full_roots(connection: sqlite3.Connection, config: CollectionConfig) -> None:
    _initialize_roots(connection, config.roots, status="plan_pending")


def initialize_practice_roots(connection: sqlite3.Connection, config: CollectionConfig) -> None:
    _initialize_roots(connection, config.roots, status="practice_ready")


def _initialize_roots(
    connection: sqlite3.Connection,
    roots: Sequence[SearchRoot],
    *,
    status: str,
) -> None:
    with connection:
        for root in roots:
            path = canonical_search_path(root.path)
            connection.execute(
                """
                INSERT OR IGNORE INTO shards(
                    shard_id, root_name, purpose, property_type, path, parent_id, depth,
                    name, reported_count, status, next_page, updated_at
                ) VALUES(?, ?, ?, ?, ?, NULL, 0, ?, NULL, ?, 1, ?)
                """,
                (
                    shard_id(path),
                    root.name,
                    root.purpose,
                    root.property_type,
                    path,
                    root.name,
                    status,
                    _now(),
                ),
            )


def plan_collection(
    *,
    connection: sqlite3.Connection,
    config: CollectionConfig,
    fetcher: PageFetcher,
    max_nodes: int = 0,
) -> dict[str, Any]:
    initialize_full_roots(connection, config)
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


def run_practice(
    *,
    connection: sqlite3.Connection,
    config: CollectionConfig,
    fetcher: PageFetcher,
    round_robin: bool = False,
) -> dict[str, Any]:
    """Collect a small fixed number of pages from each configured sale/rent root."""

    initialize_practice_roots(connection, config)
    consecutive_failures = 0
    ordering = "next_page, root_name" if round_robin else "purpose, path"
    while True:
        shard = connection.execute(
            "SELECT * FROM shards WHERE status IN ('practice_ready', 'practice_collecting') "
            f"ORDER BY {ordering} LIMIT 1"
        ).fetchone()
        if shard is None:
            break
        page_number = int(shard["next_page"])
        if page_number > config.practice_pages_per_root:
            _update_shard_status(
                connection,
                shard["shard_id"],
                "practice_complete",
                "practice_page_limit",
            )
            continue
        result = _fetch_with_retries(
            connection=connection,
            config=config,
            fetcher=fetcher,
            phase="practice",
            shard=shard,
            page_number=page_number,
        )
        if result is None or result.outcome != "ok":
            _update_shard_status(
                connection,
                shard["shard_id"],
                "practice_error",
                result.outcome if result is not None else "no_result",
            )
            consecutive_failures += 1
            if consecutive_failures >= config.max_consecutive_failed_pages:
                break
            continue
        consecutive_failures = 0
        rows = listing_rows(
            cards=result.cards,
            search_path=shard["path"],
            page=page_number,
            scraped_at=_now(),
        )
        prior_ids = {
            row["listing_id"]
            for row in connection.execute(
                "SELECT listing_id FROM listing_shards WHERE shard_id=?", (shard["shard_id"],)
            )
        }
        next_page = page_number + 1
        if not rows:
            status = "practice_complete"
            stop_reason = "empty_page"
        elif not ({row["listing_id"] for row in rows} - prior_ids):
            status = "practice_complete"
            stop_reason = "duplicate_only_page"
        elif next_page > config.practice_pages_per_root:
            status = "practice_complete"
            stop_reason = "practice_page_limit"
        else:
            status = "practice_collecting"
            stop_reason = ""
        with connection:
            _save_listings(connection=connection, shard=shard, page_number=page_number, rows=rows)
            _checkpoint_shard(
                connection=connection,
                shard_identifier=shard["shard_id"],
                status=status,
                next_page=next_page,
                stop_reason=stop_reason,
            )
    return collection_status(connection)


def collect_shards(
    *,
    connection: sqlite3.Connection,
    config: CollectionConfig,
    fetcher: PageFetcher,
    max_pages: int = 0,
) -> dict[str, Any]:
    blockers = connection.execute(
        "SELECT status, COUNT(*) AS count FROM shards "
        "WHERE status IN ('plan_pending', 'plan_error', 'unresolved') GROUP BY status"
    ).fetchall()
    if blockers:
        details = ", ".join(f"{row['status']}={row['count']}" for row in blockers)
        raise RuntimeError(f"coverage plan is incomplete ({details}); resolve it before collection")

    processed_pages = 0
    consecutive_failures = 0
    while not max_pages or processed_pages < max_pages:
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
        rows = listing_rows(
            cards=result.cards,
            search_path=shard["path"],
            page=page_number,
            scraped_at=_now(),
        )
        ids = {str(row["listing_id"]) for row in rows}
        prior_ids = {
            row["listing_id"]
            for row in connection.execute(
                "SELECT listing_id FROM listing_shards WHERE shard_id=?", (shard["shard_id"],)
            )
        }
        new_for_shard = ids - prior_ids
        next_page = page_number + 1
        status = "collecting"
        stop_reason = ""
        if not ids:
            status, stop_reason = _terminal_status(
                observed_count=len(prior_ids),
                reported_count=shard["reported_count"],
                minimum_coverage=config.minimum_observed_count_coverage,
                natural_reason="empty_page",
            )
        elif not new_for_shard:
            status, stop_reason = _terminal_status(
                observed_count=len(prior_ids | ids),
                reported_count=shard["reported_count"],
                minimum_coverage=config.minimum_observed_count_coverage,
                natural_reason="duplicate_only_page",
            )
        elif page_number >= config.max_pages_per_shard:
            status = "capped"
            stop_reason = "page_cap"
        with connection:
            _save_listings(connection=connection, shard=shard, page_number=page_number, rows=rows)
            _checkpoint_shard(
                connection=connection,
                shard_identifier=shard["shard_id"],
                status=status,
                next_page=next_page,
                stop_reason=stop_reason,
            )
    return collection_status(connection)


def _save_listings(
    *,
    connection: sqlite3.Connection,
    shard: sqlite3.Row,
    page_number: int,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    observed_at = _now()
    # The caller commits listings and the page cursor in one transaction.
    for listing in rows:
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
                observed_at,
                observed_at,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO listing_shards(listing_id, shard_id, first_page) "
            "VALUES(?, ?, ?)",
            (listing["listing_id"], shard["shard_id"], page_number),
        )


def _checkpoint_shard(
    *,
    connection: sqlite3.Connection,
    shard_identifier: str,
    status: str,
    next_page: int,
    stop_reason: str,
) -> None:
    connection.execute(
        "UPDATE shards SET status=?, next_page=?, observed_unique_count=("
        "SELECT COUNT(*) FROM listing_shards WHERE shard_id=?), stop_reason=?, updated_at=? "
        "WHERE shard_id=?",
        (status, next_page, shard_identifier, stop_reason, _now(), shard_identifier),
    )


def reset_retryable_errors(connection: sqlite3.Connection) -> None:
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
        connection.execute(
            "UPDATE shards SET status=CASE WHEN next_page > 1 THEN 'practice_collecting' "
            "ELSE 'practice_ready' END, stop_reason='', updated_at=? "
            "WHERE status='practice_error'",
            (_now(),),
        )


class BrowserPageFetcher:
    """Playwright fetcher whose proxy/session boundary is a complete browser context."""

    def __init__(
        self,
        *,
        playwright: Playwright,
        config: CollectionConfig,
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
        try:
            self._browser.close()
        except PlaywrightError:
            pass

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
        requested_url = search_url(
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
            return failed_fetch_result(
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
        meter = NetworkMeter.create()
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
            cards = tuple(listing_cards(page))
            anchors = tuple(
                page.locator("a[href]").evaluate_all(
                    "anchors => anchors.map(anchor => ({"
                    "href: anchor.href, text: (anchor.innerText || anchor.textContent || '').trim()"
                    "}))"
                )
            )
            outcome = transport_outcome(
                final_url=final_url,
                html=html,
                status_code=status_code,
            )
            if outcome == "ok":
                outcome = validate_search_page(
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
            return failed_fetch_result(
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
        proxy = proxy_settings(
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
            self._context.route("**/*", self._route_request)
        if self._config.identity_url:
            self._identity = check_identity(
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
        for key in (PROXY_USERNAME_ENV, PROXY_PASSWORD_ENV):
            value = self._env.get(key, "").replace(SESSION_PLACEHOLDER, self._context_id)
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
            and route.request.resource_type in BLOCKED_RESOURCE_TYPES
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


def listing_cards(page: Any) -> list[dict[str, str]]:
    return page.locator("article").evaluate_all(
        r"""articles => articles.map((article) => {
            if (article.closest('[aria-label="Off-Plan properties rail"], '
                + '[aria-label="Off plan list"]')) return null;
            const link = [...article.querySelectorAll('a[href]')]
                .find((anchor) => /\/property\/details-\d+\.html/i.test(anchor.href));
            if (!link) return null;
            const heading = article.querySelector('[aria-label="Title"]')
                || article.querySelector('h2, h1');
            return {
                listing_url: link.href.split('?')[0],
                title: (heading?.textContent || link.getAttribute('title') || '').trim(),
                text: (article.innerText || '').trim(),
            };
        }).filter(Boolean)"""
    )


def listing_rows(
    *,
    cards: Sequence[Mapping[str, str]],
    search_path: str,
    page: int,
    scraped_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, card in enumerate(cards):
        listing_url = str(card.get("listing_url") or "")
        match = DETAIL_URL_RE.search(listing_url)
        if not match:
            continue
        text = str(card.get("text") or "")
        listing_id = match.group("listing_id")
        rows.append(
            {
                "listing_id": listing_id,
                "property_key": f"bayut:{listing_id}",
                "scraped_at": scraped_at,
                "search_path": search_path,
                "page": page,
                "card_index": index,
                "listing_url": listing_url,
                "title": str(card.get("title") or ""),
                "price_aed": _number_from_match(PRICE_RE.search(text)),
                "size_sqft": _number_from_match(SIZE_RE.search(text)),
                "card_text": text,
                "raw_card": dict(card),
            }
        )
    return rows


def check_identity(
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


def parse_identity_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    ip = _first_identity_value(payload, "ip", "query", "address", "origin")
    country = _first_identity_value(
        payload,
        "country_code",
        "countryCode",
        "country",
        "country_code2",
    )
    asn_value = payload.get("asn")
    if isinstance(asn_value, Mapping):
        asn = _first_identity_value(asn_value, "asn", "number", "id")
        asn_org = _first_identity_value(asn_value, "name", "org", "organization")
    else:
        asn = "" if asn_value is None else str(asn_value)
        asn_org = ""
    org = _first_identity_value(payload, "org", "organization", "isp") or asn_org
    return {"ip": ip, "country": country, "asn": asn, "org": org}


def validate_identity_result(identity: Mapping[str, Any], *, expected_country: str = "") -> None:
    if identity.get("error"):
        raise RuntimeError(f"identity check failed: {identity['error']}")
    if not identity.get("ip"):
        raise RuntimeError("identity check did not return an IP address")
    country = str(identity.get("country") or "")
    if expected_country and country.upper() != expected_country.upper():
        raise RuntimeError(
            f"identity country mismatch: expected {expected_country}, received {country or 'missing'}"
        )


def proxy_settings(
    *,
    config: CollectionConfig,
    session_id: str,
    env: Mapping[str, str],
) -> dict[str, str] | None:
    if config.proxy == "direct":
        return None
    values = {
        "server": env.get(PROXY_SERVER_ENV, ""),
        "username": env.get(PROXY_USERNAME_ENV, ""),
        "password": env.get(PROXY_PASSWORD_ENV, ""),
    }
    if config.proxy_rotation == "context":
        values = {
            key: value.replace(SESSION_PLACEHOLDER, session_id) for key, value in values.items()
        }
    return {key: value for key, value in values.items() if value}


def transport_outcome(*, final_url: str, html: str, status_code: int) -> str:
    haystack = f"{final_url}\n{html[:20000]}".lower()
    if any(marker in haystack for marker in CAPTCHA_MARKERS):
        return "captcha"
    if status_code == 403:
        return "forbidden"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 400 or status_code == 0:
        return "http_error"
    return "ok"


def validate_search_page(
    *,
    requested_url: str,
    final_url: str,
    cards: Sequence[Mapping[str, str]],
    body_text: str,
    title: str,
) -> str:
    """Do not mistake a redirect, hydration shell, or unknown block for the end."""
    requested, final = urlsplit(requested_url), urlsplit(final_url)
    if (
        requested.netloc.lower() != final.netloc.lower()
        or requested.path.rstrip("/") != final.path.rstrip("/")
        or sorted(parse_qsl(requested.query)) != sorted(parse_qsl(final.query))
    ):
        return "unexpected_redirect"
    if cards:
        return "ok"
    visible = f"{title}\n{body_text}".lower()
    if any(marker in visible for marker in ("security check", "verify you are human")):
        return "captcha"
    if re.search(r"\bno (?:properties|results|listings) found\b", visible):
        return "ok"
    if re.match(r"^\s*0\s+(?:properties|apartments|villas|townhouses|penthouses)\b", title, re.I):
        return "ok"
    return "unrecognized_page"


def failed_fetch_result(
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


def _fetch_with_retries(
    *,
    connection: sqlite3.Connection,
    config: CollectionConfig,
    fetcher: PageFetcher,
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
        if result.outcome not in RETRYABLE_OUTCOMES:
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
    config: CollectionConfig,
    phase: str,
    shard: sqlite3.Row,
    page_number: int,
    attempt: int,
    result: FetchResult,
) -> str:
    if not result.html or config.evidence == "none":
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


def collection_status(connection: sqlite3.Connection) -> dict[str, Any]:
    statuses = {
        row["status"]: row["count"]
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM shards GROUP BY status ORDER BY status"
        )
    }
    run_kind = _metadata_value(connection, "run_kind") or "full"
    terminal = connection.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(reported_count), 0) AS reported, "
        "COALESCE(SUM(observed_unique_count), 0) AS observed FROM shards "
        "WHERE status <> 'split'"
    ).fetchone()
    attempts = connection.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(response_bytes), 0) AS bytes, "
        "COALESCE(SUM(request_count), 0) AS requests, "
        "COALESCE(SUM(CASE WHEN phase IN ('collect', 'practice') AND outcome='ok' "
        "THEN card_count ELSE 0 END), 0) AS cards, "
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
    remaining = sum(statuses.get(status, 0) for status in COLLECTABLE_SHARD_STATUSES)
    shard_count = sum(statuses.values())
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
    if run_kind == "practice":
        coverage_status = "practice_only"
    elif shard_count == 0:
        coverage_status = "not_started"
    elif unresolved == 0 and remaining == 0:
        coverage_status = "complete_with_tolerance" if tolerated else "complete"
    else:
        coverage_status = "not_complete"
    return {
        "schema_version": 1,
        "run_kind": run_kind,
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
        "coverage_status": coverage_status,
    }


def export_collection(connection: sqlite3.Connection, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    _export_query(
        connection,
        output / LISTINGS_EXPORT,
        "SELECT payload_json FROM listings ORDER BY listing_id",
        lambda row: json.loads(row["payload_json"]),
    )
    _export_query(
        connection,
        output / SHARDS_EXPORT,
        "SELECT * FROM shards ORDER BY purpose, property_type, path",
        lambda row: dict(row),
    )
    _export_query(
        connection,
        output / ATTEMPTS_EXPORT,
        "SELECT * FROM page_attempts ORDER BY attempt_id",
        lambda row: dict(row),
    )
    summary = collection_status(connection)
    _atomic_json(output / SUMMARY_FILE, summary)
    return summary


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
    connection: sqlite3.Connection,
    shard_identifier: str,
    status: str,
    stop_reason: str,
) -> None:
    with connection:
        connection.execute(
            "UPDATE shards SET status=?, stop_reason=?, updated_at=? WHERE shard_id=?",
            (status, stop_reason, _now(), shard_identifier),
        )


def _terminal_status(
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


def _metadata_value(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row is not None else None


def _number_from_match(match: re.Match[str] | None) -> int | float | None:
    if match is None:
        return None
    try:
        value = match.group(1).replace(",", "")
        return float(value) if "." in value else int(value)
    except ValueError:
        return None


def _first_identity_value(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _pause(config: CollectionConfig, seed: str) -> None:
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
