from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import BrowserContext, Page, Playwright, TimeoutError, sync_playwright
from twocaptcha import TwoCaptcha

from holocron.contracts import RawFile, RawRelease
from holocron.platform.execution import build_raw_file, build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.sources.dxbi.source import (
    DXBI_BASE_URL,
    DateSlice,
    DxbiConfig,
    SOURCE,
    build_date_slices,
)

logger = logging.getLogger(__name__)

SALE_REGION_SELECTOR = "#soldhistory"
RENTAL_REGION_SELECTOR = "#rentHistory"
SALE_TABLE_SELECTOR = "#report_table_soldhistory"
RENTAL_TABLE_SELECTOR = "#report_table_rentHistory"
PAGINATION_SELECTOR = ".t-Report-paginationText"
DXBI_RENTAL_MAP_URL = "https://dxbinteract.com/rental-map/"
HEATMAP_BASE_URL = "https://microservices.dxbinteract.com/heatmap"
FAM_MAP_BUILDING_URL = "https://fam-erp.com/property/xd/map/buildings"
_HEATMAP_SIGNATURE_SECRET = "6503d1b8c90fd5dea060ae7331e3139f"
_HEATMAP_SIGNATURE_MODULUS = int(
    "e7955dbe35d19560331671fc521e63c579689a4c417626e1bd0f9ca695448c9f85d903dc9"
    "e4f8fee9706543677adf359fb94b47229b2fa3b3b34754b08ac5253715341ef53445346e"
    "59f180c7680c22098e31fe2baac6cf9880c65cb74f63dfb5788a8a7db006296dbfea1d"
    "95050dd60030e0fd44980ca288b1b25b583c49b15",
    16,
)
_HEATMAP_SIGNATURE_EXPONENT = 65537
PAGINATION_CALL_PATTERN = re.compile(
    r"apex\.widget\.report\.paginate\('(?P<region_id>[^']+)',\s*'(?P<checksum>[^']+)',\s*\{"
    r"min:(?P<min>\d+),max:(?P<max>\d+),fetched:(?P<fetched>\d+)\}\);"
)


def load_page_urls(
    *, page_urls_text: str, page_urls_file: str, max_pages: int | None = None
) -> list[str]:
    urls: list[str] = []
    for raw_line in page_urls_text.splitlines():
        line = raw_line.strip()
        if line:
            urls.append(line)
    if page_urls_file.strip():
        for raw_line in Path(page_urls_file).read_text().splitlines():
            line = raw_line.strip()
            if line:
                urls.append(line)
    if not urls:
        urls.append(DXBI_BASE_URL)

    deduped = list(dict.fromkeys(urls))
    if max_pages is not None:
        return deduped[:max_pages]
    return deduped


def extract_release(
    output_dir: str | Path,
    *,
    config: DxbiConfig | dict,
    now: datetime | None = None,
    page_scraper: Callable[..., list[dict]] | None = None,
    playwright_factory: Callable[[], AbstractContextManager[Playwright]] = sync_playwright,
    progress_log: Any | None = None,
) -> RawRelease:
    parsed_config = config if isinstance(config, DxbiConfig) else DxbiConfig.model_validate(config)
    log = progress_log or logger
    if (
        parsed_config.storage_state_path.strip()
        and not Path(parsed_config.storage_state_path).exists()
    ):
        raise FileNotFoundError(f"DXBI storage state not found: {parsed_config.storage_state_path}")
    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    slices = build_date_slices(parsed_config, today=current_time.date())
    urls = load_page_urls(
        page_urls_text=parsed_config.page_urls,
        page_urls_file=parsed_config.page_urls_file,
        max_pages=parsed_config.max_pages,
    )

    release_metadata: dict[str, Any] = {
        "config": safe_config_metadata(parsed_config),
        "slice_count": len(slices),
    }
    if page_scraper is not None:
        files = _extract_with_scraper(
            output_path=output_path,
            run_id=run_id,
            current_time=current_time,
            urls=urls,
            date_slices=slices,
            page_scraper=page_scraper,
            config=parsed_config,
        )
    elif parsed_config.scrape_mode == "report_tables":
        files = _extract_with_playwright(
            output_path=output_path,
            run_id=run_id,
            current_time=current_time,
            urls=urls,
            date_slices=slices,
            config=parsed_config,
            playwright_factory=playwright_factory,
        )
    elif parsed_config.scrape_mode == "both":
        heatmap_files, heatmap_metadata = _extract_comprehensive_with_playwright(
            output_path=output_path,
            run_id=run_id,
            current_time=current_time,
            config=parsed_config,
            playwright_factory=playwright_factory,
            progress_log=log,
        )
        table_files = _extract_with_playwright(
            output_path=output_path,
            run_id=run_id,
            current_time=current_time,
            urls=urls,
            date_slices=slices,
            config=parsed_config,
            playwright_factory=playwright_factory,
        )
        files = (*heatmap_files, *table_files)
        release_metadata.update(heatmap_metadata)
    else:
        files, heatmap_metadata = _extract_comprehensive_with_playwright(
            output_path=output_path,
            run_id=run_id,
            current_time=current_time,
            config=parsed_config,
            playwright_factory=playwright_factory,
            progress_log=log,
        )
        release_metadata.update(heatmap_metadata)
    return build_raw_release(
        source=SOURCE,
        files=files,
        run_id=run_id,
        now=current_time,
        metadata=release_metadata,
    )


