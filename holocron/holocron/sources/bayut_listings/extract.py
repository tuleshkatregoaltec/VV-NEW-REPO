"""Browser-based Bayut listing-card extraction with explicit CAPTCHA handling."""

from __future__ import annotations

import contextlib
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from holocron.contracts import RawFile, RawRelease
from holocron.platform.execution import build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.platform.raw_files import write_jsonl_raw_file as _write_jsonl_raw_file
from holocron.sources.bayut_listings.source import BayutListingsConfig, SOURCE

logger = logging.getLogger(__name__)

_PAGES_FILE = "bayut_listing_search_pages.jsonl"
_LISTINGS_FILE = "bayut_listing_properties.jsonl"
_DETAIL_URL_RE = re.compile(r"/property/details-(?P<listing_id>\d+)\.html", re.IGNORECASE)
_PRICE_RE = re.compile(r"AED\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_SIZE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*sq\.?\s*ft", re.IGNORECASE)
_CAPTCHA_MARKERS = ("captchachallenge", "hcaptcha", "captcha challenge", "security check | bayut")
_BLOCKED_RESOURCE_TYPES = frozenset({"font", "image", "media"})


class BayutAccessBlockedError(RuntimeError):
    """Raised when Bayut presents an access challenge instead of listings."""


class BayutListingsClient(Protocol):
    def fetch_search_page(self, *, search_path: str, page: int) -> "BayutSearchPage": ...


@dataclass(frozen=True, slots=True)
class BayutSearchPage:
    requested_url: str
    final_url: str
    status_code: int
    html: str
    cards: tuple[dict[str, str], ...]


class BayutBrowserListingsClient:
    def __init__(self, *, context: BrowserContext, config: BayutListingsConfig) -> None:
        self._context = context
        self._config = config
        self._page: Page | None = None

    def fetch_search_page(self, *, search_path: str, page: int) -> BayutSearchPage:
        requested_url = _search_url(
            base_url=self._config.base_url,
            search_path=search_path,
            page_number=page,
        )
        browser_page = self._page_or_new()
        response = browser_page.goto(
            requested_url,
            wait_until="domcontentloaded",
            timeout=int(self._config.timeout_seconds * 1000),
        )
        browser_page.wait_for_timeout(500)
        html = browser_page.content()
        final_url = browser_page.url
        if _is_captcha_page(final_url=final_url, html=html):
            raise BayutAccessBlockedError(
                "Bayut presented a CAPTCHA challenge instead of listing results. "
                "Use a permitted session or an authorised data feed; this collector "
                "does not attempt to bypass access controls."
            )
        if response is None or response.status >= 400:
            status = response.status if response is not None else 0
            raise RuntimeError(f"Bayut search failed status={status} url={requested_url}")
        cards = tuple(_listing_cards(browser_page))
        outcome = _validate_search_page(
            requested_url=requested_url,
            final_url=final_url,
            cards=cards,
            body_text=browser_page.locator("body").inner_text(),
            title=browser_page.title(),
        )
        if outcome == "captcha":
            raise BayutAccessBlockedError("Bayut presented a security check instead of listings")
        if outcome != "ok":
            raise RuntimeError(f"Bayut search failed outcome={outcome} url={requested_url}")
        return BayutSearchPage(
            requested_url=requested_url,
            final_url=final_url,
            status_code=response.status if response is not None else 0,
            html=html,
            cards=cards,
        )

    def _page_or_new(self) -> Page:
        if self._page is None or self._page.is_closed():
            self._page = self._context.new_page()
        return self._page


def extract_release(
    output_dir: str | Path,
    *,
    config: BayutListingsConfig | dict[str, Any],
    now: datetime | None = None,
    listing_client: BayutListingsClient | None = None,
    playwright_factory: Callable[[], AbstractContextManager[Playwright]] = sync_playwright,
    progress_log: Any | None = None,
) -> RawRelease:
    parsed_config = (
        config
        if isinstance(config, BayutListingsConfig)
        else BayutListingsConfig.model_validate(config)
    )
    if parsed_config.storage_state_path and not Path(parsed_config.storage_state_path).exists():
        raise FileNotFoundError(
            f"Bayut storage state not found: {parsed_config.storage_state_path}"
        )
    current_time = now or utc_now()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    log = progress_log or logger

    with contextlib.ExitStack() as stack:
        if listing_client is None:
            listing_client = stack.enter_context(
                _browser_listing_client(config=parsed_config, playwright_factory=playwright_factory)
            )
        page_rows, listing_rows, stopped_early = _collect_pages(
            config=parsed_config,
            listing_client=listing_client,
            scraped_at=current_time.isoformat(),
            progress_log=log,
        )

    files: tuple[RawFile, ...] = (
        _write_jsonl_raw_file(output_path / _PAGES_FILE, page_rows),
        _write_jsonl_raw_file(output_path / _LISTINGS_FILE, listing_rows),
    )
    return build_raw_release(
        source=SOURCE,
        files=files,
        run_id=new_run_id(current_time),
        now=current_time,
        metadata={
            "config": safe_config_metadata(parsed_config),
            "search_path_count": len(parsed_config.search_paths),
            "search_page_count": len(page_rows),
            "property_row_count": len(listing_rows),
            "start_page": parsed_config.start_page,
            "stopped_early": stopped_early,
            "coverage_status": "bounded_search_paths_not_coverage_certified",
        },
    )


