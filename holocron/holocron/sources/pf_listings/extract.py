"""Property Finder listing search extraction logic."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from collections import Counter, deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from playwright.sync_api import BrowserContext, Page, Playwright, TimeoutError, sync_playwright

from holocron.contracts import RawFile, RawRelease
from holocron.platform.execution import build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.platform.raw_files import write_jsonl_raw_file as _write_jsonl_raw_file
from holocron.sources.pf_listings.source import (
    PF_RESIDENTIAL_CATEGORY_IDS,
    PropertyFinderListingsConfig,
    SOURCE,
)

logger = logging.getLogger(__name__)

_FILTER_SETTINGS_FILE = "pf_listing_filter_settings.jsonl"
_QUERY_PLAN_FILE = "pf_listing_query_plan.jsonl"
_PLAN_STATE_FILE = "pf_listing_plan_state.jsonl"
_LOCATION_PARTITIONS_FILE = "pf_listing_location_partitions.jsonl"
_SEARCH_PAGES_FILE = "pf_listing_search_pages.jsonl"
_PROPERTIES_FILE = "pf_listing_properties.jsonl"
_DETAILS_FILE = "pf_listing_details.jsonl"
_PROPERTY_TYPE_KEY = "filter[property_type_id]"
_BEDROOM_KEY = "filter[number_of_bedrooms]"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)
_DEFAULT_CHROME_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)
_LOCATION_PAGE_LOG_INTERVAL = 5
_QUERY_PLAN_LOG_INTERVAL = 100
_SEARCH_PAGE_LOG_INTERVAL = 100
_DETAIL_LOG_INTERVAL = 250
_MAX_FETCH_ATTEMPTS = 3
_HTTP_NOT_FOUND = 404
_HTTP_GONE = 410
_NETWORK_IDLE_TIMEOUT_MS = 15_000
_BLOCKED_RESOURCE_TYPES = frozenset({"font", "image", "media"})
_DETAILS_PATH_HTML_SUFFIX = ".html"
_DETAILS_PATH_SEGMENTS = frozenset({"/plp/", "/property/", "/commercial-"})


class PropertyFinderListingsClient(Protocol):
    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]: ...

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]: ...

    def fetch_search_page(self, *, params: Sequence[tuple[str, str]]) -> dict[str, Any]: ...

    def fetch_detail(self, *, details_path: str) -> dict[str, Any]: ...


class PropertyFinderListingsStateStore(Protocol):
    def list_keys(self, *, prefix: str) -> list[str]: ...

    def read_text(self, *, key: str, encoding: str = "utf-8") -> str: ...

    def get_json(self, *, key: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class ListingQuery:
    category_id: int
    location_id: str
    property_type_id: int | None = None
    bedroom: int | None = None
    min_price: int | None = None
    max_price: int | None = None
    depth: int = 0
    lineage: tuple[str, ...] = ()

    def params(self, *, page: int, sort: str) -> tuple[tuple[str, str], ...]:
        pairs: list[tuple[str, str]] = [
            ("c", str(self.category_id)),
            ("l", str(self.location_id)),
            ("page", str(page)),
            ("ob", sort),
        ]
        if self.property_type_id is not None:
            pairs.append(("t", str(self.property_type_id)))
        if self.bedroom is not None:
            pairs.append(("bdr[]", str(self.bedroom)))
        if self.min_price is not None:
            pairs.append(("pf", str(self.min_price)))
        if self.max_price is not None:
            pairs.append(("pt", str(self.max_price)))
        return tuple(pairs)

    @property
    def signature(self) -> str:
        payload = {
            "category_id": self.category_id,
            "location_id": self.location_id,
            "property_type_id": self.property_type_id,
            "bedroom": self.bedroom,
            "min_price": self.min_price,
            "max_price": self.max_price,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ListingPageCollectionResult:
    search_page_rows: list[dict[str, Any]]
    property_rows: list[dict[str, Any]]
    next_query_index: int
    next_page: int
    completed: bool
    fetched_pages: int
    search_error_count: int


@dataclass(frozen=True, slots=True)
class DetailCollectionResult:
    detail_rows: list[dict[str, Any]]
    next_manifest_index: int
    next_row_index: int
    completed: bool
    source_manifest_count: int
    source_property_row_count: int
    source_property_invalid_row_count: int = 0


@dataclass(frozen=True, slots=True)
class QueryPlanResult:
    plan_rows: list[dict[str, Any]]
    terminal_queries: list[ListingQuery]
    queue: deque[ListingQuery]
    assessed_count: int
    terminal_count: int
    split_count: int
    fetch_error_count: int
    skipped_count: int
    completed: bool


class PropertyFinderBrowserListingsClient:
    def __init__(
        self,
        *,
        context: BrowserContext,
        config: PropertyFinderListingsConfig,
    ) -> None:
        self._context = context
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._static_assets_base_url = config.static_assets_base_url.rstrip("/")
        self._search_page: Page | None = None
        self._detail_page: Page | None = None
        self._search_build_id: str | None = None

    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        url = (
            f"{self._static_assets_base_url}/filters/form-settings/v4/"
            f"{locale}/{category}.data.{self._config.country_code}.json"
        )
        response = httpx.get(url, headers=_headers(), timeout=self._config.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Property Finder filter settings response must be an object: {url}")
        return payload

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        url = f"{self._base_url}/api/pwa/locations"
        response = httpx.get(
            url,
            params={
                "locale": locale,
                "pagination.limit": limit,
                "pagination.page": page,
            },
            headers=_headers(),
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Property Finder locations response must be an object: {url}")
        return payload

    def fetch_search_page(self, *, params: Sequence[tuple[str, str]]) -> dict[str, Any]:
        page = self._search_page_or_new()
        url = self._search_url(params=params)
        last_error = ""
        for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
            try:
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(self._config.timeout_seconds * 1000),
                )
                status = response.status if response is not None else 0
                if status >= 500:
                    last_error = f"status={status}"
                elif status >= 400:
                    raise RuntimeError(f"Property Finder search failed status={status} url={url}")
                else:
                    return _next_data_from_page(page=page, url=url)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if attempt == _MAX_FETCH_ATTEMPTS:
                    raise RuntimeError(
                        f"Property Finder search navigation failed after retries url={url}: "
                        f"{last_error}"
                    ) from exc
            if attempt < _MAX_FETCH_ATTEMPTS:
                page.wait_for_timeout(1000 * attempt)
        raise RuntimeError(
            f"Property Finder search navigation failed after retries url={url}: {last_error}"
        )

    def _search_url(self, *, params: Sequence[tuple[str, str]]) -> str:
        return f"{self._base_url}/{self._config.locale}/search?{urlencode(list(params), doseq=True)}"

    def fetch_detail(self, *, details_path: str) -> dict[str, Any]:
        page = self._detail_page_or_new()
        url = urljoin(f"{self._base_url}/", details_path.lstrip("/"))
        page.goto(
            url, wait_until="domcontentloaded", timeout=int(self._config.timeout_seconds * 1000)
        )
        return _next_data_from_page(page=page, url=url)

    def _ensure_search_build_id(self) -> str:
        if self._search_build_id:
            return self._search_build_id
        page = self._search_page_or_new()
        bootstrap_url = urljoin(
            f"{self._base_url}/", self._config.bootstrap_search_path.lstrip("/")
        )
        page.goto(
            bootstrap_url,
            wait_until="domcontentloaded",
            timeout=int(self._config.timeout_seconds * 1000),
        )
        try:
            page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT_MS)
        except TimeoutError:
            page.wait_for_timeout(3000)
        next_data = _next_data_from_page(page=page, url=bootstrap_url)
        build_id = _string_value(next_data.get("buildId"))
        if not build_id:
            raise RuntimeError(
                "Property Finder search page did not expose Next.js buildId. "
                "Run headful with storage_state_path if the session is challenged."
            )
        self._search_build_id = build_id
        return build_id

    def _fetch_json(self, *, url: str, page: Page) -> dict[str, Any]:
        last_error = ""
        for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
            try:
                response = page.evaluate(
                    """
                    async ({ url, timeoutMs }) => {
                        const controller = new AbortController();
                        const timeout = setTimeout(() => controller.abort(), timeoutMs);
                        try {
                            const response = await fetch(url, {
                                credentials: 'include',
                                headers: { accept: 'application/json,text/plain,*/*' },
                                signal: controller.signal,
                            });
                            return {
                                status: response.status,
                                url: response.url,
                                text: await response.text(),
                            };
                        } finally {
                            clearTimeout(timeout);
                        }
                    }
                    """,
                    {"url": url, "timeoutMs": int(self._config.timeout_seconds * 1000)},
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if attempt == _MAX_FETCH_ATTEMPTS:
                    raise RuntimeError(
                        f"Property Finder browser fetch failed after retries url={url}: {last_error}"
                    ) from exc
                page.wait_for_timeout(1000 * attempt)
                continue
            if not isinstance(response, dict):
                last_error = "invalid browser fetch response"
                if attempt == _MAX_FETCH_ATTEMPTS:
                    raise RuntimeError(
                        f"Property Finder browser fetch returned invalid response: {url}"
                    )
                page.wait_for_timeout(1000 * attempt)
                continue
            status = int(response.get("status") or 0)
            text = _string_value(response.get("text"))
            if status in {_HTTP_NOT_FOUND, _HTTP_GONE}:
                return _empty_search_payload(http_status=status, url=url)
            if status >= 500 and attempt < _MAX_FETCH_ATTEMPTS:
                last_error = f"status={status}"
                page.wait_for_timeout(1000 * attempt)
                continue
            if status >= 400:
                raise RuntimeError(f"Property Finder fetch failed status={status} url={url}")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                snippet = re.sub(r"\s+", " ", text[:160]).strip()
                last_error = f"non-JSON response snippet={snippet!r}"
                if attempt == _MAX_FETCH_ATTEMPTS:
                    raise RuntimeError(
                        f"Property Finder fetch returned non-JSON after retries "
                        f"url={url}: {last_error}"
                    ) from exc
                page.wait_for_timeout(1000 * attempt)
                continue
            if not isinstance(payload, dict):
                last_error = "JSON response was not an object"
                if attempt == _MAX_FETCH_ATTEMPTS:
                    raise ValueError(f"Property Finder JSON response must be an object: {url}")
                page.wait_for_timeout(1000 * attempt)
                continue
            return payload
        raise RuntimeError(
            f"Property Finder browser fetch failed after retries url={url}: {last_error}"
        )

    def _search_page_or_new(self) -> Page:
        if self._search_page is None or self._search_page.is_closed():
            self._search_page = self._context.new_page()
        return self._search_page

    def _detail_page_or_new(self) -> Page:
        if self._detail_page is None or self._detail_page.is_closed():
            self._detail_page = self._context.new_page()
        return self._detail_page


def extract_release(
    output_dir: str | Path,
    *,
    config: PropertyFinderListingsConfig | dict,
    now: datetime | None = None,
    listing_client: PropertyFinderListingsClient | None = None,
    state_store: PropertyFinderListingsStateStore | None = None,
    playwright_factory: Callable[[], AbstractContextManager[Playwright]] = sync_playwright,
    progress_log: Any | None = None,
) -> RawRelease:
    parsed_config = (
        config
        if isinstance(config, PropertyFinderListingsConfig)
        else PropertyFinderListingsConfig.model_validate(config)
    )
    if (
        parsed_config.storage_state_path.strip()
        and not Path(parsed_config.storage_state_path).exists()
    ):
        raise FileNotFoundError(
            f"Property Finder storage state not found: {parsed_config.storage_state_path}"
        )

    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    log = progress_log or logger

    with contextlib.ExitStack() as stack:
        if listing_client is None:
            listing_client = stack.enter_context(
                _browser_listing_client(config=parsed_config, playwright_factory=playwright_factory)
            )
        files, metadata = _extract_files(
            output_path=output_path,
            config=parsed_config,
            listing_client=listing_client,
            state_store=state_store,
            scraped_at=current_time.isoformat(),
            progress_log=log,
        )

    if not files:
        raise RuntimeError("Property Finder listings extraction produced no raw files")

    return build_raw_release(
        source=SOURCE,
        files=files,
        run_id=run_id,
        now=current_time,
        metadata={"config": safe_config_metadata(parsed_config), **metadata},
    )


def _extract_files(
    *,
    output_path: Path,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    state_store: PropertyFinderListingsStateStore | None,
    scraped_at: str,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    if config.mode == "snapshot":
        return _extract_snapshot_files(
            output_path=output_path,
            config=config,
            listing_client=listing_client,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )
    if config.mode == "plan":
        return _extract_plan_files(
            output_path=output_path,
            config=config,
            listing_client=listing_client,
            state_store=state_store,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )
    if state_store is None:
        raise RuntimeError(f"Property Finder {config.mode} mode requires an R2/S3 state store")
    if config.mode == "search":
        return _extract_search_chunk_files(
            output_path=output_path,
            config=config,
            listing_client=listing_client,
            state_store=state_store,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )
    if config.mode == "latest_delta":
        return _extract_latest_delta_files(
            output_path=output_path,
            config=config,
            listing_client=listing_client,
            state_store=state_store,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )
    if config.mode == "details":
        return _extract_detail_chunk_files(
            output_path=output_path,
            config=config,
            listing_client=listing_client,
            state_store=state_store,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )
    raise ValueError(f"Unsupported Property Finder listings mode: {config.mode}")


def _extract_snapshot_files(
    *,
    output_path: Path,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    scraped_at: str,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    filter_settings_by_category = {
        category: listing_client.fetch_filter_settings(category=category, locale=config.locale)
        for category in config.categories
    }
    property_type_choices = {
        category: _property_type_choices(filter_settings)
        for category, filter_settings in filter_settings_by_category.items()
    }
    location_children_by_parent, location_partition_rows = _collect_location_partitions(
        config=config,
        listing_client=listing_client,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )
    plan_rows, terminal_queries = _plan_queries(
        config=config,
        listing_client=listing_client,
        filter_settings_by_category=filter_settings_by_category,
        property_type_choices=property_type_choices,
        location_children_by_parent=location_children_by_parent,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )
    listing_pages = _collect_listing_pages(
        config=config,
        listing_client=listing_client,
        terminal_queries=terminal_queries,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )
    search_page_rows = listing_pages.search_page_rows
    property_rows = listing_pages.property_rows
    detail_rows = _collect_detail_rows(
        config=config,
        listing_client=listing_client,
        property_rows=property_rows,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )

    filter_setting_rows = [
        {
            "endpoint": "filter_settings",
            "scraped_at": scraped_at,
            "locale": config.locale,
            "country_code": config.country_code,
            "category_id": category,
            "property_type_choices": property_type_choices[category],
            "bedroom_choices": _choice_rows(filter_settings, _BEDROOM_KEY),
            "sort_choices": _choice_rows(filter_settings, "sort"),
            "raw": filter_settings,
        }
        for category, filter_settings in filter_settings_by_category.items()
    ]
    files = (
        _write_jsonl_raw_file(output_path / _FILTER_SETTINGS_FILE, filter_setting_rows),
        _write_jsonl_raw_file(output_path / _LOCATION_PARTITIONS_FILE, location_partition_rows),
        _write_jsonl_raw_file(output_path / _QUERY_PLAN_FILE, plan_rows),
        _write_jsonl_raw_file(output_path / _SEARCH_PAGES_FILE, search_page_rows),
        _write_jsonl_raw_file(output_path / _PROPERTIES_FILE, property_rows),
        _write_jsonl_raw_file(output_path / _DETAILS_FILE, detail_rows),
    )
    metadata = {
        "stage": "snapshot",
        "planned_query_count": len(plan_rows),
        "location_partition_count": len(location_partition_rows),
        "location_partition_parent_count": len(location_children_by_parent),
        "terminal_query_count": len(terminal_queries),
        "search_page_count": len(search_page_rows),
        "property_row_count": len(property_rows),
        "detail_row_count": len(detail_rows),
        "search_completed_result_set": listing_pages.completed,
        "next_query_index": listing_pages.next_query_index,
        "next_page": listing_pages.next_page,
        "search_error_count": listing_pages.search_error_count,
        "categories": list(config.categories),
        "location_ids": list(config.location_ids),
    }
    return files, metadata


def _extract_plan_files(
    *,
    output_path: Path,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    state_store: PropertyFinderListingsStateStore | None,
    scraped_at: str,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    filter_settings_by_category = {
        category: listing_client.fetch_filter_settings(category=category, locale=config.locale)
        for category in config.categories
    }
    property_type_choices = {
        category: _property_type_choices(filter_settings)
        for category, filter_settings in filter_settings_by_category.items()
    }
    location_children_by_parent, location_partition_rows = _collect_location_partitions(
        config=config,
        listing_client=listing_client,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )
    previous_state = _load_plan_state(
        state_store=state_store,
        plan_state_manifest_s3_key=config.plan_state_manifest_s3_key,
    )
    if previous_state:
        queue = deque(
            _listing_query_from_payload(query_payload)
            for query_payload in previous_state.get("queue", [])
            if isinstance(query_payload, dict)
        )
        assessed_start = int(previous_state.get("assessed_count") or 0)
        terminal_start = int(previous_state.get("terminal_count") or 0)
        split_start = int(previous_state.get("split_count") or 0)
        fetch_error_start = int(previous_state.get("fetch_error_count") or 0)
        skipped_start = int(previous_state.get("skipped_count") or 0)
    else:
        queue = deque(
            ListingQuery(category_id=category, location_id=location_id)
            for category in config.categories
            for location_id in config.location_ids
        )
        assessed_start = 0
        terminal_start = 0
        split_start = 0
        fetch_error_start = 0
        skipped_start = 0

    plan_result = _plan_queries_chunk(
        config=config,
        listing_client=listing_client,
        filter_settings_by_category=filter_settings_by_category,
        property_type_choices=property_type_choices,
        location_children_by_parent=location_children_by_parent,
        queue=queue,
        assessed_start=assessed_start,
        terminal_start=terminal_start,
        split_start=split_start,
        fetch_error_start=fetch_error_start,
        skipped_start=skipped_start,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )
    filter_setting_rows = _filter_setting_rows(
        config=config,
        filter_settings_by_category=filter_settings_by_category,
        property_type_choices=property_type_choices,
        scraped_at=scraped_at,
    )
    plan_state_rows = [
        {
            "endpoint": "plan_state",
            "scraped_at": scraped_at,
            "completed": plan_result.completed,
            "queue": [_query_payload(query) for query in plan_result.queue],
            "queue_count": len(plan_result.queue),
            "assessed_count": plan_result.assessed_count,
            "terminal_count": plan_result.terminal_count,
            "split_count": plan_result.split_count,
            "fetch_error_count": plan_result.fetch_error_count,
            "skipped_count": plan_result.skipped_count,
            "max_planned_queries": config.max_planned_queries,
            "max_plan_queries_per_run": config.max_plan_queries_per_run,
        }
    ]
    files: tuple[RawFile, ...] = (
        _write_jsonl_raw_file(output_path / _QUERY_PLAN_FILE, plan_result.plan_rows),
        _write_jsonl_raw_file(output_path / _PLAN_STATE_FILE, plan_state_rows),
    )
    if not previous_state:
        files = (
            _write_jsonl_raw_file(output_path / _FILTER_SETTINGS_FILE, filter_setting_rows),
            _write_jsonl_raw_file(output_path / _LOCATION_PARTITIONS_FILE, location_partition_rows),
            *files,
        )
    metadata = {
        "stage": "plan",
        "planned_query_count": plan_result.assessed_count,
        "plan_rows_in_run": len(plan_result.plan_rows),
        "location_partition_count": len(location_partition_rows),
        "location_partition_parent_count": len(location_children_by_parent),
        "terminal_query_count": plan_result.terminal_count,
        "terminal_query_count_in_run": len(plan_result.terminal_queries),
        "split_count": plan_result.split_count,
        "fetch_error_count": plan_result.fetch_error_count,
        "skipped_planning_limit_count": plan_result.skipped_count,
        "plan_completed_result_set": plan_result.completed,
        "queue_count": len(plan_result.queue),
        "previous_plan_manifest_s3_keys": list(config.plan_manifest_s3_keys),
        "previous_plan_state_manifest_s3_key": config.plan_state_manifest_s3_key,
        "categories": list(config.categories),
        "location_ids": list(config.location_ids),
    }
    return files, metadata


def _extract_search_chunk_files(
    *,
    output_path: Path,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    state_store: PropertyFinderListingsStateStore,
    scraped_at: str,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    terminal_queries = _load_terminal_queries_from_plan(
        state_store=state_store,
        plan_manifest_s3_key=config.plan_manifest_s3_key,
        plan_manifest_s3_keys=config.plan_manifest_s3_keys,
    )
    listing_pages = _collect_listing_pages(
        config=config,
        listing_client=listing_client,
        terminal_queries=terminal_queries,
        scraped_at=scraped_at,
        progress_log=progress_log,
        query_start_index=config.search_query_cursor,
        page_start=config.search_page_cursor,
    )
    detail_rows: list[dict[str, Any]] = []
    if config.fetch_details:
        detail_rows = _collect_detail_rows(
            config=config,
            listing_client=listing_client,
            property_rows=listing_pages.property_rows,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )
    files = (
        _write_jsonl_raw_file(output_path / _SEARCH_PAGES_FILE, listing_pages.search_page_rows),
        _write_jsonl_raw_file(output_path / _PROPERTIES_FILE, listing_pages.property_rows),
    )
    if config.fetch_details:
        files = (*files, _write_jsonl_raw_file(output_path / _DETAILS_FILE, detail_rows))
    metadata = {
        "stage": "search",
        "plan_manifest_s3_key": config.plan_manifest_s3_key,
        "plan_manifest_s3_keys": list(config.plan_manifest_s3_keys),
        "terminal_query_count": len(terminal_queries),
        "query_start_index": config.search_query_cursor,
        "page_start": config.search_page_cursor,
        "next_query_index": listing_pages.next_query_index,
        "next_page": listing_pages.next_page,
        "search_completed_result_set": listing_pages.completed,
        "search_page_count": len(listing_pages.search_page_rows),
        "property_row_count": len(listing_pages.property_rows),
        "detail_row_count": len(detail_rows),
        "search_error_count": listing_pages.search_error_count,
        "categories": list(config.categories),
        "location_ids": list(config.location_ids),
    }
    return files, metadata


def _extract_latest_delta_files(
    *,
    output_path: Path,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    state_store: PropertyFinderListingsStateStore,
    scraped_at: str,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    previous_state = _load_latest_delta_state(
        state_store=state_store,
        key=config.latest_delta_state_key,
    )
    state_listings = _latest_delta_listings(previous_state)
    state_was_empty = not state_listings
    queries = [
        ListingQuery(category_id=category, location_id=location_id)
        for category in config.categories
        for location_id in config.location_ids
    ]
    search_page_rows: list[dict[str, Any]] = []
    property_rows: list[dict[str, Any]] = []
    detail_candidates: list[dict[str, Any]] = []
    seen_properties: set[str] = set()
    pages_remaining = config.max_search_pages_per_run
    stopped_queries = 0
    search_error_count = 0

    _log_info(
        progress_log,
        (
            "pf_listings: latest delta start queries=%s max_pages_per_query=%s "
            "page_budget=%s state_empty=%s"
        ),
        len(queries),
        config.max_pages_per_query,
        config.max_search_pages_per_run,
        state_was_empty,
    )

    for query_index, query in enumerate(queries):
        if pages_remaining <= 0:
            break
        seen_pages_in_a_row = 0
        page_count = config.max_pages_per_query
        page = 1
        while page <= min(page_count, config.max_pages_per_query) and pages_remaining > 0:
            params = query.params(page=page, sort=config.sort)
            try:
                payload = listing_client.fetch_search_page(params=params)
            except Exception as exc:  # noqa: BLE001
                search_error_count += 1
                pages_remaining -= 1
                search_page_rows.append(
                    {
                        "endpoint": "latest_delta_search",
                        "scraped_at": scraped_at,
                        "query_signature": query.signature,
                        "query_index": query_index,
                        "query": _query_payload(query),
                        "params": dict(params),
                        "page": page,
                        "status": "search_error",
                        "listing_wrapper_count": 0,
                        "total_count": None,
                        "page_count": page_count,
                        "meta": {},
                        "error": str(exc),
                    }
                )
                break

            search_result = _search_result(payload)
            meta = _search_meta(search_result)
            wrappers = _listing_wrappers(search_result)
            page_count = _page_count(search_result, fallback=page_count)
            pages_remaining -= 1
            page_new_or_changed = 0
            page_property_count = 0

            for wrapper_index, wrapper in enumerate(wrappers, start=1):
                property_payload = _property_from_wrapper(wrapper)
                if property_payload is None:
                    continue
                property_key = _property_key(wrapper=wrapper, property_payload=property_payload)
                if property_key in seen_properties:
                    continue
                seen_properties.add(property_key)
                row = _property_row(
                    query=query,
                    page=page,
                    wrapper_index=wrapper_index,
                    property_key=property_key,
                    wrapper=wrapper,
                    property_payload=property_payload,
                    scraped_at=scraped_at,
                )
                identity = _latest_delta_listing_identity(row)
                fingerprint = _fingerprint_payload(property_payload)
                previous = state_listings.get(identity)
                reason = "unchanged"
                selected_for_detail = False
                if previous is None:
                    reason = "new"
                    selected_for_detail = (
                        not state_was_empty or config.latest_delta_bootstrap_details
                    )
                elif previous.get("property_fingerprint") != fingerprint:
                    reason = "changed"
                    selected_for_detail = True

                if selected_for_detail and config.fetch_details:
                    detail_candidates.append(row)
                    page_new_or_changed += 1
                elif reason in {"new", "changed"}:
                    page_new_or_changed += 1

                row.update(
                    {
                        "delta_reason": reason,
                        "selected_for_detail": selected_for_detail and config.fetch_details,
                        "property_fingerprint": fingerprint,
                        "previous_property_fingerprint": previous.get("property_fingerprint")
                        if previous
                        else "",
                    }
                )
                property_rows.append(row)
                page_property_count += 1

            if not state_was_empty and page_property_count and page_new_or_changed == 0:
                seen_pages_in_a_row += 1
            else:
                seen_pages_in_a_row = 0

            search_page_rows.append(
                {
                    "endpoint": "latest_delta_search",
                    "scraped_at": scraped_at,
                    "query_signature": query.signature,
                    "query_index": query_index,
                    "query": _query_payload(query),
                    "params": dict(params),
                    "page": page,
                    "status": "ok",
                    "listing_wrapper_count": len(wrappers),
                    "property_row_count": page_property_count,
                    "new_or_changed_count": page_new_or_changed,
                    "seen_pages_in_a_row": seen_pages_in_a_row,
                    "total_count": _total_count(search_result, fallback=len(wrappers)),
                    "page_count": page_count,
                    "meta": meta,
                    "raw": search_result,
                }
            )

            if not wrappers:
                break
            if (
                not state_was_empty
                and seen_pages_in_a_row >= config.latest_delta_stop_after_seen_pages
            ):
                stopped_queries += 1
                break
            page += 1
            if config.request_pause_seconds:
                time.sleep(config.request_pause_seconds)

    if config.fetch_details and config.latest_delta_detail_audit_limit > 0 and not state_was_empty:
        selected_ids = {_latest_delta_listing_identity(row) for row in detail_candidates}
        audit_rows = sorted(
            (
                row
                for row in property_rows
                if row.get("delta_reason") == "unchanged"
                and _latest_delta_listing_identity(row) not in selected_ids
            ),
            key=lambda row: str(
                state_listings.get(_latest_delta_listing_identity(row), {}).get(
                    "last_detail_scraped_at"
                )
                or ""
            ),
        )
        for row in audit_rows[: config.latest_delta_detail_audit_limit]:
            row["delta_reason"] = "audit"
            row["selected_for_detail"] = True
            detail_candidates.append(row)

    detail_rows: list[dict[str, Any]] = []
    if config.fetch_details and detail_candidates:
        detail_rows = _collect_detail_rows(
            config=config,
            listing_client=listing_client,
            property_rows=detail_candidates,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )

    state_payload = _build_latest_delta_state_payload(
        previous_state=previous_state,
        property_rows=property_rows,
        detail_rows=detail_rows,
        scraped_at=scraped_at,
    )
    state_file = "pf_listing_latest_delta_state.json"
    state_update = _write_state_update_file(
        output_path, state_file, config.latest_delta_state_key, state_payload
    )
    files = (
        _write_jsonl_raw_file(output_path / _SEARCH_PAGES_FILE, search_page_rows),
        _write_jsonl_raw_file(output_path / _PROPERTIES_FILE, property_rows),
        _write_jsonl_raw_file(output_path / _DETAILS_FILE, detail_rows),
    )
    reason_counts = dict(
        Counter(str(row.get("delta_reason") or "unknown") for row in property_rows)
    )
    metadata = {
        "stage": "latest_delta",
        "query_count": len(queries),
        "search_page_count": len(search_page_rows),
        "property_row_count": len(property_rows),
        "selected_detail_candidate_count": len(detail_candidates),
        "detail_row_count": len(detail_rows),
        "search_error_count": search_error_count,
        "stopped_query_count": stopped_queries,
        "state_was_empty": state_was_empty,
        "delta_reason_counts": reason_counts,
        "categories": list(config.categories),
        "location_ids": list(config.location_ids),
        "_state_updates": [state_update],
    }
    return files, metadata


def _extract_detail_chunk_files(
    *,
    output_path: Path,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    state_store: PropertyFinderListingsStateStore,
    scraped_at: str,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    details = _collect_detail_rows_from_manifests(
        config=config,
        listing_client=listing_client,
        state_store=state_store,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )
    files = (_write_jsonl_raw_file(output_path / _DETAILS_FILE, details.detail_rows),)
    metadata = {
        "stage": "details",
        "manifest_prefix": config.manifest_prefix,
        "detail_manifest_start_index": config.detail_manifest_cursor,
        "detail_row_start_index": config.detail_row_cursor,
        "next_manifest_index": details.next_manifest_index,
        "next_row_index": details.next_row_index,
        "detail_completed_result_set": details.completed,
        "source_manifest_count": details.source_manifest_count,
        "source_property_row_count": details.source_property_row_count,
        "source_property_invalid_row_count": details.source_property_invalid_row_count,
        "detail_row_count": len(details.detail_rows),
        "categories": list(config.categories),
        "location_ids": list(config.location_ids),
    }
    return files, metadata


def _load_latest_delta_state(
    *, state_store: PropertyFinderListingsStateStore, key: str
) -> dict[str, Any]:
    payload = state_store.get_json(key=key)
    if payload is not None and isinstance(payload.get("listings"), dict):
        return dict(payload)
    return {"version": 1, "listings": {}}


def _latest_delta_listings(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    listings = state.get("listings")
    if not isinstance(listings, dict):
        return {}
    return {str(key): value for key, value in listings.items() if isinstance(value, dict)}


def _latest_delta_listing_identity(row: Mapping[str, Any]) -> str:
    listing_id = _string_value(row.get("listing_id"))
    if listing_id:
        return f"listing_id:{listing_id}"
    property_key = _string_value(row.get("property_key"))
    if property_key:
        return property_key
    details_path = _string_value(row.get("details_path"))
    if details_path:
        return f"path:{details_path}"
    return "sha256:" + _fingerprint_payload(row)


def _build_latest_delta_state_payload(
    *,
    previous_state: Mapping[str, Any],
    property_rows: Sequence[Mapping[str, Any]],
    detail_rows: Sequence[Mapping[str, Any]],
    scraped_at: str,
) -> dict[str, Any]:
    listings = _latest_delta_listings(previous_state)
    for row in property_rows:
        identity = _latest_delta_listing_identity(row)
        previous = listings.get(identity, {})
        raw_property_value = row.get("raw_property")
        raw_property = raw_property_value if isinstance(raw_property_value, Mapping) else {}
        listings[identity] = {
            **previous,
            "listing_identity": identity,
            "listing_id": row.get("listing_id"),
            "property_key": row.get("property_key"),
            "first_seen_at": previous.get("first_seen_at") or scraped_at,
            "last_seen_at": scraped_at,
            "property_fingerprint": row.get("property_fingerprint")
            or _fingerprint_payload(raw_property),
            "listed_date": raw_property.get("listed_date"),
            "last_refreshed_at": raw_property.get("last_refreshed_at"),
            "details_path": row.get("details_path"),
            "share_url": row.get("share_url"),
            "category_id": row.get("category_id"),
            "location_id": row.get("location_id"),
            "property_type_id": row.get("property_type_id"),
        }

    for row in detail_rows:
        if row.get("status") != "ok":
            continue
        identity = _latest_delta_listing_identity(row)
        listing_id = _string_value(row.get("listing_id"))
        if not identity:
            continue
        previous = listings.get(identity, {})
        detail_property = row.get("detail_property")
        listings[identity] = {
            **previous,
            "listing_identity": identity,
            "listing_id": listing_id,
            "last_detail_scraped_at": scraped_at,
            "detail_fingerprint": _fingerprint_payload(detail_property),
        }

    return {
        "version": 1,
        "updated_at": scraped_at,
        "listing_count": len(listings),
        "listings": listings,
    }


def _fingerprint_payload(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_state_update_file(
    output_path: Path, file_name: str, key: str, payload: Mapping[str, Any]
) -> dict[str, str]:
    path = output_path / file_name
    path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
    return {"key": key, "path": str(path)}


def _filter_setting_rows(
    *,
    config: PropertyFinderListingsConfig,
    filter_settings_by_category: Mapping[int, dict[str, Any]],
    property_type_choices: Mapping[int, Sequence[dict[str, Any]]],
    scraped_at: str,
) -> list[dict[str, Any]]:
    return [
        {
            "endpoint": "filter_settings",
            "scraped_at": scraped_at,
            "locale": config.locale,
            "country_code": config.country_code,
            "category_id": category,
            "property_type_choices": list(property_type_choices[category]),
            "bedroom_choices": _choice_rows(filter_settings, _BEDROOM_KEY),
            "sort_choices": _choice_rows(filter_settings, "sort"),
            "raw": filter_settings,
        }
        for category, filter_settings in filter_settings_by_category.items()
    ]


def _collect_location_partitions(
    *,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    scraped_at: str,
    progress_log: Any,
) -> tuple[dict[str, tuple[str, ...]], list[dict[str, Any]]]:
    if not config.split_by_location:
        _log_info(progress_log, "pf_listings: location partition discovery disabled")
        return {}, []

    _log_info(
        progress_log,
        "pf_listings: discovering location partitions roots=%s max_pages=%s page_limit=%s",
        list(config.location_ids),
        config.max_location_pages,
        config.location_page_limit,
    )
    root_ids = {str(location_id) for location_id in config.location_ids}
    children_by_parent: dict[str, list[str]] = {}
    rows: list[dict[str, Any]] = []
    seen_location_ids: set[str] = set()
    for page in range(1, config.max_location_pages + 1):
        payload = listing_client.fetch_locations(
            page=page,
            limit=config.location_page_limit,
            locale=config.locale,
        )
        attributes = _location_attributes(payload)
        for location in attributes:
            location_id = _string_value(location.get("id"))
            path_ids = _path_ids(location.get("path"))
            if not location_id or location_id in seen_location_ids:
                continue
            if not _location_is_under_roots(
                location_id=location_id,
                path_ids=path_ids,
                root_ids=root_ids,
            ):
                continue
            seen_location_ids.add(location_id)
            parent_id = path_ids[-2] if len(path_ids) > 1 else None
            rows.append(
                {
                    "endpoint": "pwa_locations",
                    "scraped_at": scraped_at,
                    "locale": config.locale,
                    "location_id": location_id,
                    "parent_location_id": parent_id,
                    "path": _string_value(location.get("path")),
                    "path_ids": path_ids,
                    "path_name": _string_value(location.get("path_name")),
                    "name": _string_value(location.get("name")),
                    "level": location.get("level"),
                    "location_type": _string_value(location.get("location_type")),
                    "children_count": location.get("children_count"),
                    "top_location_id": location.get("top_location_id"),
                    "published": location.get("published"),
                    "raw": location,
                }
            )
            if parent_id and parent_id != location_id:
                children_by_parent.setdefault(parent_id, []).append(location_id)
        if page <= 2 or page % _LOCATION_PAGE_LOG_INTERVAL == 0:
            _log_info(
                progress_log,
                (
                    "pf_listings: location partition progress page=%s response_count=%s "
                    "partitions=%s parent_count=%s"
                ),
                page,
                len(attributes),
                len(rows),
                len(children_by_parent),
            )
        if not attributes or len(attributes) < config.location_page_limit:
            break
        if config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)

    deduped_children_by_parent = {
        parent_id: tuple(dict.fromkeys(children))
        for parent_id, children in children_by_parent.items()
    }
    _log_info(
        progress_log,
        "pf_listings: completed location partition discovery partitions=%s parent_count=%s",
        len(rows),
        len(deduped_children_by_parent),
    )
    return (deduped_children_by_parent, rows)


def _load_plan_state(
    *,
    state_store: PropertyFinderListingsStateStore | None,
    plan_state_manifest_s3_key: str,
) -> dict[str, Any]:
    if not plan_state_manifest_s3_key.strip():
        return {}
    if state_store is None:
        raise RuntimeError("Property Finder plan resume requires an R2/S3 state store")
    rows = _load_manifest_jsonl_rows(
        state_store=state_store,
        manifest=_read_manifest(
            state_store=state_store,
            manifest_key=plan_state_manifest_s3_key,
        ),
        manifest_key=plan_state_manifest_s3_key,
        file_name=_PLAN_STATE_FILE,
    )
    if not rows:
        return {}
    return rows[-1]


def _plan_queries(
    *,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    filter_settings_by_category: Mapping[int, dict[str, Any]],
    property_type_choices: Mapping[int, Sequence[dict[str, Any]]],
    location_children_by_parent: Mapping[str, Sequence[str]],
    scraped_at: str,
    progress_log: Any,
) -> tuple[list[dict[str, Any]], list[ListingQuery]]:
    queue: deque[ListingQuery] = deque(
        ListingQuery(category_id=category, location_id=location_id)
        for category in config.categories
        for location_id in config.location_ids
    )
    plan_result = _plan_queries_chunk(
        config=config,
        listing_client=listing_client,
        filter_settings_by_category=filter_settings_by_category,
        property_type_choices=property_type_choices,
        location_children_by_parent=location_children_by_parent,
        queue=queue,
        assessed_start=0,
        terminal_start=0,
        split_start=0,
        fetch_error_start=0,
        skipped_start=0,
        scraped_at=scraped_at,
        progress_log=progress_log,
        max_assessments=config.max_planned_queries,
        include_assessed_index=False,
    )
    return plan_result.plan_rows, plan_result.terminal_queries


def _plan_queries_chunk(
    *,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    filter_settings_by_category: Mapping[int, dict[str, Any]],
    property_type_choices: Mapping[int, Sequence[dict[str, Any]]],
    location_children_by_parent: Mapping[str, Sequence[str]],
    queue: deque[ListingQuery],
    assessed_start: int,
    terminal_start: int,
    split_start: int,
    fetch_error_start: int,
    skipped_start: int,
    scraped_at: str,
    progress_log: Any,
    max_assessments: int | None = None,
    include_assessed_index: bool = True,
) -> QueryPlanResult:
    plan_rows: list[dict[str, Any]] = []
    terminal_queries: list[ListingQuery] = []
    status_counts: Counter[str] = Counter(
        {
            "terminal": terminal_start,
            "split": split_start,
            "fetch_error": fetch_error_start,
            "skipped_planning_limit": skipped_start,
        }
    )
    assessed_total = assessed_start
    assessed_this_run = 0
    max_assessments = max_assessments or config.max_plan_queries_per_run

    _log_info(
        progress_log,
        (
            "pf_listings: planning query chunk start assessed_total=%s queue=%s "
            "max_per_run=%s max_planned=%s max_results_per_query=%s max_depth=%s"
        ),
        assessed_total,
        len(queue),
        max_assessments,
        config.max_planned_queries,
        config.max_results_per_query,
        config.max_partition_depth,
    )
    while (
        queue
        and assessed_this_run < max_assessments
        and assessed_total < config.max_planned_queries
    ):
        query = queue.popleft()
        params = query.params(page=1, sort=config.sort)
        try:
            payload = listing_client.fetch_search_page(params=params)
        except Exception as exc:  # noqa: BLE001
            assessed_total += 1
            assessed_this_run += 1
            status_counts["fetch_error"] += 1
            plan_rows.append(
                {
                    "endpoint": "search_plan",
                    "scraped_at": scraped_at,
                    "query_signature": query.signature,
                    "query": _query_payload(query),
                    "params": dict(params),
                    "status": "fetch_error",
                    "split_reason": "",
                    "needs_split": None,
                    "terminal": False,
                    "depth": query.depth,
                    **({"assessed_index": assessed_total} if include_assessed_index else {}),
                    "error": str(exc),
                }
            )
            _log_warning(
                progress_log,
                (
                    "pf_listings: query planning fetch error assessed_total=%s "
                    "assessed_run=%s queue=%s query=%s error=%s"
                ),
                assessed_total,
                assessed_this_run,
                len(queue),
                query.signature,
                exc,
            )
            continue

        search_result = _search_result(payload)
        meta = _search_meta(search_result)
        listings = _listing_wrappers(search_result)
        total_count = _total_count(search_result, fallback=len(listings))
        page_count = _page_count(search_result, fallback=1 if listings else 0)
        needs_split = (
            total_count > config.max_results_per_query or page_count > config.max_pages_per_query
        )
        split_reason = ""
        children: list[ListingQuery] = []
        if needs_split and query.depth < config.max_partition_depth:
            children, split_reason = _split_query(
                query=query,
                config=config,
                filter_settings=filter_settings_by_category.get(query.category_id, {}),
                property_type_choices=property_type_choices.get(query.category_id, ()),
                location_children_by_parent=location_children_by_parent,
                search_result=search_result,
            )
        status = "terminal"
        if children:
            status = "split"
            queue.extend(children)
        else:
            terminal_queries.append(query)

        assessed_total += 1
        assessed_this_run += 1
        status_counts[status] += 1
        plan_rows.append(
            {
                "endpoint": "search_plan",
                "scraped_at": scraped_at,
                "query_signature": query.signature,
                "query": _query_payload(query),
                "params": dict(params),
                "status": status,
                "split_reason": split_reason,
                "needs_split": needs_split,
                "terminal": status == "terminal",
                "depth": query.depth,
                **({"assessed_index": assessed_total} if include_assessed_index else {}),
                "total_count": total_count,
                "page_count": page_count,
                "listing_count_on_first_page": len(listings),
                "meta": meta,
            }
        )
        if (
            assessed_this_run <= 5
            or assessed_this_run % _QUERY_PLAN_LOG_INTERVAL == 0
            or (status == "split" and query.depth <= 1)
        ):
            _log_info(
                progress_log,
                (
                    "pf_listings: query planning chunk progress assessed_run=%s "
                    "assessed_total=%s queue=%s terminal=%s split=%s "
                    "last_signature=%s last_status=%s last_split=%s "
                    "last_total=%s last_pages=%s"
                ),
                assessed_this_run,
                assessed_total,
                len(queue),
                status_counts["terminal"],
                status_counts["split"],
                query.signature,
                status,
                split_reason,
                total_count,
                page_count,
            )
        if config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)

    if queue and assessed_total >= config.max_planned_queries:
        while queue:
            query = queue.popleft()
            status_counts["skipped_planning_limit"] += 1
            plan_rows.append(
                {
                    "endpoint": "search_plan",
                    "scraped_at": scraped_at,
                    "query_signature": query.signature,
                    "query": _query_payload(query),
                    "params": dict(query.params(page=1, sort=config.sort)),
                    "status": "skipped_planning_limit",
                    "split_reason": "max_planned_queries",
                    "needs_split": None,
                    "terminal": False,
                    "depth": query.depth,
                }
            )

    completed = not queue
    _log_info(
        progress_log,
        (
            "pf_listings: completed query planning chunk assessed_run=%s "
            "assessed_total=%s queue=%s terminal=%s split=%s fetch_error=%s "
            "skipped=%s plan_rows=%s completed=%s"
        ),
        assessed_this_run,
        assessed_total,
        len(queue),
        status_counts["terminal"],
        status_counts["split"],
        status_counts["fetch_error"],
        status_counts["skipped_planning_limit"],
        len(plan_rows),
        completed,
    )
    return QueryPlanResult(
        plan_rows=plan_rows,
        terminal_queries=terminal_queries,
        queue=queue,
        assessed_count=assessed_total,
        terminal_count=status_counts["terminal"],
        split_count=status_counts["split"],
        fetch_error_count=status_counts["fetch_error"],
        skipped_count=status_counts["skipped_planning_limit"],
        completed=completed,
    )


def _collect_listing_pages(
    *,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    terminal_queries: Sequence[ListingQuery],
    scraped_at: str,
    progress_log: Any,
    query_start_index: int = 0,
    page_start: int = 1,
) -> ListingPageCollectionResult:
    search_page_rows: list[dict[str, Any]] = []
    property_rows: list[dict[str, Any]] = []
    seen_properties: set[str] = set()
    pages_remaining = config.max_search_pages_per_run
    page_fetch_count = 0
    search_error_count = 0
    next_query_index = min(query_start_index, len(terminal_queries))
    next_page = max(page_start, 1)

    _log_info(
        progress_log,
        (
            "pf_listings: collecting listing pages terminal_queries=%s "
            "start_query_index=%s start_page=%s max_pages_per_run=%s"
        ),
        len(terminal_queries),
        query_start_index,
        page_start,
        config.max_search_pages_per_run,
    )
    for query_index in range(query_start_index, len(terminal_queries)):
        if pages_remaining <= 0:
            break
        query = terminal_queries[query_index]
        next_query_index = query_index
        page = max(page_start, 1) if query_index == query_start_index else 1
        next_page = page
        page_count = config.max_pages_per_query
        while page <= min(page_count, config.max_pages_per_query) and pages_remaining > 0:
            params = query.params(page=page, sort=config.sort)
            try:
                payload = listing_client.fetch_search_page(params=params)
            except Exception as exc:  # noqa: BLE001
                page_fetch_count += 1
                search_page_rows.append(
                    {
                        "endpoint": "search",
                        "scraped_at": scraped_at,
                        "query_signature": query.signature,
                        "query_index": query_index,
                        "query": _query_payload(query),
                        "params": dict(params),
                        "page": page,
                        "status": "search_error",
                        "listing_wrapper_count": 0,
                        "total_count": None,
                        "page_count": page_count,
                        "meta": {},
                        "error": str(exc),
                    }
                )
                search_error_count += 1
                _log_warning(
                    progress_log,
                    (
                        "pf_listings: listing page fetch error fetched_pages=%s "
                        "remaining_budget=%s query=%s query_page=%s error=%s"
                    ),
                    page_fetch_count,
                    max(pages_remaining - 1, 0),
                    query.signature,
                    page,
                    exc,
                )
                pages_remaining -= 1
                next_query_index = query_index + 1
                next_page = 1
                break
            search_result = _search_result(payload)
            meta = _search_meta(search_result)
            wrappers = _listing_wrappers(search_result)
            page_count = _page_count(search_result, fallback=page_count)
            page_fetch_count += 1
            pages_remaining -= 1
            page_row = {
                "endpoint": "search",
                "scraped_at": scraped_at,
                "query_signature": query.signature,
                "query_index": query_index,
                "query": _query_payload(query),
                "params": dict(params),
                "page": page,
                "status": "ok",
                "listing_wrapper_count": len(wrappers),
                "total_count": _total_count(search_result, fallback=len(wrappers)),
                "page_count": page_count,
                "meta": meta,
                "raw": search_result,
            }
            search_page_rows.append(page_row)
            for wrapper_index, wrapper in enumerate(wrappers, start=1):
                property_payload = _property_from_wrapper(wrapper)
                if property_payload is None:
                    continue
                property_key = _property_key(wrapper=wrapper, property_payload=property_payload)
                if property_key in seen_properties:
                    continue
                seen_properties.add(property_key)
                property_rows.append(
                    _property_row(
                        query=query,
                        page=page,
                        wrapper_index=wrapper_index,
                        property_key=property_key,
                        wrapper=wrapper,
                        property_payload=property_payload,
                        scraped_at=scraped_at,
                    )
                )
            if (
                page_fetch_count <= 5
                or page_fetch_count % _SEARCH_PAGE_LOG_INTERVAL == 0
                or pages_remaining == 1
            ):
                _log_info(
                    progress_log,
                    (
                        "pf_listings: listing page progress fetched_pages=%s "
                        "remaining_budget=%s query=%s query_page=%s wrappers=%s "
                        "distinct_properties=%s"
                    ),
                    page_fetch_count,
                    pages_remaining,
                    query.signature,
                    page,
                    len(wrappers),
                    len(property_rows),
                )
            if not wrappers:
                next_query_index = query_index + 1
                next_page = 1
                break
            page += 1
            next_query_index = query_index
            next_page = page
            if config.request_pause_seconds:
                time.sleep(config.request_pause_seconds)
        else:
            if page > min(page_count, config.max_pages_per_query):
                next_query_index = query_index + 1
                next_page = 1
    _log_info(
        progress_log,
        (
            "pf_listings: completed listing page collection pages=%s distinct_properties=%s "
            "next_query_index=%s next_page=%s completed=%s errors=%s"
        ),
        len(search_page_rows),
        len(property_rows),
        next_query_index,
        next_page,
        next_query_index >= len(terminal_queries),
        search_error_count,
    )
    return ListingPageCollectionResult(
        search_page_rows=search_page_rows,
        property_rows=property_rows,
        next_query_index=next_query_index,
        next_page=next_page,
        completed=next_query_index >= len(terminal_queries),
        fetched_pages=page_fetch_count,
        search_error_count=search_error_count,
    )


def _collect_detail_rows(
    *,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    property_rows: Sequence[dict[str, Any]],
    scraped_at: str,
    progress_log: Any,
) -> list[dict[str, Any]]:
    if not config.fetch_details:
        _log_info(progress_log, "pf_listings: detail collection disabled")
        return []

    detail_rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    detail_target = min(config.max_details_per_run, len(property_rows))
    _log_info(
        progress_log,
        "pf_listings: collecting detail pages candidate_properties=%s max_details=%s",
        len(property_rows),
        config.max_details_per_run,
    )
    for property_row in property_rows:
        if len(detail_rows) >= config.max_details_per_run:
            break
        details_path = _string_value(property_row.get("details_path"))
        if not details_path or details_path in seen_paths:
            continue
        seen_paths.add(details_path)
        try:
            payload = listing_client.fetch_detail(details_path=details_path)
            detail_payload = _property_detail_payload(payload)
        except Exception as exc:  # noqa: BLE001
            detail_rows.append(
                {
                    "endpoint": "plp_detail",
                    "scraped_at": scraped_at,
                    "listing_id": property_row.get("listing_id"),
                    "property_id": property_row.get("property_id"),
                    "property_key": property_row.get("property_key"),
                    "details_path": details_path,
                    "category_id": property_row.get("category_id"),
                    "location_id": property_row.get("location_id"),
                    "status": "detail_error",
                    "error": str(exc),
                }
            )
            if len(detail_rows) <= 5 or len(detail_rows) % _DETAIL_LOG_INTERVAL == 0:
                _log_info(
                    progress_log,
                    "pf_listings: detail progress fetched=%s target=%s listing_id=%s status=error",
                    len(detail_rows),
                    detail_target,
                    property_row.get("listing_id"),
                )
            if config.request_pause_seconds:
                time.sleep(config.request_pause_seconds)
            continue
        detail_rows.append(
            {
                "endpoint": "plp_detail",
                "scraped_at": scraped_at,
                "status": "ok",
                "listing_id": property_row.get("listing_id"),
                "property_id": property_row.get("property_id"),
                "property_key": property_row.get("property_key"),
                "details_path": details_path,
                "category_id": property_row.get("category_id"),
                "location_id": property_row.get("location_id"),
                "detail_property": detail_payload.get("property") if detail_payload else None,
                "raw": detail_payload or payload,
            }
        )
        if len(detail_rows) <= 5 or len(detail_rows) % _DETAIL_LOG_INTERVAL == 0:
            _log_info(
                progress_log,
                "pf_listings: detail progress fetched=%s target=%s listing_id=%s",
                len(detail_rows),
                detail_target,
                property_row.get("listing_id"),
            )
        if config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)
    _log_info(
        progress_log,
        "pf_listings: completed detail collection details=%s unique_paths=%s",
        len(detail_rows),
        len(seen_paths),
    )
    return detail_rows


def _collect_detail_rows_from_manifests(
    *,
    config: PropertyFinderListingsConfig,
    listing_client: PropertyFinderListingsClient,
    state_store: PropertyFinderListingsStateStore,
    scraped_at: str,
    progress_log: Any,
) -> DetailCollectionResult:
    manifest_keys = sorted(state_store.list_keys(prefix=config.manifest_prefix))
    detail_rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    source_property_row_count = 0
    source_property_invalid_row_count = 0
    next_manifest_index = min(config.detail_manifest_cursor, len(manifest_keys))
    next_row_index = config.detail_row_cursor

    _log_info(
        progress_log,
        (
            "pf_listings: collecting detail pages from manifests manifest_count=%s "
            "start_manifest_index=%s start_row_index=%s max_details=%s"
        ),
        len(manifest_keys),
        config.detail_manifest_cursor,
        config.detail_row_cursor,
        config.max_details_per_run,
    )
    for manifest_index in range(config.detail_manifest_cursor, len(manifest_keys)):
        manifest_key = manifest_keys[manifest_index]
        manifest = _read_manifest(state_store=state_store, manifest_key=manifest_key)
        file_entry = _manifest_file_entry(manifest, _PROPERTIES_FILE)
        if file_entry is None:
            next_manifest_index = manifest_index + 1
            next_row_index = 0
            continue
        source_key = _string_value(file_entry.get("s3_key"))
        if not source_key:
            raise ValueError(
                f"Property Finder properties file entry is missing s3_key: {manifest_key}"
            )
        property_rows, invalid_row_count = _read_jsonl_dicts_lenient(
            text=state_store.read_text(key=source_key),
            source_key=source_key,
        )
        if invalid_row_count:
            source_property_invalid_row_count += invalid_row_count
            _log_info(
                progress_log,
                "pf_listings: skipped invalid property JSONL rows count=%s source_key=%s",
                invalid_row_count,
                source_key,
            )
        source_property_row_count += len(property_rows)
        row_index = (
            config.detail_row_cursor if manifest_index == config.detail_manifest_cursor else 0
        )
        while row_index < len(property_rows):
            if len(detail_rows) >= config.max_details_per_run:
                return DetailCollectionResult(
                    detail_rows=detail_rows,
                    next_manifest_index=manifest_index,
                    next_row_index=row_index,
                    completed=False,
                    source_manifest_count=len(manifest_keys),
                    source_property_row_count=source_property_row_count,
                    source_property_invalid_row_count=source_property_invalid_row_count,
                )
            property_row = property_rows[row_index]
            row_index += 1
            details_path = _string_value(property_row.get("details_path"))
            if not details_path or details_path in seen_paths:
                next_manifest_index = manifest_index
                next_row_index = row_index
                continue
            seen_paths.add(details_path)
            try:
                payload = listing_client.fetch_detail(details_path=details_path)
                detail_payload = _property_detail_payload(payload)
                status = "ok"
                error = ""
            except Exception as exc:  # noqa: BLE001
                payload = {}
                detail_payload = {}
                status = "detail_error"
                error = str(exc)
            row = {
                "endpoint": "plp_detail",
                "scraped_at": scraped_at,
                "status": status,
                "listing_id": property_row.get("listing_id"),
                "property_id": property_row.get("property_id"),
                "property_key": property_row.get("property_key"),
                "details_path": details_path,
                "category_id": property_row.get("category_id"),
                "location_id": property_row.get("location_id"),
                "source_manifest_key": manifest_key,
                "source_properties_s3_key": source_key,
                "source_manifest_index": manifest_index,
                "source_row_index": row_index - 1,
            }
            if status == "ok":
                row["detail_property"] = detail_payload.get("property") if detail_payload else None
                row["raw"] = detail_payload or payload
            else:
                row["error"] = error
            detail_rows.append(row)
            next_manifest_index = manifest_index
            next_row_index = row_index
            if len(detail_rows) <= 5 or len(detail_rows) % _DETAIL_LOG_INTERVAL == 0:
                _log_info(
                    progress_log,
                    (
                        "pf_listings: detail manifest progress fetched=%s max_details=%s "
                        "manifest_index=%s row_index=%s listing_id=%s status=%s"
                    ),
                    len(detail_rows),
                    config.max_details_per_run,
                    manifest_index,
                    row_index - 1,
                    property_row.get("listing_id"),
                    status,
                )
            if config.request_pause_seconds:
                time.sleep(config.request_pause_seconds)
        next_manifest_index = manifest_index + 1
        next_row_index = 0

    _log_info(
        progress_log,
        (
            "pf_listings: completed detail manifest collection details=%s "
            "next_manifest_index=%s next_row_index=%s completed=%s"
        ),
        len(detail_rows),
        next_manifest_index,
        next_row_index,
        True,
    )
    return DetailCollectionResult(
        detail_rows=detail_rows,
        next_manifest_index=next_manifest_index,
        next_row_index=next_row_index,
        completed=True,
        source_manifest_count=len(manifest_keys),
        source_property_row_count=source_property_row_count,
        source_property_invalid_row_count=source_property_invalid_row_count,
    )


def _split_query(
    *,
    query: ListingQuery,
    config: PropertyFinderListingsConfig,
    filter_settings: dict[str, Any],
    property_type_choices: Sequence[dict[str, Any]],
    location_children_by_parent: Mapping[str, Sequence[str]],
    search_result: dict[str, Any],
) -> tuple[list[ListingQuery], str]:
    if config.split_by_property_type and query.property_type_id is None:
        property_type_ids = tuple(
            value
            for value in (_int_value(choice.get("value")) for choice in property_type_choices)
            if value is not None
        )
        if property_type_ids:
            return (
                [
                    ListingQuery(
                        category_id=query.category_id,
                        location_id=query.location_id,
                        property_type_id=property_type_id,
                        min_price=query.min_price,
                        max_price=query.max_price,
                        depth=query.depth + 1,
                        lineage=(*query.lineage, f"property_type:{property_type_id}"),
                    )
                    for property_type_id in property_type_ids
                ],
                "property_type",
            )

    if config.split_by_location:
        child_location_ids = tuple(
            location_id
            for location_id in location_children_by_parent.get(str(query.location_id), ())
            if location_id != str(query.location_id)
        )
        if child_location_ids:
            return (
                [
                    ListingQuery(
                        category_id=query.category_id,
                        location_id=location_id,
                        property_type_id=query.property_type_id,
                        bedroom=query.bedroom,
                        min_price=query.min_price,
                        max_price=query.max_price,
                        depth=query.depth + 1,
                        lineage=(*query.lineage, f"location:{location_id}"),
                    )
                    for location_id in child_location_ids
                ],
                "location",
            )

    if (
        config.split_by_bedrooms
        and query.category_id in PF_RESIDENTIAL_CATEGORY_IDS
        and query.bedroom is None
        and _bedroom_split_is_allowed(query, config=config)
        and _choice_rows(filter_settings, _BEDROOM_KEY)
    ):
        return (
            [
                ListingQuery(
                    category_id=query.category_id,
                    location_id=query.location_id,
                    property_type_id=query.property_type_id,
                    bedroom=bedroom,
                    min_price=query.min_price,
                    max_price=query.max_price,
                    depth=query.depth + 1,
                    lineage=(*query.lineage, f"bedroom:{bedroom}"),
                )
                for bedroom in config.bedroom_values
            ],
            "bedroom",
        )

    if config.split_by_price:
        bounds = _price_bounds(search_result=search_result, query=query)
        if bounds is not None:
            min_price, max_price = bounds
            if max_price > min_price:
                midpoint = (min_price + max_price) // 2
                if midpoint >= min_price and midpoint < max_price:
                    return (
                        [
                            ListingQuery(
                                category_id=query.category_id,
                                location_id=query.location_id,
                                property_type_id=query.property_type_id,
                                bedroom=query.bedroom,
                                min_price=min_price if min_price > 0 else None,
                                max_price=midpoint,
                                depth=query.depth + 1,
                                lineage=(*query.lineage, f"price_max:{midpoint}"),
                            ),
                            ListingQuery(
                                category_id=query.category_id,
                                location_id=query.location_id,
                                property_type_id=query.property_type_id,
                                bedroom=query.bedroom,
                                min_price=midpoint + 1,
                                max_price=max_price,
                                depth=query.depth + 1,
                                lineage=(*query.lineage, f"price_min:{midpoint + 1}"),
                            ),
                        ],
                        "price",
                    )
    return [], ""


def _bedroom_split_is_allowed(
    query: ListingQuery,
    *,
    config: PropertyFinderListingsConfig,
) -> bool:
    if query.property_type_id is None:
        return True
    return query.property_type_id in set(config.bedroom_eligible_property_type_ids)


def _property_row(
    *,
    query: ListingQuery,
    page: int,
    wrapper_index: int,
    property_key: str,
    wrapper: dict[str, Any],
    property_payload: dict[str, Any],
    scraped_at: str,
) -> dict[str, Any]:
    details_path = _details_path(wrapper=wrapper, property_payload=property_payload)
    location = property_payload.get("location")
    if not isinstance(location, dict):
        location = {}
    location_context = _location_context(property_payload=property_payload, location=location)
    return {
        "endpoint": "search",
        "scraped_at": scraped_at,
        "query_signature": query.signature,
        "query": _query_payload(query),
        "category_id": query.category_id,
        "location_id": query.location_id,
        "property_type_id": query.property_type_id,
        "bedroom": query.bedroom,
        "min_price": query.min_price,
        "max_price": query.max_price,
        "page": page,
        "wrapper_index": wrapper_index,
        "listing_id": _first_string(
            property_payload,
            wrapper,
            keys=("listing_id", "listingId", "id"),
        ),
        "property_id": _first_string(
            property_payload,
            wrapper,
            keys=("property_id", "propertyId"),
        ),
        "property_key": property_key,
        "reference": _first_string(property_payload, wrapper, keys=("reference", "reference_id")),
        "details_path": details_path,
        "share_url": _share_url(details_path=details_path, property_payload=property_payload),
        "title": _first_string(property_payload, wrapper, keys=("title", "name")),
        "type": property_payload.get("type"),
        "price": property_payload.get("price"),
        "size": property_payload.get("size"),
        "bedrooms": property_payload.get("bedrooms"),
        "bathrooms": property_payload.get("bathrooms"),
        "location_tree": property_payload.get("location_tree"),
        "location": location,
        **location_context,
        "latitude": _coordinate(location, "lat", "latitude"),
        "longitude": _coordinate(location, "lon", "lng", "longitude"),
        "is_available": property_payload.get("is_available"),
        "is_verified": property_payload.get("is_verified"),
        "is_featured": property_payload.get("is_featured"),
        "is_premium": property_payload.get("is_premium"),
        "agent": property_payload.get("agent"),
        "broker": property_payload.get("broker"),
        "client": property_payload.get("client"),
        "images": property_payload.get("images"),
        "raw_wrapper": wrapper,
        "raw_property": property_payload,
    }


def _location_context(
    *,
    property_payload: Mapping[str, Any],
    location: Mapping[str, Any],
) -> dict[str, Any]:
    location_tree = property_payload.get("location_tree")
    nodes = (
        [node for node in location_tree if isinstance(node, dict)]
        if isinstance(location_tree, list)
        else []
    )
    if not nodes and location:
        nodes = [dict(location)]

    ids_by_type: dict[str, str] = {}
    ordered_ids: list[str] = []
    ordered_names: list[str] = []
    for node in nodes:
        location_id = _first_node_value(node, "id", "location_id", "locationId")
        if location_id and location_id not in ordered_ids:
            ordered_ids.append(location_id)
        name = _first_node_value(node, "name", "full_name", "path_name")
        if name:
            ordered_names.append(name)
        raw_type = _first_node_value(node, "type", "location_type", "locationType", "level")
        normalized_type = _normalize_location_type(raw_type)
        if location_id and normalized_type and normalized_type not in ids_by_type:
            ids_by_type[normalized_type] = location_id

    leaf_location_id = (
        ordered_ids[-1]
        if ordered_ids
        else _first_node_value(
            location,
            "id",
            "location_id",
            "locationId",
        )
    )
    return {
        "listing_location_ids": ordered_ids,
        "listing_location_names": ordered_names,
        "city_location_id": ids_by_type.get("city"),
        "community_location_id": ids_by_type.get("community"),
        "subcommunity_location_id": ids_by_type.get("subcommunity"),
        "tower_location_id": ids_by_type.get("tower"),
        "building_location_id": ids_by_type.get("building") or ids_by_type.get("tower"),
        "leaf_location_id": leaf_location_id,
    }


def _first_node_value(node: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = node.get(key)
        if value is not None:
            return _string_value(value)
    return ""


def _normalize_location_type(value: str) -> str:
    normalized = value.lower().replace("_", "").replace("-", "").replace(" ", "")
    if normalized in {"city", "0"}:
        return "city"
    if normalized in {"community", "1"}:
        return "community"
    if normalized in {"subcommunity", "subcommunityname", "2"}:
        return "subcommunity"
    if normalized in {"tower", "building", "3", "4", "5"}:
        return "tower" if normalized == "tower" else "building"
    return normalized


def _property_type_choices(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _choice_rows(payload, _PROPERTY_TYPE_KEY)


def _choice_rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    filter_choices = payload.get("filterChoices")
    if not isinstance(filter_choices, dict):
        return []
    choices = filter_choices.get(key)
    if not isinstance(choices, list):
        return []
    return [
        choice
        for choice in choices
        if isinstance(choice, dict) and choice.get("value") not in ("", None)
    ]


def _location_attributes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Property Finder locations response.data must be an object")
    attributes = data.get("attributes")
    if attributes is None:
        return []
    if not isinstance(attributes, list) or not all(isinstance(item, dict) for item in attributes):
        raise ValueError("Property Finder locations response.data.attributes must be a list")
    return attributes


def _location_is_under_roots(
    *,
    location_id: str,
    path_ids: Sequence[str],
    root_ids: set[str],
) -> bool:
    return location_id in root_ids or any(root_id in path_ids for root_id in root_ids)


def _path_ids(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part for part in value.split(".") if part]


def _search_result(payload: dict[str, Any]) -> dict[str, Any]:
    page_props = payload.get("pageProps")
    if isinstance(page_props, dict):
        for key in ("searchResult", "initialSearchResult"):
            value = page_props.get(key)
            if isinstance(value, dict):
                return value
    for key in ("searchResult", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _empty_search_payload(*, http_status: int, url: str) -> dict[str, Any]:
    return {
        "pageProps": {
            "searchResult": {
                "listings": [],
                "meta": {
                    "total_count": 0,
                    "page_count": 0,
                    "page": 1,
                    "http_status": http_status,
                    "url": url,
                },
            }
        }
    }


def _search_meta(search_result: dict[str, Any]) -> dict[str, Any]:
    meta = search_result.get("meta")
    return meta if isinstance(meta, dict) else {}


def _listing_wrappers(search_result: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("listings", "results", "items", "properties"):
        value = search_result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _property_from_wrapper(wrapper: dict[str, Any]) -> dict[str, Any] | None:
    listing_type = _string_value(wrapper.get("listing_type") or wrapper.get("listingType"))
    property_payload = wrapper.get("property")
    if isinstance(property_payload, dict):
        if listing_type and listing_type != "property":
            return None
        return property_payload
    if _looks_like_property(wrapper):
        return wrapper
    return None


def _looks_like_property(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("price", "reference", "property_type", "listing_id"))


def _property_key(*, wrapper: dict[str, Any], property_payload: dict[str, Any]) -> str:
    for key in ("listing_id", "listingId", "id", "property_id", "propertyId", "reference"):
        value = _first_string(property_payload, wrapper, keys=(key,))
        if value:
            return f"{key}:{value}"
    details_path = _details_path(wrapper=wrapper, property_payload=property_payload)
    if details_path:
        return f"path:{details_path}"
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(property_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    )


def _property_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    page_props = payload.get("pageProps")
    if isinstance(page_props, dict):
        value = page_props.get("propertyResult")
        if isinstance(value, dict):
            return value
        value = page_props.get("property")
        if isinstance(value, dict):
            return {"property": value}
    value = payload.get("propertyResult")
    if isinstance(value, dict):
        return value
    return {}


def _total_count(search_result: dict[str, Any], *, fallback: int) -> int:
    meta = _search_meta(search_result)
    for container in (meta, search_result):
        for key in ("total_count", "totalCount", "total", "count"):
            value = _int_value(container.get(key))
            if value is not None and value >= 0:
                return value
    return fallback


def _page_count(search_result: dict[str, Any], *, fallback: int) -> int:
    meta = _search_meta(search_result)
    for container in (meta, search_result):
        for key in ("page_count", "pageCount", "pages", "total_pages", "totalPages"):
            value = _int_value(container.get(key))
            if value is not None and value >= 0:
                return value
    total_count = _total_count(search_result, fallback=0)
    per_page = _int_value(meta.get("per_page") or meta.get("perPage") or meta.get("page_size"))
    if total_count and per_page:
        return (total_count + per_page - 1) // per_page
    return fallback


def _price_bounds(
    *,
    search_result: dict[str, Any],
    query: ListingQuery,
) -> tuple[int, int] | None:
    if query.min_price is not None and query.max_price is not None:
        return query.min_price, query.max_price
    meta = _search_meta(search_result)
    candidates = [
        (meta.get("min_price"), meta.get("max_price")),
        (meta.get("price_min"), meta.get("price_max")),
        (meta.get("minPrice"), meta.get("maxPrice")),
    ]
    for key in ("price", "price_range", "min_max_price", "priceRange"):
        value = meta.get(key)
        if isinstance(value, dict):
            candidates.extend(
                [
                    (value.get("min"), value.get("max")),
                    (value.get("minimum"), value.get("maximum")),
                    (value.get("min_price"), value.get("max_price")),
                ]
            )
    for raw_min, raw_max in candidates:
        min_price = _int_value(raw_min)
        max_price = _int_value(raw_max)
        if min_price is not None and max_price is not None and max_price > min_price:
            return min_price, max_price
    return None


def _details_path(*, wrapper: dict[str, Any], property_payload: dict[str, Any]) -> str:
    for container in (property_payload, wrapper):
        path = _details_path_from_container(container)
        if path:
            return path
    return ""


def _details_path_from_container(container: Any) -> str:
    if isinstance(container, dict):
        for key in (
            "share_url",
            "property_url",
            "detail_url",
            "listing_url",
            "url",
            "path",
            "href",
        ):
            value = container.get(key)
            if isinstance(value, str):
                path = _normalize_details_path(value)
                if path:
                    return path
        for key in ("links", "link"):
            path = _details_path_from_container(container.get(key))
            if path:
                return path
    if isinstance(container, list):
        for item in container:
            path = _details_path_from_container(item)
            if path:
                return path
    return ""


def _normalize_details_path(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme and parsed.netloc:
        path = parsed.path
    else:
        path = candidate
    if _DETAILS_PATH_HTML_SUFFIX not in path:
        return ""
    if not any(segment in path for segment in _DETAILS_PATH_SEGMENTS):
        return ""
    return path


def _share_url(*, details_path: str, property_payload: dict[str, Any]) -> str:
    for key in ("share_url", "property_url", "detail_url", "listing_url", "url"):
        value = property_payload.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return details_path


def _coordinate(location: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in location:
            return location.get(key)
    coordinates = location.get("coordinates")
    if isinstance(coordinates, dict):
        for key in keys:
            if key in coordinates:
                return coordinates.get(key)
    return None


def _query_payload(query: ListingQuery) -> dict[str, Any]:
    return {
        "category_id": query.category_id,
        "location_id": query.location_id,
        "property_type_id": query.property_type_id,
        "bedroom": query.bedroom,
        "min_price": query.min_price,
        "max_price": query.max_price,
        "depth": query.depth,
        "lineage": list(query.lineage),
    }


def _listing_query_from_payload(payload: Mapping[str, Any]) -> ListingQuery:
    category_id = _int_value(payload.get("category_id"))
    location_id = _string_value(payload.get("location_id"))
    if category_id is None or not location_id:
        raise ValueError(f"Property Finder query payload is missing category/location: {payload}")
    lineage = payload.get("lineage")
    return ListingQuery(
        category_id=category_id,
        location_id=location_id,
        property_type_id=_int_value(payload.get("property_type_id")),
        bedroom=_int_value(payload.get("bedroom")),
        min_price=_int_value(payload.get("min_price")),
        max_price=_int_value(payload.get("max_price")),
        depth=_int_value(payload.get("depth")) or 0,
        lineage=tuple(_string_value(item) for item in lineage if item)
        if isinstance(lineage, list)
        else (),
    )


def _load_terminal_queries_from_plan(
    *,
    state_store: PropertyFinderListingsStateStore,
    plan_manifest_s3_key: str,
    plan_manifest_s3_keys: Sequence[str] = (),
) -> list[ListingQuery]:
    manifest_keys = tuple(
        dict.fromkeys(
            key.strip()
            for key in (*plan_manifest_s3_keys, plan_manifest_s3_key)
            if key and key.strip()
        )
    )
    if not manifest_keys:
        raise ValueError("Property Finder search mode requires at least one plan manifest")
    terminal_queries: list[ListingQuery] = []
    for manifest_key in manifest_keys:
        manifest = _read_manifest(state_store=state_store, manifest_key=manifest_key)
        plan_rows = _load_manifest_jsonl_rows(
            state_store=state_store,
            manifest=manifest,
            manifest_key=manifest_key,
            file_name=_QUERY_PLAN_FILE,
        )
        for row in plan_rows:
            if row.get("terminal") is not True:
                continue
            query_payload = row.get("query")
            if not isinstance(query_payload, dict):
                raise ValueError(
                    f"Property Finder terminal plan row is missing query: {manifest_key}"
                )
            terminal_queries.append(_listing_query_from_payload(query_payload))
    return terminal_queries


def _read_manifest(
    *,
    state_store: PropertyFinderListingsStateStore,
    manifest_key: str,
) -> dict[str, Any]:
    try:
        manifest = json.loads(state_store.read_text(key=manifest_key))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Property Finder manifest is not valid JSON: {manifest_key}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"Property Finder manifest must be an object: {manifest_key}")
    return manifest


def _load_manifest_jsonl_rows(
    *,
    state_store: PropertyFinderListingsStateStore,
    manifest: Mapping[str, Any],
    manifest_key: str,
    file_name: str,
) -> list[dict[str, Any]]:
    file_entry = _manifest_file_entry(manifest, file_name)
    if file_entry is None:
        raise ValueError(f"Property Finder manifest is missing {file_name}: {manifest_key}")
    source_key = _string_value(file_entry.get("s3_key"))
    if not source_key:
        raise ValueError(f"Property Finder manifest file entry is missing s3_key: {manifest_key}")
    rows = _read_jsonl_dicts(text=state_store.read_text(key=source_key), source_key=source_key)
    expected_count = file_entry.get("row_count")
    if expected_count is not None and int(expected_count) != len(rows):
        raise ValueError(
            f"Property Finder row_count mismatch for {source_key}: "
            f"manifest={expected_count} actual={len(rows)}"
        )
    return rows


def _manifest_file_entry(
    manifest: Mapping[str, Any],
    file_name: str,
) -> dict[str, Any] | None:
    files = manifest.get("files")
    if not isinstance(files, list):
        return None
    for entry in files:
        if not isinstance(entry, dict):
            continue
        if Path(_string_value(entry.get("path"))).name == file_name:
            return entry
    return None


def _read_jsonl_dicts(*, text: str, source_key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Property Finder JSONL row is invalid: {source_key}:{line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise ValueError(
                f"Property Finder JSONL row must be an object: {source_key}:{line_number}"
            )
        rows.append(row)
    return rows


def _read_jsonl_dicts_lenient(*, text: str, source_key: str) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    invalid_row_count = 0
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            invalid_row_count += 1
            continue
        if not isinstance(row, dict):
            invalid_row_count += 1
            continue
        rows.append(row)
    if invalid_row_count:
        logger.warning(
            "Property Finder skipped invalid JSONL rows source_key=%s count=%s",
            source_key,
            invalid_row_count,
        )
    return rows, invalid_row_count


def _next_data_from_page(*, page: Page, url: str) -> dict[str, Any]:
    text = page.locator("#__NEXT_DATA__").text_content(timeout=_NETWORK_IDLE_TIMEOUT_MS)
    if not text:
        raise RuntimeError(f"Property Finder page did not expose __NEXT_DATA__: {url}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Property Finder __NEXT_DATA__ was not valid JSON: {url}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Property Finder __NEXT_DATA__ must be an object: {url}")
    return payload


def _first_string(*containers: Mapping[str, Any], keys: Sequence[str]) -> str:
    for container in containers:
        for key in keys:
            value = container.get(key)
            if value is not None:
                return _string_value(value)
    return ""


def _int_value(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = re.sub(r"[^\d-]", "", value)
        if stripped and stripped not in {"-"}:
            return int(stripped)
    return None


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@contextmanager
def _browser_listing_client(
    *,
    config: PropertyFinderListingsConfig,
    playwright_factory: Callable[[], AbstractContextManager[Playwright]],
):
    with _virtual_display_if_needed(config), playwright_factory() as playwright:
        context = _new_context(playwright=playwright, config=config)
        try:
            yield PropertyFinderBrowserListingsClient(context=context, config=config)
        finally:
            browser = context.browser
            if browser is not None:
                browser.close()


def _new_context(*, playwright: Playwright, config: PropertyFinderListingsConfig) -> BrowserContext:
    launch_kwargs: dict[str, Any] = {
        "headless": config.headless,
        "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    }
    executable_path = _resolve_browser_executable(config.chrome_path)
    if executable_path:
        launch_kwargs["executable_path"] = executable_path
    browser = playwright.chromium.launch(**launch_kwargs)
    context_kwargs: dict[str, Any] = {"user_agent": _USER_AGENT}
    if config.storage_state_path.strip():
        context_kwargs["storage_state"] = config.storage_state_path
    context = browser.new_context(**context_kwargs)
    if config.block_media_requests:
        context.route(
            "**/*",
            lambda route, request: (
                route.abort()
                if request.resource_type in _BLOCKED_RESOURCE_TYPES
                else route.continue_()
            ),
        )
    return context


def _resolve_browser_executable(chrome_path: str) -> str | None:
    candidate = chrome_path.strip()
    if candidate:
        resolved = shutil.which(candidate) if "/" not in candidate else candidate
        if resolved and Path(resolved).exists():
            return resolved
        raise FileNotFoundError(f"Property Finder browser executable not found: {chrome_path}")

    for name in _DEFAULT_CHROME_CANDIDATES:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


@contextmanager
def _virtual_display_if_needed(config: PropertyFinderListingsConfig) -> Iterator[None]:
    if config.headless or os.environ.get("DISPLAY"):
        yield
        return
    if not shutil.which("Xvfb"):
        raise RuntimeError(
            "Property Finder headful browser requested but DISPLAY is unset and Xvfb is not installed"
        )

    process: subprocess.Popen | None = None
    old_display = os.environ.get("DISPLAY")
    display = ""
    for display_number in range(90, 110):
        candidate = f":{display_number}"
        if Path(f"/tmp/.X{display_number}-lock").exists():
            continue
        process = subprocess.Popen(
            ["Xvfb", candidate, "-screen", "0", "1366x768x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)
        if process.poll() is None:
            display = candidate
            break
        process = None

    if process is None or not display:
        raise RuntimeError(
            "Property Finder headful browser requested but Xvfb could not be started"
        )

    logger.info("Property Finder: started virtual display %s for headful browser", display)
    os.environ["DISPLAY"] = display
    try:
        yield
    finally:
        if old_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = old_display
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.info(message, *args)


def _log_warning(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.warning(message, *args)


def _headers() -> dict[str, str]:
    return {
        "accept": "application/json,text/plain,*/*",
        "user-agent": _USER_AGENT,
    }