def _collect_all_slices(
    *,
    output_path: Path,
    urls: list[str],
    date_slices: Iterable[DateSlice],
    collect_rows: Callable[[str, DateSlice], list[dict]],
) -> tuple[RawFile, ...]:
    files = []
    for date_slice in date_slices:
        rows: list[dict] = []
        for url in urls:
            rows.extend(collect_rows(url, date_slice))
        files.append(_write_slice_file(output_path=output_path, date_slice=date_slice, rows=rows))
    return tuple(files)


def _extract_with_scraper(
    *,
    output_path: Path,
    run_id: str,
    current_time: datetime,
    urls: list[str],
    date_slices: Iterable[DateSlice],
    page_scraper: Callable[..., list[dict]],
    config: DxbiConfig,
) -> tuple[RawFile, ...]:
    scraped_at = current_time.isoformat()

    def collect(url: str, date_slice: DateSlice) -> list[dict]:
        return page_scraper(
            url=url, date_slice=date_slice, run_id=run_id, config=config, scraped_at=scraped_at
        )

    return _collect_all_slices(
        output_path=output_path, urls=urls, date_slices=date_slices, collect_rows=collect
    )


def _extract_with_playwright(
    *,
    output_path: Path,
    run_id: str,
    current_time: datetime,
    urls: list[str],
    date_slices: Iterable[DateSlice],
    config: DxbiConfig,
    playwright_factory: Callable[[], AbstractContextManager[Playwright]],
) -> tuple[RawFile, ...]:
    scraped_at = current_time.isoformat()
    with _virtual_display_if_needed(config), playwright_factory() as playwright:
        browser_context = _new_context(playwright=playwright, config=config)
        try:

            def collect(url: str, date_slice: DateSlice) -> list[dict]:
                return _scrape_url_slice(
                    context=browser_context,
                    url=url,
                    date_slice=date_slice,
                    run_id=run_id,
                    scraped_at=scraped_at,
                    config=config,
                )

            return _collect_all_slices(
                output_path=output_path, urls=urls, date_slices=date_slices, collect_rows=collect
            )
        finally:
            browser = browser_context.browser
            if browser is not None:
                browser.close()