def _collect_pages(
    *,
    config: BayutListingsConfig,
    listing_client: BayutListingsClient,
    scraped_at: str,
    progress_log: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    page_rows: list[dict[str, Any]] = []
    listings_by_id: dict[str, dict[str, Any]] = {}
    stopped_early = False
    for search_path in config.search_paths:
        seen_ids_for_path: set[str] = set()
        for page_number in range(
            config.start_page, config.start_page + config.max_pages_per_search
        ):
            result = listing_client.fetch_search_page(
                search_path=search_path,
                page=page_number,
            )
            listing_rows = _listing_rows(
                cards=result.cards,
                search_path=search_path,
                page=page_number,
                scraped_at=scraped_at,
            )
            ids = {row["listing_id"] for row in listing_rows}
            page_rows.append(
                {
                    "endpoint": "bayut_search_page",
                    "scraped_at": scraped_at,
                    "search_path": search_path,
                    "page": page_number,
                    "requested_url": result.requested_url,
                    "final_url": result.final_url,
                    "status_code": result.status_code,
                    "card_count": len(result.cards),
                    "listing_count": len(listing_rows),
                    "raw_html": result.html,
                }
            )
            for row in listing_rows:
                listings_by_id.setdefault(row["listing_id"], row)
            _log_info(
                progress_log,
                "bayut_listings: path=%s page=%s cards=%s listings=%s distinct=%s",
                search_path,
                page_number,
                len(result.cards),
                len(listing_rows),
                len(listings_by_id),
            )
            if not ids or ids.issubset(seen_ids_for_path):
                stopped_early = True
                break
            seen_ids_for_path.update(ids)
            if config.request_pause_seconds:
                time.sleep(config.request_pause_seconds)
    return page_rows, list(listings_by_id.values()), stopped_early


def _listing_rows(
    *,
    cards: Sequence[Mapping[str, str]],
    search_path: str,
    page: int,
    scraped_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, card in enumerate(cards):
        listing_url = str(card.get("listing_url") or "")
        match = _DETAIL_URL_RE.search(listing_url)
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
                "price_aed": _number_from_match(_PRICE_RE.search(text)),
                "size_sqft": _number_from_match(_SIZE_RE.search(text)),
                "card_text": text,
                "raw_card": dict(card),
            }
        )
    return rows


def _listing_cards(page: Page) -> list[dict[str, str]]:
    return page.locator("article").evaluate_all(
        """articles => articles.map((article) => {
            if (article.closest('[aria-label="Off-Plan properties rail"], '
                + '[aria-label="Off plan list"]')) return null;
            const link = [...article.querySelectorAll('a[href]')]
                .find((anchor) => /\\/property\\/details-\\d+\\.html/i.test(anchor.href));
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


def _validate_search_page(
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


def _search_url(*, base_url: str, search_path: str, page_number: int) -> str:
    if page_number < 1:
        raise ValueError("page_number must be at least 1")
    absolute = urljoin(f"{base_url.rstrip('/')}/", search_path.lstrip("/"))
    parts = urlsplit(absolute)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "page"
    ]
    path = f"{parts.path.rstrip('/')}/"
    if re.search(r"/page-\d+/$", path, re.IGNORECASE):
        raise ValueError("search path must not contain a page cursor")
    if page_number > 1:
        path += f"page-{page_number}/"
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def _is_captcha_page(*, final_url: str, html: str) -> bool:
    haystack = f"{final_url}\n{html[:20000]}".lower()
    return any(marker in haystack for marker in _CAPTCHA_MARKERS)


def _number_from_match(match: re.Match[str] | None) -> int | float | None:
    if match is None:
        return None
    try:
        value = match.group(1).replace(",", "")
        return float(value) if "." in value else int(value)
    except ValueError:
        return None


@contextlib.contextmanager
def _browser_listing_client(
    *,
    config: BayutListingsConfig,
    playwright_factory: Callable[[], AbstractContextManager[Playwright]],
):
    with playwright_factory() as playwright:
        launch_kwargs: dict[str, Any] = {"headless": config.headless}
        if config.chrome_path:
            launch_kwargs["executable_path"] = config.chrome_path
        browser = playwright.chromium.launch(**launch_kwargs)
        context_kwargs: dict[str, Any] = {}
        if config.storage_state_path:
            context_kwargs["storage_state"] = config.storage_state_path
        context = browser.new_context(**context_kwargs)
        if config.block_media_requests:
            context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in _BLOCKED_RESOURCE_TYPES
                    else route.continue_()
                ),
            )
        try:
            yield BayutBrowserListingsClient(context=context, config=config)
        finally:
            context.close()
            browser.close()


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    method = getattr(progress_log, "info", None)
    if callable(method):
        method(message, *args)