def _extract_comprehensive_with_playwright(
    *,
    output_path: Path,
    run_id: str,
    current_time: datetime,
    config: DxbiConfig,
    playwright_factory: Callable[[], AbstractContextManager[Playwright]],
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    scraped_at = current_time.isoformat()
    with _virtual_display_if_needed(config), playwright_factory() as playwright:
        browser_context = _new_context(playwright=playwright, config=config)
        page = browser_context.new_page()
        try:
            _log_info(progress_log, "dxbi: opening rental map for comprehensive scrape")
            page.goto(DXBI_RENTAL_MAP_URL, wait_until="domcontentloaded", timeout=120000)
            try:
                page.wait_for_load_state("networkidle", timeout=45000)
            except TimeoutError:
                page.wait_for_timeout(8000)
            _maybe_solve_captcha(page=page, api_key=config.twocaptcha_api_key)
            return _extract_heatmap_files(
                output_path=output_path,
                run_id=run_id,
                scraped_at=scraped_at,
                page=page,
                config=config,
                progress_log=progress_log,
            )
        finally:
            page.close()
            browser = browser_context.browser
            if browser is not None:
                browser.close()


def _extract_heatmap_files(
    *,
    output_path: Path,
    run_id: str,
    scraped_at: str,
    page: Page,
    config: DxbiConfig,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    rental_sink = _JsonlSink(output_path / "dxbi_heatmap_rental_buildings.jsonl")
    detail_sink = _JsonlSink(output_path / "dxbi_heatmap_buildings.jsonl")
    status_sink = _JsonlSink(output_path / "dxbi_heatmap_building_statuses.jsonl")
    chessboard_sink = _JsonlSink(output_path / "dxbi_heatmap_chessboards.jsonl")
    fam_sink = _JsonlSink(output_path / "dxbi_fam_map_buildings.jsonl")
    error_sink = _JsonlSink(output_path / "dxbi_heatmap_errors.jsonl")

    unique_buildings: dict[str, dict[str, Any]] = {}
    query_count = 0
    _log_info(
        progress_log,
        "dxbi: heatmap query matrix property_types=%s bedrooms=%s",
        ",".join(config.heatmap_property_types),
        ",".join(config.heatmap_bedrooms),
    )
    for query in _heatmap_rental_queries(config):
        query_count += 1
        response = _heatmap_fetch_json(
            page=page,
            url=f"{HEATMAP_BASE_URL}/api/v1/rentals",
            method="POST",
            body=query,
            signed=True,
            timeout_seconds=config.heatmap_fetch_timeout_seconds,
        )
        if response["status"] >= 400 or not isinstance(response["payload"], list):
            error_sink.write(_response_row("heatmap_rentals", run_id, scraped_at, response, query))
            _log_warning(
                progress_log,
                "dxbi: rentals query failed status=%s query=%s",
                response["status"],
                query,
            )
            _pause_heatmap(page=page, config=config)
            continue

        rows = response["payload"]
        for item in rows:
            location_id = str(item.get("location_id") or "").strip()
            rental_sink.write(
                {
                    "endpoint": "heatmap_rentals",
                    "query": query,
                    "location_id": location_id,
                    "raw": item,
                    "_run_id": run_id,
                    "_scraped_at": scraped_at,
                }
            )
            if location_id and location_id not in unique_buildings:
                unique_buildings[location_id] = item
        _log_info(
            progress_log,
            "dxbi: rentals query %s returned rows=%s unique_buildings=%s",
            query,
            len(rows),
            len(unique_buildings),
        )
        _pause_heatmap(page=page, config=config)

    building_ids = list(unique_buildings)
    if config.max_heatmap_buildings is not None:
        building_ids = building_ids[: config.max_heatmap_buildings]
    _log_info(
        progress_log,
        "dxbi: fetching per-building payloads count=%s discovered=%s",
        len(building_ids),
        len(unique_buildings),
    )

    detail_errors = 0
    for index, location_id in enumerate(building_ids, start=1):
        seed = unique_buildings[location_id]
        if config.include_heatmap_building_details:
            response = _heatmap_fetch_json(
                page=page,
                url=f"{HEATMAP_BASE_URL}/api/v1/building/{location_id}",
                method="GET",
                signed=True,
                timeout_seconds=config.heatmap_fetch_timeout_seconds,
            )
            _write_endpoint_response(
                sink=detail_sink,
                error_sink=error_sink,
                endpoint="heatmap_building",
                run_id=run_id,
                scraped_at=scraped_at,
                response=response,
                location_id=location_id,
                seed=seed,
            )
            detail_errors += int(response["status"] >= 400)
            _pause_heatmap(page=page, config=config)

        if config.include_heatmap_building_status:
            response = _heatmap_fetch_json(
                page=page,
                url=f"{HEATMAP_BASE_URL}/api/v1/building-status/{location_id}",
                method="GET",
                signed=True,
                timeout_seconds=config.heatmap_fetch_timeout_seconds,
            )
            _write_endpoint_response(
                sink=status_sink,
                error_sink=error_sink,
                endpoint="heatmap_building_status",
                run_id=run_id,
                scraped_at=scraped_at,
                response=response,
                location_id=location_id,
                seed=seed,
            )
            detail_errors += int(response["status"] >= 400)
            _pause_heatmap(page=page, config=config)

        if config.include_heatmap_chessboard:
            response = _heatmap_fetch_json(
                page=page,
                url=f"{HEATMAP_BASE_URL}/api/v1/chessboard/{location_id}",
                method="GET",
                signed=True,
                timeout_seconds=config.heatmap_fetch_timeout_seconds,
            )
            _write_endpoint_response(
                sink=chessboard_sink,
                error_sink=error_sink,
                endpoint="heatmap_chessboard",
                run_id=run_id,
                scraped_at=scraped_at,
                response=response,
                location_id=location_id,
                seed=seed,
            )
            detail_errors += int(response["status"] >= 400)
            _pause_heatmap(page=page, config=config)

        if config.include_fam_map_buildings:
            response = _heatmap_fetch_json(
                page=page,
                url=f"{FAM_MAP_BUILDING_URL}?building_id={location_id}",
                method="GET",
                signed=False,
                timeout_seconds=config.heatmap_fetch_timeout_seconds,
            )
            _write_endpoint_response(
                sink=fam_sink,
                error_sink=error_sink,
                endpoint="fam_map_building",
                run_id=run_id,
                scraped_at=scraped_at,
                response=response,
                location_id=location_id,
                seed=seed,
            )
            detail_errors += int(response["status"] >= 400)
            _pause_heatmap(page=page, config=config)

        if index == 1 or index % config.heatmap_progress_interval == 0:
            _log_info(
                progress_log,
                "dxbi: building payload progress %s/%s errors=%s",
                index,
                len(building_ids),
                detail_errors,
            )

    sinks = (rental_sink, detail_sink, status_sink, chessboard_sink, fam_sink, error_sink)
    all_files = tuple(sink.close() for sink in sinks)
    files = tuple(file for file in all_files if file.row_count and file.row_count > 0)
    if rental_sink.row_count == 0:
        raise RuntimeError("DXBI comprehensive heatmap scrape produced zero rental building rows")
    metadata = {
        "scrape_mode": "comprehensive",
        "heatmap_query_count": query_count,
        "heatmap_rental_building_rows": rental_sink.row_count,
        "heatmap_unique_buildings_discovered": len(unique_buildings),
        "heatmap_buildings_attempted": len(building_ids),
        "heatmap_building_rows": detail_sink.row_count,
        "heatmap_building_status_rows": status_sink.row_count,
        "heatmap_chessboard_rows": chessboard_sink.row_count,
        "fam_map_building_rows": fam_sink.row_count,
        "heatmap_error_rows": error_sink.row_count,
    }
    _log_info(progress_log, "dxbi: comprehensive scrape metadata=%s", metadata)
    return files, metadata


class _JsonlSink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = path.open("wb")
        self._hasher = hashlib.sha256()
        self._size = 0
        self.row_count = 0

    def write(self, row: dict[str, Any]) -> None:
        line = (json.dumps(row, sort_keys=True) + "\n").encode()
        self._handle.write(line)
        self._hasher.update(line)
        self._size += len(line)
        self.row_count += 1

    def close(self) -> RawFile:
        if not self._handle.closed:
            self._handle.close()
        return build_raw_file(
            path=self.path,
            sha256=self._hasher.hexdigest(),
            size_bytes=self._size,
            row_count=self.row_count,
            content_type="application/x-ndjson",
        )


def _heatmap_rental_queries(config: DxbiConfig) -> list[dict[str, Any]]:
    return [
        {
            "Area": 0,
            "Location": 0,
            "Type": property_type,
            "Bedrooms": bedroom,
            "RentalRange": {"Min": None, "Max": None},
        }
        for property_type in config.heatmap_property_types
        for bedroom in config.heatmap_bedrooms
    ]


def _heatmap_fetch_json(
    *,
    page: Page,
    url: str,
    method: str,
    body: dict[str, Any] | None = None,
    signed: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    signature = _heatmap_client_signature() if signed else ""
    return page.evaluate(
        """
        async ({ url, method, body, signature, timeoutMs }) => {
            const headers = {};
            if (signature) headers['Client-Signature'] = signature;
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeoutMs);
            const options = { method, headers, signal: controller.signal };
            if (body !== null) {
                headers['Content-Type'] = 'application/json';
                options.body = JSON.stringify(body);
            }
            try {
                const response = await fetch(url, options);
                const text = await response.text();
                let payload = null;
                try {
                    payload = JSON.parse(text);
                } catch (error) {
                    payload = null;
                }
                return {
                    url,
                    method,
                    status: response.status,
                    content_type: response.headers.get('content-type') || '',
                    payload,
                    text: payload === null ? text.slice(0, 2000) : '',
                };
            } catch (error) {
                return {
                    url,
                    method,
                    status: 599,
                    content_type: '',
                    payload: null,
                    text: `fetch_error: ${error.name || 'Error'}: ${error.message || ''}`,
                };
            } finally {
                clearTimeout(timer);
            }
        }
        """,
        {
            "url": url,
            "method": method,
            "body": body,
            "signature": signature,
            "timeoutMs": int(timeout_seconds * 1000),
        },
    )


def _heatmap_client_signature(*, timestamp: int | None = None) -> str:
    message = f"{_HEATMAP_SIGNATURE_SECRET}:{timestamp or int(time.time())}".encode("utf-8")
    key_size = (_HEATMAP_SIGNATURE_MODULUS.bit_length() + 7) // 8
    max_message_size = key_size - 11
    if len(message) > max_message_size:
        raise ValueError("DXBI heatmap client-signature payload is too large")
    padding_length = key_size - len(message) - 3
    padding = bytearray()
    while len(padding) < padding_length:
        byte = secrets.randbelow(255) + 1
        padding.append(byte)
    encoded_message = b"\x00\x02" + bytes(padding) + b"\x00" + message
    encrypted = pow(
        int.from_bytes(encoded_message, "big"),
        _HEATMAP_SIGNATURE_EXPONENT,
        _HEATMAP_SIGNATURE_MODULUS,
    )
    return base64.b64encode(encrypted.to_bytes(key_size, "big")).decode("ascii")


def _response_row(
    endpoint: str,
    run_id: str,
    scraped_at: str,
    response: dict[str, Any],
    request_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "request_url": response.get("url", ""),
        "request_method": response.get("method", ""),
        "request_body": request_body,
        "status": response.get("status"),
        "content_type": response.get("content_type", ""),
        "payload": response.get("payload"),
        "text": response.get("text", ""),
        "_run_id": run_id,
        "_scraped_at": scraped_at,
    }


def _write_endpoint_response(
    *,
    sink: _JsonlSink,
    error_sink: _JsonlSink,
    endpoint: str,
    run_id: str,
    scraped_at: str,
    response: dict[str, Any],
    location_id: str,
    seed: dict[str, Any],
) -> None:
    row = _response_row(endpoint, run_id, scraped_at, response)
    row["location_id"] = location_id
    row["seed"] = seed
    if response.get("status", 0) >= 400:
        error_sink.write(row)
        return
    sink.write(row)


def _pause_heatmap(*, page: Page, config: DxbiConfig) -> None:
    if config.heatmap_request_pause_seconds <= 0:
        return
    page.wait_for_timeout(int(config.heatmap_request_pause_seconds * 1000))


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.info(message, *args)


def _log_warning(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.warning(message, *args)


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)
DEFAULT_CHROME_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)


def _resolve_browser_executable(chrome_path: str) -> str | None:
    candidate = chrome_path.strip()
    if candidate:
        resolved = shutil.which(candidate) if "/" not in candidate else candidate
        if resolved and Path(resolved).exists():
            return resolved
        raise FileNotFoundError(f"DXBI browser executable not found: {chrome_path}")

    for name in DEFAULT_CHROME_CANDIDATES:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


@contextmanager
def _virtual_display_if_needed(config: DxbiConfig) -> Iterator[None]:
    if config.headless or os.environ.get("DISPLAY"):
        yield
        return
    if not shutil.which("Xvfb"):
        raise RuntimeError(
            "DXBI headful browser requested but DISPLAY is unset and Xvfb is not installed"
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
        raise RuntimeError("DXBI headful browser requested but Xvfb could not be started")

    logger.info("DXBI: started virtual display %s for headful browser", display)
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


def _raise_if_blocked_ajax(*, statuses: Iterable[int], url: str) -> None:
    blocked = sorted({status for status in statuses if status >= 400})
    if not blocked:
        return
    statuses_text = ", ".join(str(status) for status in blocked)
    raise RuntimeError(
        "DXBI APEX requests were blocked while scraping "
        f"{url} (HTTP {statuses_text}). "
        "Run with headless=false, use a real Chrome executable via chrome_path if needed, "
        "or provide a storage_state_path from a cleared browser session."
    )


def _new_context(*, playwright: Playwright, config: DxbiConfig) -> BrowserContext:
    launch_kwargs: dict = {
        "headless": config.headless,
        "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    }
    executable_path = _resolve_browser_executable(config.chrome_path)
    if executable_path:
        launch_kwargs["executable_path"] = executable_path
    browser = playwright.chromium.launch(**launch_kwargs)
    context_kwargs: dict = {"user_agent": _USER_AGENT}
    if config.storage_state_path.strip():
        context_kwargs["storage_state"] = config.storage_state_path
    return browser.new_context(**context_kwargs)


def _scrape_url_slice(
    *,
    context: BrowserContext,
    url: str,
    date_slice: DateSlice,
    run_id: str,
    scraped_at: str,
    config: DxbiConfig,
) -> list[dict]:
    page = context.new_page()
    blocked_ajax_statuses: list[int] = []
    ajax_request_count = 0

    def handle_response(response) -> None:
        nonlocal ajax_request_count
        if "wwv_flow.ajax" not in response.url:
            return
        ajax_request_count += 1
        if response.status >= 400:
            blocked_ajax_statuses.append(response.status)

    page.on("response", handle_response)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except TimeoutError:
            page.wait_for_timeout(3000)
        _maybe_solve_captcha(page=page, api_key=config.twocaptcha_api_key)
        _maybe_accept_terms(page)
        _apply_date_slice(page=page, date_slice=date_slice)
        _maybe_solve_captcha(page=page, api_key=config.twocaptcha_api_key)
        try:
            page.wait_for_selector(f"{SALE_TABLE_SELECTOR} tbody tr", timeout=15000)
        except TimeoutError:
            pass
        rows = []
        rows.extend(
            _collect_table_pages(
                page=page,
                url=url,
                run_id=run_id,
                scraped_at=scraped_at,
                date_slice=date_slice,
                table_selector=SALE_TABLE_SELECTOR,
                table_name="sales",
                region_selector=SALE_REGION_SELECTOR,
            )
        )
        rows.extend(
            _collect_table_pages(
                page=page,
                url=url,
                run_id=run_id,
                scraped_at=scraped_at,
                date_slice=date_slice,
                table_selector=RENTAL_TABLE_SELECTOR,
                table_name="rentals",
                region_selector=RENTAL_REGION_SELECTOR,
            )
        )
        _raise_if_blocked_ajax(statuses=blocked_ajax_statuses, url=url)
        if url.rstrip("/") == DXBI_BASE_URL.rstrip("/") and ajax_request_count == 0:
            raise RuntimeError(
                "DXBI root page did not emit any APEX ajax responses while scraping. "
                "The session may be blocked or page behavior has changed."
            )
        if url.rstrip("/") == DXBI_BASE_URL.rstrip("/") and not rows:
            raise RuntimeError(
                "DXBI root page returned zero rows after date refresh; this usually means "
                "Cloudflare blocked report ajax calls or the page contract changed."
            )
        return rows
    finally:
        page.close()


def _collect_table_pages(
    *,
    page: Page,
    url: str,
    run_id: str,
    scraped_at: str,
    date_slice: DateSlice,
    table_selector: str,
    table_name: str,
    region_selector: str,
) -> list[dict]:
    rows = _extract_table_rows(
        page=page,
        table_selector=table_selector,
        table_name=table_name,
        page_number=1,
        url=url,
        run_id=run_id,
        scraped_at=scraped_at,
        date_slice=date_slice,
    )
    calls = _extract_pagination_calls(page=page, region_selector=region_selector)
    if not calls:
        return rows

    seed = calls[0]
    page_size = int(seed["options"]["fetched"] or seed["options"]["max"])
    if page_size <= 0:
        return rows

    page_number = 2
    next_min = int(seed["options"]["min"])
    while True:
        call = {
            "region_id": seed["region_id"],
            "checksum": seed["checksum"],
            "options": {
                "min": next_min,
                "max": page_size,
                "fetched": page_size,
            },
        }
        _paginate_report(page=page, table_selector=table_selector, call=call)
        page_rows = _extract_table_rows(
            page=page,
            table_selector=table_selector,
            table_name=table_name,
            page_number=page_number,
            url=url,
            run_id=run_id,
            scraped_at=scraped_at,
            date_slice=date_slice,
        )
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        next_min += page_size
        page_number += 1
    return rows


def _extract_table_rows(
    *,
    page: Page,
    table_selector: str,
    table_name: str,
    page_number: int,
    url: str,
    run_id: str,
    scraped_at: str,
    date_slice: DateSlice,
) -> list[dict]:
    # Extract all row content in one JS call to avoid per-element locator timeouts
    # when APEX re-renders the table mid-iteration. Keep the ordered column
    # metadata in raw JSONL so later parsers can recover links and hidden labels.
    raw_table: dict = page.evaluate(
        """
        selector => {
            const table = document.querySelector(selector);
            if (!table) return { headers: {}, rows: [] };
            const headers = {};
            Array.from(table.querySelectorAll('thead th')).forEach(th => {
                if (!th.id) return;
                headers[th.id] = th.innerText ?? '';
            });
            const tbody = table.querySelector('tbody');
            if (!tbody) return { headers, rows: [] };
            return {
                headers,
                rows: Array.from(tbody.querySelectorAll('tr')).map(tr =>
                    Array.from(tr.querySelectorAll('td')).map(td => {
                        const header = td.getAttribute('headers') || '';
                        return {
                            header,
                            label: headers[header] || '',
                            text: td.innerText ?? '',
                            html: td.innerHTML ?? '',
                            links: Array.from(td.querySelectorAll('a[href]')).map(a => ({
                                text: a.innerText ?? '',
                                href: a.href || a.getAttribute('href') || '',
                                title: a.getAttribute('title') || '',
                                aria_label: a.getAttribute('aria-label') || '',
                                class: a.getAttribute('class') || '',
                            })),
                        };
                    })
                ),
            };
        }
        """,
        table_selector,
    )
    rows = []
    raw_rows = raw_table.get("rows", [])
    for row_index, cell_values in enumerate(raw_rows):
        normalized = [_normalize_cell_text(cell.get("text", "")) for cell in cell_values]
        if not any(normalized):
            continue
        columns = [_build_column_payload(cell) for cell in cell_values]
        links = [
            {
                "cell_header": column["id"],
                "cell_label": column["label"],
                **link,
            }
            for column in columns
            for link in column["links"]
        ]
        rows.append(
            {
                "table": table_name,
                "cells": normalized,
                "columns": columns,
                "links": links,
                "detail_urls": _detail_urls(links),
                "_run_id": run_id,
                "_scraped_at": scraped_at,
                "_slice_start_date": date_slice.start_date.isoformat(),
                "_slice_end_date": date_slice.end_date.isoformat(),
                "_source_url": url,
                "_page_number": page_number,
                "_row_number": row_index + 1,
            }
        )
    return rows


def _build_column_payload(cell: dict) -> dict:
    return {
        "id": str(cell.get("header") or ""),
        "label": _normalize_cell_text(str(cell.get("label") or "")),
        "text": _normalize_cell_text(str(cell.get("text") or "")),
        "html": str(cell.get("html") or ""),
        "links": [
            {
                "text": _normalize_cell_text(str(link.get("text") or "")),
                "href": str(link.get("href") or ""),
                "title": _normalize_cell_text(str(link.get("title") or "")),
                "aria_label": _normalize_cell_text(str(link.get("aria_label") or "")),
                "class": _normalize_cell_text(str(link.get("class") or "")),
            }
            for link in cell.get("links", [])
            if isinstance(link, dict) and str(link.get("href") or "").strip()
        ],
    }


def _detail_urls(links: list[dict]) -> list[str]:
    return list(
        dict.fromkeys(
            str(link.get("href") or "")
            for link in links
            if urlparse(str(link.get("href") or "")).netloc.lower() == "dxb.is"
        )
    )


def _normalize_cell_text(value: str) -> str:
    return " ".join(part.strip() for part in value.splitlines() if part.strip())


def _apply_date_slice(*, page: Page, date_slice: DateSlice) -> None:
    start_str = date_slice.start_date.isoformat()
    end_str = date_slice.end_date.isoformat()
    result = page.evaluate(
        """
        ([startDate, endDate]) => {
            if (typeof window.$s !== 'function') return { status: 'no-$s' };
            if (!document.querySelector('#P74_START_DATE') || !document.querySelector('#P74_END_DATE')) {
                return { status: 'missing-date-items' };
            }

            const reportHtml = (regionSelector, tableSelector) => {
                const catchNode = document.querySelector(`${regionSelector} [id^="report_"][id$="_catch"]`);
                const bodyNode = document.querySelector(`${tableSelector} tbody`);
                return [
                    catchNode ? catchNode.innerHTML : '',
                    bodyNode ? bodyNode.innerHTML : '',
                ].join('\\n');
            };
            const token = `${startDate}:${endDate}:${Date.now()}`;
            const state = {
                token,
                soldBefore: reportHtml('#soldhistory', '#report_table_soldhistory'),
                rentBefore: reportHtml('#rentHistory', '#report_table_rentHistory'),
                soldPresent: !!document.querySelector('#soldhistory'),
                rentPresent: !!document.querySelector('#rentHistory'),
                soldDone: false,
                rentDone: false,
            };
            window.__holocronDxbiRefresh = state;

            const jq = window.apex?.jQuery || window.jQuery;
            if (typeof jq === 'function') {
                if (state.soldPresent) {
                    jq('#soldhistory').one('apexafterrefresh', () => { state.soldDone = true; });
                }
                if (state.rentPresent) {
                    jq('#rentHistory').one('apexafterrefresh', () => { state.rentDone = true; });
                }
            }

            $s('P74_START_DATE', startDate, null, true);
            $s('P74_END_DATE', endDate, null, true);
            try {
                apex.region('soldhistory').refresh();
                apex.region('rentHistory').refresh();
            } catch (error) {
                return { status: 'refresh-error', detail: String(error) };
            }

            return { status: 'ok', token };
        }
        """,
        [start_str, end_str],
    )
    if result.get("status") != "ok":
        detail = result.get("detail") or result.get("status")
        raise RuntimeError(f"DXBI date refresh not ready: {detail}")

    try:
        page.wait_for_function(
            """
            ({ token }) => {
                const state = window.__holocronDxbiRefresh;
                if (!state || state.token !== token) return false;

                const reportHtml = (regionSelector, tableSelector) => {
                    const catchNode = document.querySelector(`${regionSelector} [id^="report_"][id$="_catch"]`);
                    const bodyNode = document.querySelector(`${tableSelector} tbody`);
                    return [
                        catchNode ? catchNode.innerHTML : '',
                        bodyNode ? bodyNode.innerHTML : '',
                    ].join('\\n');
                };
                const soldChanged = reportHtml('#soldhistory', '#report_table_soldhistory') !== state.soldBefore;
                const rentChanged = reportHtml('#rentHistory', '#report_table_rentHistory') !== state.rentBefore;
                const soldReady = !state.soldPresent || state.soldDone || soldChanged;
                const rentReady = !state.rentPresent || state.rentDone || rentChanged;
                return soldReady && rentReady;
            }
            """,
            arg={
                "token": result.get("token", ""),
            },
            timeout=20000,
        )
    except TimeoutError:
        page.wait_for_timeout(3000)


def _extract_pagination_calls(*, page: Page, region_selector: str) -> list[dict]:
    links = page.locator(f"{region_selector} {PAGINATION_SELECTOR} a[href]")
    calls = []
    seen: set[int] = set()
    for link_index in range(links.count()):
        href = links.nth(link_index).get_attribute("href") or ""
        match = PAGINATION_CALL_PATTERN.search(href)
        if match is None:
            continue
        min_value = int(match.group("min"))
        if min_value in seen:
            continue
        seen.add(min_value)
        calls.append(
            {
                "region_id": match.group("region_id"),
                "checksum": match.group("checksum"),
                "options": {
                    "min": min_value,
                    "max": int(match.group("max")),
                    "fetched": int(match.group("fetched")),
                },
            }
        )
    return sorted(calls, key=lambda call: call["options"]["min"])


def _paginate_report(*, page: Page, table_selector: str, call: dict) -> None:
    previous_html = page.evaluate(
        "(sel) => document.querySelector(sel + ' tbody')?.innerHTML ?? ''",
        table_selector,
    )
    page.evaluate(
        """
        ({ regionId, checksum, options }) => {
            apex.widget.report.paginate(regionId, checksum, options);
        }
        """,
        {"regionId": call["region_id"], "checksum": call["checksum"], "options": call["options"]},
    )
    try:
        page.wait_for_function(
            """
            ({ selector, previousHtml }) => {
                const node = document.querySelector(selector);
                return !!node && node.innerHTML !== previousHtml;
            }
            """,
            arg={"selector": f"{table_selector} tbody", "previousHtml": previous_html},
            timeout=15000,
        )
    except TimeoutError:
        page.wait_for_timeout(2000)


def _maybe_solve_captcha(*, page: Page, api_key: str) -> None:
    challenge = _detect_captcha(page)
    if challenge is None:
        return
    resolved_api_key = api_key or os.environ.get("TWOCAPTCHA_API_KEY", "").strip()
    resolved_api_key = resolved_api_key or os.environ.get("CAPTCHA_API_KEY", "").strip()
    if not resolved_api_key:
        raise RuntimeError("DXBI captcha detected but twocaptcha_api_key is not configured")
    solver = TwoCaptcha(resolved_api_key)
    if challenge["kind"] == "turnstile":
        result = solver.turnstile(sitekey=challenge["sitekey"], url=page.url)
    else:
        result = solver.hcaptcha(sitekey=challenge["sitekey"], url=page.url)
    token = result["code"]
    _inject_captcha_token(page=page, token=token)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except TimeoutError:
        page.wait_for_timeout(3000)


def _maybe_accept_terms(page: Page) -> None:
    try:
        checkbox = page.locator(
            "dialog input[type='checkbox'], .a-Dialog input[type='checkbox']"
        ).first
        if checkbox.is_visible(timeout=3000):
            checkbox.check()
            page.locator(
                "dialog button:has-text('Submit'), .a-Dialog button:has-text('Submit')"
            ).first.click()
            page.wait_for_timeout(1000)
    except TimeoutError:
        pass


def _detect_captcha(page: Page) -> dict | None:
    turnstile = page.locator(
        "iframe[src*='challenges.cloudflare.com'], div.cf-turnstile[data-sitekey]"
    )
    if turnstile.count():
        sitekey = _sitekey_from_locator(
            page, "div.cf-turnstile[data-sitekey]"
        ) or _sitekey_from_iframe(turnstile.first.get_attribute("src") or "")
        if sitekey:
            return {"kind": "turnstile", "sitekey": sitekey}
    hcaptcha = page.locator("[data-sitekey], iframe[src*='hcaptcha']")
    if hcaptcha.count():
        sitekey = _sitekey_from_locator(page, "[data-sitekey]") or _sitekey_from_iframe(
            hcaptcha.first.get_attribute("src") or ""
        )
        if sitekey:
            return {"kind": "hcaptcha", "sitekey": sitekey}
    return None


def _sitekey_from_locator(page: Page, selector: str) -> str:
    locator = page.locator(selector)
    if not locator.count():
        return ""
    return locator.first.get_attribute("data-sitekey") or ""


def _sitekey_from_iframe(src: str) -> str:
    if not src:
        return ""
    return parse_qs(urlparse(src).query).get("sitekey", [""])[0]


def _inject_captcha_token(*, page: Page, token: str) -> None:
    page.evaluate(
        """
        value => {
            for (const selector of [
                'textarea[name="h-captcha-response"]',
                'textarea[name="g-recaptcha-response"]',
                'input[name="cf-turnstile-response"]',
                'textarea[name="cf-turnstile-response"]'
            ]) {
                for (const node of document.querySelectorAll(selector)) {
                    node.value = value;
                    node.innerHTML = value;
                    node.dispatchEvent(new Event('input', { bubbles: true }));
                    node.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
            for (const form of document.forms) {
                const submit = form.querySelector('[type="submit"]');
                if (submit) {
                    submit.click();
                    return;
                }
            }
        }
        """,
        token,
    )


def _write_slice_file(*, output_path: Path, date_slice: DateSlice, rows: list[dict]) -> RawFile:
    path = output_path / f"slice_{date_slice.key}.jsonl"
    hasher = hashlib.sha256()
    size = 0
    with path.open("wb") as handle:
        for row in rows:
            line = (json.dumps(row, sort_keys=True) + "\n").encode()
            handle.write(line)
            hasher.update(line)
            size += len(line)
    return build_raw_file(
        path=path,
        sha256=hasher.hexdigest(),
        size_bytes=size,
        row_count=len(rows),
        content_type="application/x-ndjson",
        metadata={
            "slice_start_date": date_slice.start_date.isoformat(),
            "slice_end_date": date_slice.end_date.isoformat(),
        },
    )
