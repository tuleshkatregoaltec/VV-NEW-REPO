#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from holocron.sources.dxbi.rental_coverage import (
    MANIFEST_VERSION,
    build_rental_manifest,
    checkpoint_key,
    configuration_hash,
    filter_options_signature,
    manifest_hash,
    manifest_configurations,
    raw_row_fingerprint,
    read_location_inventory,
    select_marginal_coverage,
    validate_filter_discovery,
)


DXBI_URL = "https://dxbinteract.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)
REPORTS = {
    "rentals": {
        "region_selector": "#rentHistory",
        "region_name": "rentHistory",
        "marker": "47624226685649900817",
        "table_selector": "#report_table_rentHistory",
        "deal": "RENT",
    },
    "sales": {
        "region_selector": "#soldhistory",
        "region_name": "soldhistory",
        "marker": "29609740940913885923",
        "table_selector": "#report_table_soldhistory",
        "deal": "SALE",
    },
}
PAGE_SIZE = 300
COLLECTOR_VERSION = 3
CENT = Decimal("0.01")
RECOVERABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504, 598}
FETCH_EVAL_TIMEOUT_MS = 120_000
PAGINATION_PATTERN = re.compile(
    r"apex\.widget\.report\.paginate\('([^']+)'\s*,\s*'([^']+)'\s*,"
    r"\s*\{min:(\d+),max:(\d+),fetched:(\d+)\}\)"
)
PRICE_BUCKETS = (
    (Decimal("0"), Decimal("24999.99")),
    (Decimal("25000"), Decimal("49999.99")),
    (Decimal("50000"), Decimal("74999.99")),
    (Decimal("75000"), Decimal("99999.99")),
    (Decimal("100000"), Decimal("124999.99")),
    (Decimal("125000"), Decimal("149999.99")),
    (Decimal("150000"), Decimal("199999.99")),
    (Decimal("200000"), Decimal("299999.99")),
    (Decimal("300000"), Decimal("499999.99")),
    (Decimal("500000"), Decimal("999999.99")),
    (Decimal("1000000"), None),
)
SIZE_BUCKETS = (
    (Decimal("0"), Decimal("249.99")),
    (Decimal("250"), Decimal("499.99")),
    (Decimal("500"), Decimal("749.99")),
    (Decimal("750"), Decimal("999.99")),
    (Decimal("1000"), Decimal("1499.99")),
    (Decimal("1500"), Decimal("1999.99")),
    (Decimal("2000"), Decimal("2999.99")),
    (Decimal("3000"), Decimal("4999.99")),
    (Decimal("5000"), Decimal("9999.99")),
    (Decimal("10000"), None),
)
DEFAULT_FILTER_OVERRIDES = {
    "P74_DEAL": "RENT",
    "P74_PROP_TYPE": "A",
    "P74_STATUS": "B",
    "P74_BEDS": "-1",
    "P74_SOLD_BY": "B",
    "P74_FLAG": "A",
    "P74_PROCEDURE": "B",
}
DEFAULT_LOCATION = {"id": "1", "text": "Dubai", "slug": "dubai"}
DEFAULT_LOCATION_INVENTORY = Path(__file__).with_name("dxbi_rental_locations.tsv")
RENTAL_FILTER_DOM_IDS = {
    "P74_PROP_TYPE": "prop-type",
    "P74_STATUS": "status",
    "P74_BEDS": "beds",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value, "f")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def dates_between(start: date, end: date, direction: str) -> Iterator[date]:
    if direction == "asc":
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)
        return
    current = end
    while current >= start:
        yield current
        current -= timedelta(days=1)


def shard_key(shard: dict[str, Any]) -> str:
    key = "|".join(
        (
            shard["date"],
            decimal_text(shard["min_price"]),
            decimal_text(shard["max_price"]),
            decimal_text(shard["min_size"]),
            decimal_text(shard["max_size"]),
        )
    )
    page_start = int(shard.get("page_start", 1))
    return key if page_start == 1 else f"{key}|page={page_start}"


def pagination_root_key(shard: dict[str, Any]) -> str:
    return shard_key({**shard, "page_start": 1})


def initial_shards(day: date) -> list[dict[str, Any]]:
    return [
        {
            "date": day.isoformat(),
            "min_price": Decimal("0"),
            "max_price": None,
            "min_size": None,
            "max_size": None,
        }
    ]


def bisect_range(
    minimum: Decimal, maximum: Decimal | None
) -> tuple[tuple[Decimal, Decimal], tuple[Decimal, Decimal | None]]:
    if maximum is None:
        next_maximum = max(minimum * 2, minimum + Decimal("1000000"))
        return (minimum, next_maximum), (next_maximum + CENT, None)
    if maximum - minimum < CENT:
        raise ValueError("range cannot be split further")
    midpoint = ((minimum + maximum) / 2).quantize(CENT)
    if midpoint >= maximum:
        midpoint = maximum - CENT
    return (minimum, midpoint), (midpoint + CENT, maximum)


def split_capped_shard(shard: dict[str, Any]) -> list[dict[str, Any]]:
    min_price = shard["min_price"]
    max_price = shard["max_price"]
    min_size = shard["min_size"]
    max_size = shard["max_size"]

    if min_size is None:
        if min_price == 0 and max_price is None:
            return [
                {**shard, "min_price": minimum, "max_price": maximum}
                for minimum, maximum in PRICE_BUCKETS
            ]
        # Once the broad range has been divided into stable price buckets,
        # switch axes instead of bisecting popular round-number rents down to
        # one-cent price ranges. A capped price/size cell is bisected by size
        # below and ultimately paginated if it cannot be split further.
        return [
            {**shard, "min_size": minimum, "max_size": maximum} for minimum, maximum in SIZE_BUCKETS
        ]

    if max_size is None or max_size - min_size > CENT or (
        min_size > 0 and max_size - min_size == CENT
    ):
        ranges = bisect_range(min_size, max_size)
        return [{**shard, "min_size": minimum, "max_size": maximum} for minimum, maximum in ranges]
    # DXBI treats some zero-valued size bounds as blank filters. If such a
    # terminal-looking size cell is still capped, return to the price axis
    # before attempting pagination. This keeps the partition fail-closed while
    # avoiding an APEX page request that can return an ambiguous empty page.
    if max_price is None or max_price - min_price >= CENT:
        ranges = bisect_range(min_price, max_price)
        return [
            {**shard, "min_price": minimum, "max_price": maximum}
            for minimum, maximum in ranges
        ]
    return []


def refine_paged_checkpoint(
    *,
    output_dir: Path,
    state: dict[str, Any],
    root_key: str,
    children: list[dict[str, Any]],
    configuration: dict[str, Any],
) -> None:
    """Replace previously paged rows when a capped shard can now be split further."""
    page_prefix = f"{root_key}|page="
    superseded_keys = [
        key
        for key in state["completed"]
        if key == root_key or key.startswith(page_prefix)
    ]
    for key in superseded_keys:
        item = state["completed"].pop(key)
        relative_path = str(item.get("path") or "")
        if not relative_path:
            continue
        path = output_dir / relative_path
        if path.exists():
            archive = path.with_name(f"{path.name}.superseded")
            sequence = 1
            while archive.exists():
                archive = path.with_name(f"{path.name}.superseded.{sequence}")
                sequence += 1
            path.rename(archive)

    for key in list(state["failed"]):
        if key == root_key or key.startswith(page_prefix):
            state["failed"].pop(key)
    state["paged"].pop(root_key, None)
    state["expanded"][root_key] = {
        "children": [
            checkpoint_key(configuration, shard_key(child)) for child in children
        ],
        "expanded_at": utc_now(),
        "reason": "refined_previously_paged_capped_shard",
    }


def refine_expanded_checkpoint(
    *,
    output_dir: Path,
    state: dict[str, Any],
    root_key: str,
    children: list[dict[str, Any]],
    configuration: dict[str, Any],
) -> None:
    """Replace a saved expansion when newer split rules produce safer children."""
    descendants = {root_key}
    pending = [root_key]
    while pending:
        parent = pending.pop()
        saved = state["expanded"].get(parent) or {}
        for child_key in saved.get("children") or []:
            if child_key not in descendants:
                descendants.add(child_key)
                pending.append(child_key)

    completed_keys = [
        key
        for key in state["completed"]
        if any(
            key == descendant or key.startswith(f"{descendant}|page=")
            for descendant in descendants
        )
    ]
    for key in completed_keys:
        item = state["completed"].pop(key)
        relative_path = str(item.get("path") or "")
        if not relative_path:
            continue
        path = output_dir / relative_path
        if path.exists():
            archive = path.with_name(f"{path.name}.superseded")
            sequence = 1
            while archive.exists():
                archive = path.with_name(f"{path.name}.superseded.{sequence}")
                sequence += 1
            path.rename(archive)

    for key in list(state["failed"]):
        if any(
            key == descendant or key.startswith(f"{descendant}|page=")
            for descendant in descendants
        ):
            state["failed"].pop(key)
    for key in list(state["paged"]):
        if key in descendants:
            state["paged"].pop(key)
    for key in list(state["expanded"]):
        if key in descendants:
            state["expanded"].pop(key)

    state["expanded"][root_key] = {
        "children": [
            checkpoint_key(configuration, shard_key(child)) for child in children
        ],
        "expanded_at": utc_now(),
        "reason": "refined_saved_expansion",
    }


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def load_state(path: Path, configuration: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": 2,
            "configuration": configuration,
            "completed": {},
            "expanded": {},
            "failed": {},
            "paged": {},
            "partitions": {},
            "requests": 0,
        }
    state = json.loads(path.read_text())
    expected_hash = configuration["configuration_hash"]
    actual_hash = (state.get("configuration") or {}).get("configuration_hash")
    if state.get("version") != 2 or actual_hash != expected_hash:
        raise RuntimeError(
            f"checkpoint {path} belongs to configuration {actual_hash or 'legacy'}, "
            f"not {expected_hash}"
        )
    state.setdefault("paged", {})
    state.setdefault("partitions", {})
    return state


def write_shard(
    path: Path,
    shard: dict[str, Any],
    rows: list[dict[str, Any]],
    transaction_type: str,
    configuration: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as raw_handle:
        temporary = Path(raw_handle.name)
    try:
        with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as handle:
            for index, row in enumerate(rows, start=1):
                record = {
                    "transaction_type": transaction_type,
                    "report_type": configuration["report_type"],
                    "source_account": configuration["account"],
                    "source_run_id": configuration["source_run_id"],
                    "filter_profile": {
                        "id": configuration["profile_id"],
                        "label": configuration.get("profile_label", ""),
                        "filters": configuration["filters"],
                    },
                    "source_location": {
                        "id": configuration["location_id"],
                        "text": configuration["location_text"],
                        "slug": configuration["location_slug"],
                    },
                    "configuration_hash": configuration["configuration_hash"],
                    "collection_strategy": configuration.get("collection_strategy", "split"),
                    "collector_version": configuration.get("collector_version", 2),
                    "shard": {
                        key: decimal_text(value) if isinstance(value, Decimal) else value
                        for key, value in shard.items()
                    },
                    "row_index_in_response": index,
                    "columns": row["columns"],
                    "row_attributes": row.get("row_attributes") or {},
                    "hidden_attributes": row.get("hidden_attributes") or {},
                    "scraped_at": utc_now(),
                }
                record["raw_row_fingerprint"] = raw_row_fingerprint(record)
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def virtual_display() -> Iterator[None]:
    process: subprocess.Popen[bytes] | None = None
    display = ""
    for display_number in range(90, 120):
        if Path(f"/tmp/.X{display_number}-lock").exists():
            continue
        candidate = f":{display_number}"
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
        raise RuntimeError("could not start an isolated Xvfb display")

    previous_display = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = display
    try:
        yield
    finally:
        if previous_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = previous_display
        process.terminate()
        process.wait(timeout=5)


def maybe_accept_terms(page: Page) -> None:
    checkbox = page.locator("dialog input[type='checkbox'], .a-Dialog input[type='checkbox']").first
    try:
        if checkbox.is_visible(timeout=3_000):
            checkbox.check()
            page.locator(
                "dialog button:has-text('Submit'), .a-Dialog button:has-text('Submit')"
            ).first.click()
            page.wait_for_timeout(1_000)
    except PlaywrightTimeoutError:
        pass


def login(page: Page, credentials: dict[str, str], report: dict[str, str]) -> None:
    page.goto(DXBI_URL, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(3_000)
    maybe_accept_terms(page)
    sign_in_candidates = page.get_by_text("Sign In", exact=True)
    sign_in: Any | None = None
    for index in range(sign_in_candidates.count()):
        candidate = sign_in_candidates.nth(index)
        if candidate.is_visible(timeout=1_000):
            sign_in = candidate
            break
    if page.locator(report["region_selector"]).count() and sign_in is None:
        return

    if sign_in is None:
        raise RuntimeError("DXB Sign In control not found on an unauthenticated page")
    sign_in.click()
    page.wait_for_timeout(2_000)
    scope: Any = page
    for frame in page.frames:
        if frame.locator("input[type='password']").count():
            scope = frame
            break

    username = scope.locator(
        "#P9999_USERNAME, input[name='P9999_USERNAME'], input[type='email']"
    ).first
    password = scope.locator(
        "#P9999_PASSWORD, input[name='P9999_PASSWORD'], input[type='password']"
    ).first
    if not username.count() or not password.count():
        raise RuntimeError("DXB modal login fields not found")
    username.fill(credentials["email"])
    password.fill(credentials["password"])
    submit = scope.get_by_role("button", name="Continue", exact=True).first
    if not submit.count():
        raise RuntimeError("DXB modal Continue button not found")
    submit.click()
    page.wait_for_timeout(5_000)
    page.goto(DXBI_URL, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(3_000)
    if not page.locator(report["region_selector"]).count():
        raise RuntimeError("DXB login did not expose the requested transaction region")


def apply_filters_and_refresh(
    page: Page,
    shard: dict[str, Any],
    filter_overrides: dict[str, str],
    location: dict[str, str],
    report: dict[str, str],
) -> None:
    payload = {
        "date": shard["date"],
        "minPrice": decimal_text(shard["min_price"]),
        "maxPrice": decimal_text(shard["max_price"]),
        "minSize": decimal_text(shard["min_size"]),
        "maxSize": decimal_text(shard["max_size"]),
        "pageStart": int(shard.get("page_start", 1)),
        "filterOverrides": filter_overrides,
        "location": location,
    }
    refresh = page.evaluate(
        """filters => {
            const set = (id, value) => {
                if (document.querySelector(`#${id}`)) window.$s(id, value, null, true);
            };
            if (typeof window.$s !== 'function' || !window.apex?.region) {
                throw new Error('APEX filter API is unavailable');
            }
            set('P74_DLD_LOCATION_ID', filters.location.id);
            set('P74_DLD_LOCATION_TEXT', filters.location.text);
            set('P74_DLD_LOCATION', filters.location.slug);
            for (const [id, value] of Object.entries(filters.filterOverrides)) {
                set(id, value);
            }
            set('P74_START_DATE', filters.date);
            set('P74_END_DATE', filters.date);
            set('P74_MIN_PRICE', filters.minPrice);
            set('P74_MAX_PRICE', filters.maxPrice);
            set('P74_MIN_SIZE', filters.minSize);
            set('P74_MAX_SIZE', filters.maxSize);
            set('P74_PROJECT', '');
            set('P74_PROJECT_A', '');
            set('P74_PROJECT_A_HIDDENVALUE', '');
            set('P74_PROJECT_B', '');
            set('P74_PROJECT_B_HIDDENVALUE', '');
            set('P74_MY_PROJECT', '');
            set('P74_MY_PROJECT_HIDDENVALUE', '');
            const token = String(Date.now());
            const state = {token, soldDone: false, rentDone: false};
            window.__dxbiBackfillRefresh = state;
            const jq = window.apex?.jQuery || window.jQuery;
            if (typeof jq === 'function') {
                jq('#soldhistory').one(
                    'apexafterrefresh', () => { state.soldDone = true; }
                );
                jq('#rentHistory').one(
                    'apexafterrefresh', () => { state.rentDone = true; }
                );
            }
            window.apex.region('soldhistory').refresh();
            window.apex.region('rentHistory').refresh();
            return {token};
        }""",
        payload,
    )
    try:
        page.wait_for_function(
            """token => {
                const state = window.__dxbiBackfillRefresh;
                return state?.token === token && state.soldDone && state.rentDone;
            }""",
            arg=refresh["token"],
            timeout=20_000,
        )
    except PlaywrightTimeoutError:
        page.wait_for_timeout(3_000)


def apply_report_profile(page: Page, filter_overrides: dict[str, str]) -> None:
    """Switch sale/rental profile without replacing the landing-page date window."""
    refresh = page.evaluate(
        """filterOverrides => {
            if (typeof window.$s !== 'function' || !window.apex?.region) {
                throw new Error('APEX filter API is unavailable');
            }
            for (const [id, value] of Object.entries(filterOverrides)) {
                if (document.querySelector(`#${id}`)) window.$s(id, value, null, true);
            }
            const token = String(Date.now());
            const state = {token, soldDone: false, rentDone: false};
            window.__dxbiBackfillRefresh = state;
            const jq = window.apex?.jQuery || window.jQuery;
            if (typeof jq === 'function') {
                jq('#soldhistory').one('apexafterrefresh', () => { state.soldDone = true; });
                jq('#rentHistory').one('apexafterrefresh', () => { state.rentDone = true; });
            }
            window.apex.region('soldhistory').refresh();
            window.apex.region('rentHistory').refresh();
            return {token};
        }""",
        filter_overrides,
    )
    try:
        page.wait_for_function(
            """token => {
                const state = window.__dxbiBackfillRefresh;
                return state?.token === token && state.soldDone && state.rentDone;
            }""",
            arg=refresh["token"],
            timeout=20_000,
        )
    except PlaywrightTimeoutError:
        page.wait_for_timeout(3_000)


def capture_template(
    page: Page,
    template_date: str,
    filter_overrides: dict[str, str],
    report: dict[str, str],
    location: dict[str, str],
) -> dict[str, str]:
    pagination_selector = (
        f"{report['region_selector']} "
        'a[href*="apex.widget.report.paginate"], '
        f'{report["region_selector"]} a[href^="#action$paginate"]'
    )
    link = page.locator(pagination_selector).first
    # The landing page already has a dense reporting window. Prefer capturing
    # its APEX request before applying a one-day slice: sparse dates and renamed
    # root locations may legitimately render no pagination control.
    if not link.count():
        apply_report_profile(page, filter_overrides)
    if not link.count():
        shard = {
            "date": template_date,
            "min_price": Decimal("0"),
            "max_price": None,
            "min_size": None,
            "max_size": None,
        }
        apply_filters_and_refresh(page, shard, filter_overrides, location, report)
    if not link.count():
        raise RuntimeError("dense template window produced no transaction pagination link")
    href = link.get_attribute("href") or ""
    match = PAGINATION_PATTERN.search(href)
    region_id = match.group(1) if match else report["marker"]

    with page.expect_request(
        lambda request: (
            request.method == "POST"
            and "wwv_flow.ajax?p_context=litedxb/transactions/" in request.url
            and report["marker"] in (request.post_data or "")
        ),
        timeout=10_000,
    ) as request_info:
        # Rental pagination remains in the DOM while its panel is visually
        # hidden. Dispatching the native click still produces the authenticated
        # APEX request and avoids Playwright's visibility guard.
        link.evaluate("element => element.click()")
    request = request_info.value
    return {
        "url": request.url,
        "post_data": request.post_data or "",
        "region_id": region_id,
    }


def fetch_rows(
    page: Page,
    template: dict[str, str],
    shard: dict[str, Any],
    filter_overrides: dict[str, str],
    location: dict[str, str],
    report: dict[str, str],
) -> dict[str, Any]:
    payload = {
        "template": template,
        "date": shard["date"],
        "minPrice": decimal_text(shard["min_price"]),
        "maxPrice": decimal_text(shard["max_price"]),
        "minSize": decimal_text(shard["min_size"]),
        "maxSize": decimal_text(shard["max_size"]),
        "pageStart": int(shard.get("page_start", 1)),
        "filterOverrides": filter_overrides,
        "location": location,
        "report": report,
    }
    return page.evaluate(
        """async input => {
            const params = new URLSearchParams(input.template.post_data);
            params.set('p_pg_min_row', String(input.pageStart));
            // APEX uses max_rows as the page size, not the absolute ending row.
            params.set('p_pg_max_rows', '300');
            params.set('p_pg_rows_fetched', '300');
            params.set('x01', input.template.region_id);
            const payload = JSON.parse(params.get('p_json'));
            for (const item of payload.pageItems?.itemsToSubmit || []) {
                if (item.n === 'P74_DLD_LOCATION_ID') item.v = input.location.id;
                if (item.n === 'P74_DLD_LOCATION_TEXT') item.v = input.location.text;
                if (item.n === 'P74_DLD_LOCATION') item.v = input.location.slug;
                if (Object.hasOwn(input.filterOverrides, item.n)) {
                    item.v = input.filterOverrides[item.n];
                }
                if (item.n === 'P74_START_DATE') item.v = input.date;
                if (item.n === 'P74_END_DATE') item.v = input.date;
                if (item.n === 'P74_MIN_PRICE') item.v = input.minPrice;
                if (item.n === 'P74_MAX_PRICE') item.v = input.maxPrice;
                if (item.n === 'P74_MIN_SIZE') item.v = input.minSize;
                if (item.n === 'P74_MAX_SIZE') item.v = input.maxSize;
            }
            params.set('p_json', JSON.stringify(payload));
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 90000);
            let response;
            try {
                response = await fetch(input.template.url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest',
                        Accept: 'text/html, */*; q=0.01'
                    },
                    body: params.toString(),
                    signal: controller.signal
                });
            } catch (error) {
                return {
                    status: 598,
                    login_redirect: false,
                    rows: [],
                    error: String(error),
                    pagination_text: '',
                    reported_total: null,
                    has_next_page: false,
                    next_page_start: null
                };
            } finally {
                clearTimeout(timeout);
            }
            const html = await response.text();
            const processingError = /Error processing request[.]/i.test(html);
            const document_ = new DOMParser().parseFromString(html, 'text/html');
            const table = document_.querySelector(input.report.table_selector);
            const headers = {};
            table?.querySelectorAll('thead th').forEach(header => {
                if (header.id) {
                    headers[header.id] = (
                        header.innerText || header.textContent || ''
                    ).replace(/\\s+/g, ' ').trim();
                }
            });
            const attributes = element => Object.fromEntries(
                Array.from(element?.attributes || []).map(attribute => [
                    attribute.name, attribute.value
                ])
            );
            const rows = table ? Array.from(table.querySelectorAll('tbody tr')).map(row => ({
                row_attributes: attributes(row),
                hidden_attributes: Object.fromEntries(
                    Array.from(row.querySelectorAll('input[type="hidden"], [hidden]'))
                        .flatMap(element => {
                            const key = element.getAttribute('name') || element.id;
                            const value = element.value || element.getAttribute('value')
                                || element.getAttribute('data-value') || '';
                            return key ? [[key, value]] : [];
                        })
                ),
                columns: Array.from(row.querySelectorAll('td')).map(cell => {
                    const id = cell.getAttribute('headers') || '';
                    return {
                        id,
                        label: headers[id] || '',
                        text: (cell.innerText || cell.textContent || '')
                            .replace(/\\s+/g, ' ').trim(),
                        html: cell.innerHTML || '',
                        links: Array.from(cell.querySelectorAll('a[href]')).map(link => ({
                            text: (link.innerText || link.textContent || '')
                                .replace(/\\s+/g, ' ').trim(),
                            href: link.href || link.getAttribute('href') || '',
                            class: link.getAttribute('class') || ''
                        })),
                        attributes: attributes(cell)
                    };
                })
            })).filter(row => row.columns.some(column => column.text)) : [];
            const paginationText = Array.from(document_.querySelectorAll(
                '.a-Report-paginationText, .t-Report-paginationText, '
                + '.a-IRR-pagination-label, .a-Report-pagination'
            )).map(element => (element.innerText || element.textContent || '')
                .replace(/\\s+/g, ' ').trim()).filter(Boolean).join(' | ');
            const totalMatch = paginationText.match(/\\bof\\s+([\\d,]+)/i);
            const paginationStarts = [];
            document_.querySelectorAll(
                'a[href*="paginate"], [onclick*="paginate"], '
                + 'a[href*="p_pg_min_row"], [data-min], [data-page-start]'
            ).forEach(element => {
                const sources = [
                    element.getAttribute('href') || '',
                    element.getAttribute('onclick') || '',
                    element.getAttribute('data-min') || '',
                    element.getAttribute('data-page-start') || ''
                ];
                for (const source of sources) {
                    for (const match of source.matchAll(
                        /(?:\\bmin\\b|p_pg_min_row|page-start)\\s*[:=]\\s*['"]?(\\d+)/gi
                    )) paginationStarts.push(Number(match[1]));
                    if (/^\\d+$/.test(source)) paginationStarts.push(Number(source));
                }
            });
            const nextStarts = paginationStarts.filter(value => value > input.pageStart);
            const nextPageStart = nextStarts.length ? Math.min(...nextStarts) : null;
            return {
                status: processingError ? 598 : response.status,
                login_redirect: /P9999_USERNAME|apex_authentication/i.test(html),
                error: processingError ? 'DXBI_APEX_PROCESSING_ERROR' : '',
                rows,
                pagination_text: paginationText.slice(0, 500),
                reported_total: totalMatch ? Number(totalMatch[1].replace(/,/g, '')) : null,
                has_next_page: nextPageStart !== null,
                next_page_start: nextPageStart
            };
        }""",
        payload,
    )


def discover_filter_options(page: Page) -> dict[str, list[dict[str, str]]]:
    """Read the rental choices from DXBI's APEX items and slug-named popup controls."""
    discovered: dict[str, list[dict[str, str]]] = {}
    for item_id, dom_id in RENTAL_FILTER_DOM_IDS.items():
        discovered[item_id] = page.evaluate(
            r"""input => {
            const {itemId, domId} = input;
            const options = [];
            const seen = new Set();
            const add = (value, label) => {
                value = String(value || '').trim();
                label = String(label || '').replace(/\s+/g, ' ').trim();
                if (!value || !label || seen.has(value)) return;
                seen.add(value);
                options.push({value, label});
            };
            const item = document.querySelector(`#${itemId}`);
            item?.querySelectorAll('option').forEach(option => add(option.value, option.text));
            const roots = domId === 'status'
                ? document.querySelectorAll(
                    '.popup-pills[data-id="status"][data-ref="rent"]'
                )
                : document.querySelectorAll(
                    `.popup-pills[data-id="${domId}"], `
                    + `.popup-radio[data-id="${domId}"]`
                );
            roots.forEach(root => root.querySelectorAll(
                '[data-value], [data-return-value], input[type="radio"], '
                + '.radio-like-btn[data-id]'
            ).forEach(element => {
                const value = element.getAttribute('data-value')
                    || element.getAttribute('data-return-value')
                    || element.getAttribute('data-id') || element.value;
                const labelElement = element.id
                    ? document.querySelector(`label[for="${CSS.escape(element.id)}"]`)
                    : null;
                add(value, labelElement?.textContent || element.textContent || element.title);
            }));
            return options;
        }""",
            {"itemId": item_id, "domId": dom_id},
        )
    return discovered


def inspect_filter_page(page: Page) -> dict[str, Any]:
    """Return the verbose DOM diagnostics used when DXBI changes its APEX controls."""
    return page.evaluate(
        """() => ({
            url: location.href,
            page_text: document.body.innerText,
            state: {
                location: {
                    slug: document.querySelector('#P74_DLD_LOCATION')?.value || '',
                    id: document.querySelector('#P74_DLD_LOCATION_ID')?.value || '',
                    text: document.querySelector('#P74_DLD_LOCATION_TEXT')?.value || ''
                },
                deal: document.querySelector('#P74_DEAL')?.value || '',
                start_date: document.querySelector('#P74_START_DATE')?.value || '',
                end_date: document.querySelector('#P74_END_DATE')?.value || ''
            },
            controls: [...document.querySelectorAll(
                '.inline-popup[data-id], .search-choose-btns[data-id], .more-filters[data-id]'
            )].map(element => element.outerHTML.slice(0, 6000)),
            regions: ['#soldhistory', '#rentHistory'].map(selector => ({
                selector,
                html: document.querySelector(selector)?.outerHTML.slice(0, 16000) || '',
                links: [...(document.querySelector(selector)?.querySelectorAll('a') || [])]
                    .map(link => ({
                        text: (link.textContent || '').trim(),
                        href: link.getAttribute('href') || '',
                        onclick: link.getAttribute('onclick') || ''
                    }))
            })),
            scripts: [...document.scripts].map(script => script.src).filter(Boolean),
            area_links: [...document.links]
                .filter(link => /Business Bay|Downtown Dubai|Dubai Marina/i.test(
                    link.textContent || ''
                ))
                .map(link => ({text: (link.textContent || '').trim(), href: link.href}))
        })"""
    )


def configuration_paths(output_dir: Path, configuration: dict[str, Any]) -> tuple[Path, Path]:
    config_hash = configuration["configuration_hash"]
    checkpoint_path = output_dir / "checkpoints" / f"{config_hash}.json"
    shard_dir = (
        output_dir
        / "shards"
        / f"profile={configuration['profile_id']}"
        / f"location={configuration['location_id']}"
    )
    return checkpoint_path, shard_dir


def _singleton_configuration(
    *,
    report: dict[str, str],
    report_name: str,
    account: str,
    filters: dict[str, str],
    location: dict[str, str],
) -> dict[str, Any]:
    configuration: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "manifest_hash": "unmanaged",
        "report_type": report_name,
        "account": account,
        "profile_id": "broad",
        "profile_label": "Configured profile",
        "location_id": location["id"],
        "location_text": location["text"],
        "location_slug": location["slug"],
        "filters": {**filters, "P74_DEAL": report["deal"]},
    }
    configuration["configuration_hash"] = configuration_hash(configuration)
    return configuration


def _collected_fingerprints(output_dir: Path) -> dict[tuple[str, str], Counter[str]]:
    collected: dict[tuple[str, str], Counter[str]] = {}
    for path in sorted((output_dir / "shards").rglob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                profile = payload.get("filter_profile") or {}
                location = payload.get("source_location") or {}
                key = (str(profile.get("id") or "default"), str(location.get("id") or "1"))
                fingerprint = str(
                    payload.get("raw_row_fingerprint") or raw_row_fingerprint(payload)
                )
                collected.setdefault(key, Counter())[fingerprint] += 1
    return collected


def write_run_reconciliation(
    *,
    output_dir: Path,
    configurations: list[dict[str, Any]],
    dates: list[date],
    status: str,
    run_requests: int,
    manifest_hash: str,
) -> dict[str, Any]:
    expected = len(configurations) * len(dates)
    completed = failed = raw_rows = cumulative_requests = 0
    terminal_status: dict[str, dict[str, str]] = {}
    for configuration in configurations:
        state_path, _ = configuration_paths(output_dir, configuration)
        state = load_state(state_path, configuration)
        cumulative_requests += int(state.get("requests") or 0)
        for day in dates:
            partition = state["partitions"].get(day.isoformat()) or {}
            partition_status = str(partition.get("status") or "missing")
            terminal_status.setdefault(configuration["configuration_hash"], {})[day.isoformat()] = (
                partition_status
            )
            completed += partition_status == "complete"
            failed += partition_status == "failed"
        raw_rows += sum(int(item.get("rows") or 0) for item in state["completed"].values())

    fingerprints = _collected_fingerprints(output_dir)
    union_fingerprints: Counter[str] = Counter()
    for configuration_fingerprints in fingerprints.values():
        union_fingerprints |= configuration_fingerprints
    unique_source_rows = union_fingerprints.total()
    reconciliation = {
        "status": status,
        "report_type": configurations[0]["report_type"] if configurations else "rentals",
        "manifest_hash": manifest_hash,
        "started_at": min(
            (
                str(
                    load_state(configuration_paths(output_dir, config)[0], config).get("started_at")
                )
                for config in configurations
                if configuration_paths(output_dir, config)[0].exists()
            ),
            default=utc_now(),
        ),
        "finished_at": utc_now(),
        "raw_rows": raw_rows,
        "unique_source_rows": unique_source_rows,
        "normalized_rows": 0,
        "quarantined_rows": 0,
        "profile_overlap_rows": max(0, raw_rows - unique_source_rows),
        "loaded_contracts": 0,
        "run_requests": cumulative_requests,
        "invocation_requests": run_requests,
        "expected_partitions": expected,
        "completed_partitions": completed,
        "failed_partitions": failed,
        "missing_partitions": expected - completed - failed,
        "terminal_partition_status": terminal_status,
    }
    atomic_json(output_dir / "reconciliation.json", reconciliation)
    return reconciliation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--storage-state", required=True)
    parser.add_argument("--browser", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--direction", choices=("asc", "desc"), required=True)
    parser.add_argument("--template-date", default="2025-07-01")
    parser.add_argument("--delay-min", type=float, default=3.0)
    parser.add_argument("--delay-max", type=float, default=6.0)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--report", choices=tuple(REPORTS), default="rentals")
    parser.add_argument(
        "--account-id",
        default="",
        help="Stable non-secret account label recorded in raw rows and checkpoint identities.",
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--manifest-path", type=Path)
    parser.add_argument("--location-inventory", type=Path, default=DEFAULT_LOCATION_INVENTORY)
    parser.add_argument(
        "--verify-manifest",
        action="store_true",
        help="Fail if authenticated filter choices differ from the stored manifest.",
    )
    parser.add_argument(
        "--discover-manifest",
        action="store_true",
        help="Discover authenticated filter options, write --manifest-path, and exit.",
    )
    parser.add_argument(
        "--coverage-validation",
        action="store_true",
        help="Scrape broad/leaf and citywide/area candidates, then select marginal profiles.",
    )
    parser.add_argument(
        "--collection-strategy",
        choices=("split", "paginate"),
        default="split",
        help="Split capped result sets (default) or page the citywide result directly.",
    )
    parser.add_argument(
        "--profile-ids",
        default="",
        help="Comma-separated manifest profile IDs, or 'all', for an isolated diagnostic run.",
    )
    parser.add_argument(
        "--location-ids",
        default="",
        help="Comma-separated manifest location IDs, or 'all', for an isolated diagnostic run.",
    )
    parser.add_argument(
        "--filter-overrides-json",
        default="{}",
        help="JSON map of P74 filter IDs to values; merged with the existing rental profile.",
    )
    parser.add_argument("--inspect-filter-items", action="store_true")
    parser.add_argument("--page-url", default=DXBI_URL)
    parser.add_argument("--area-slug", default="")
    parser.add_argument("--location-id", default=DEFAULT_LOCATION["id"])
    parser.add_argument("--location-text", default=DEFAULT_LOCATION["text"])
    parser.add_argument("--location-slug", default=DEFAULT_LOCATION["slug"])
    return parser.parse_args()


def scrape_configuration(
    *,
    page: Page,
    context: Any,
    credentials: dict[str, str],
    storage_path: Path,
    output_dir: Path,
    configuration: dict[str, Any],
    dates: list[date],
    direction: str,
    template_date: str,
    report: dict[str, str],
    delay_min: float,
    delay_max: float,
    request_limit: int | None,
    collection_strategy: str = "split",
    template_cache: dict[str, dict[str, str]] | None = None,
) -> tuple[str, int]:
    state_path, shard_dir = configuration_paths(output_dir, configuration)
    state = load_state(state_path, configuration)
    state.setdefault("started_at", utc_now())
    current_requests = 0
    ordered_dates = dates if direction == "asc" else list(reversed(dates))
    if all(
        (state["partitions"].get(day.isoformat()) or {}).get("status") == "complete"
        for day in ordered_dates
    ):
        return "complete", 0
    location = {
        "id": configuration["location_id"],
        "text": configuration["location_text"],
        "slug": configuration["location_slug"],
    }
    filters = configuration["filters"]
    template_key = f"{report['region_name']}|{template_date}"
    try:
        template = (template_cache or {}).get(template_key)
        if template is None:
            template = capture_template(page, template_date, filters, report, location)
            if template_cache is not None:
                template_cache[template_key] = template
    except Exception as error:
        reason = f"template_capture_failed: {type(error).__name__}: {error}"
        state["failed"]["configuration"] = {"reason": reason, "failed_at": utc_now()}
        for day in dates:
            state["partitions"][day.isoformat()] = {
                "status": "failed",
                "reason": reason,
                "updated_at": utc_now(),
            }
        atomic_json(state_path, state)
        return "failed", 0
    state["failed"].pop("configuration", None)

    for day in ordered_dates:
        day_key = day.isoformat()
        if (state["partitions"].get(day_key) or {}).get("status") == "complete":
            continue
        queue = initial_shards(day)
        partition_failed = False
        while queue:
            shard = queue.pop(0)
            local_key = shard_key(shard)
            local_root_key = pagination_root_key(shard)
            key = checkpoint_key(configuration, local_key)
            root_key = checkpoint_key(configuration, local_root_key)
            if key == root_key and root_key in state["paged"]:
                children = (
                    split_capped_shard(shard)
                    if collection_strategy == "split"
                    else []
                )
                if children:
                    refine_paged_checkpoint(
                        output_dir=output_dir,
                        state=state,
                        root_key=root_key,
                        children=children,
                        configuration=configuration,
                    )
                    queue = children + queue
                    atomic_json(state_path, state)
                    print(f"REFINE {root_key} children={len(children)}", flush=True)
                    continue
                queue = [
                    {**shard, "page_start": state["paged"][root_key]["next_page_start"]}
                ] + queue
                continue
            if key in state["completed"]:
                continue
            if key in state["expanded"]:
                children = split_capped_shard(shard)
                expected_children = [
                    checkpoint_key(configuration, shard_key(child)) for child in children
                ]
                saved_children = list(state["expanded"][key].get("children") or [])
                if children and saved_children != expected_children:
                    refine_expanded_checkpoint(
                        output_dir=output_dir,
                        state=state,
                        root_key=key,
                        children=children,
                        configuration=configuration,
                    )
                    atomic_json(state_path, state)
                    print(f"REFINE_EXPANSION {key} children={len(children)}", flush=True)
                queue = children + queue
                continue
            if request_limit is not None and current_requests >= request_limit:
                state["partitions"][day_key] = {
                    "status": "incomplete",
                    "reason": "request_budget_exhausted",
                    "updated_at": utc_now(),
                }
                atomic_json(state_path, state)
                return "incomplete", current_requests

            response: dict[str, Any] | None = None
            for attempt in range(1, 4):
                if request_limit is not None and current_requests >= request_limit:
                    break
                try:
                    response = fetch_rows(page, template, shard, filters, location, report)
                except PlaywrightTimeoutError as error:
                    response = {
                        "status": 598,
                        "login_redirect": False,
                        "rows": [],
                        "error": f"PLAYWRIGHT_TIMEOUT: {error}",
                    }
                except Exception as error:
                    response = {
                        "status": 598,
                        "login_redirect": False,
                        "rows": [],
                        "error": f"{type(error).__name__}: {error}",
                    }

                current_requests += 1
                state["requests"] = int(state.get("requests", 0)) + 1
                if response["login_redirect"]:
                    login(page, credentials, report)
                    context.storage_state(path=storage_path)
                    template = capture_template(page, template_date, filters, report, location)
                    if template_cache is not None:
                        template_cache[template_key] = template
                    if attempt < 3:
                        continue
                if response["status"] < 400:
                    break
                if response["status"] in RECOVERABLE_HTTP_STATUSES and attempt < 3:
                    retry_delay = random.uniform(10 * attempt, 20 * attempt)
                    print(
                        f"RETRY {key} status={response['status']} attempt={attempt} "
                        f"error={response.get('error', '')} delay={retry_delay:.1f}s",
                        flush=True,
                    )
                    time.sleep(retry_delay)
                    continue
                break

            budget_exhausted = bool(
                response
                and response["status"] >= 400
                and response["status"] in RECOVERABLE_HTTP_STATUSES
                and request_limit is not None
                and current_requests >= request_limit
            )
            if response is None or response["status"] >= 400:
                reason = (
                    "request_budget_exhausted"
                    if response is None or budget_exhausted
                    else f"HTTP {response['status']}: {response.get('error', '')}"
                )
                state["failed"][key] = {
                    "reason": reason,
                    "failed_at": utc_now(),
                }
                state["partitions"][day_key] = {
                    "status": ("incomplete" if response is None or budget_exhausted else "failed"),
                    "reason": reason,
                    "updated_at": utc_now(),
                }
                atomic_json(state_path, state)
                if response is None or budget_exhausted:
                    return "incomplete", current_requests
                partition_failed = True
                break

            rows = response["rows"]
            state["failed"].pop(key, None)
            page_start = int(shard.get("page_start", 1))
            response_next = response.get("next_page_start")
            next_page_start = int(response_next) if response_next is not None else None
            has_next_page = bool(response.get("has_next_page"))
            reported_total = response.get("reported_total")
            telemetry = {
                "status": int(response["status"]),
                "requested_page_start": page_start,
                "reported_total": reported_total,
                "has_next_page": has_next_page,
                "next_page_start": next_page_start,
                "pagination_text": str(response.get("pagination_text") or "")[:500],
            }
            if page_start > 1 and not rows and root_key in state["paged"]:
                reason = "pagination_invariant_failed: requested page returned no rows"
                state["failed"][key] = {"reason": reason, "failed_at": utc_now(), **telemetry}
                state["partitions"][day_key] = {
                    "status": "failed",
                    "reason": reason,
                    "updated_at": utc_now(),
                }
                atomic_json(state_path, state)
                partition_failed = True
                break
            if has_next_page and (next_page_start is None or next_page_start <= page_start):
                reason = "pagination_invariant_failed: invalid next page"
                state["failed"][key] = {"reason": reason, "failed_at": utc_now(), **telemetry}
                state["partitions"][day_key] = {
                    "status": "failed",
                    "reason": reason,
                    "updated_at": utc_now(),
                }
                atomic_json(state_path, state)
                partition_failed = True
                break
            returned_through = page_start + len(rows) - 1
            if (
                len(rows) < PAGE_SIZE
                and not has_next_page
                and reported_total is not None
                and int(reported_total) > returned_through
            ):
                reason = "pagination_invariant_failed: reported total exceeds returned rows"
                state["failed"][key] = {"reason": reason, "failed_at": utc_now(), **telemetry}
                state["partitions"][day_key] = {
                    "status": "failed",
                    "reason": reason,
                    "updated_at": utc_now(),
                }
                atomic_json(state_path, state)
                partition_failed = True
                break

            direct_page = collection_strategy == "paginate"
            should_page = has_next_page and (direct_page or len(rows) < PAGE_SIZE)
            if direct_page and len(rows) == PAGE_SIZE:
                should_page = True
            if len(rows) < PAGE_SIZE and not should_page:
                digest = hashlib.sha256(key.encode()).hexdigest()[:20]
                relative_path = ""
                if rows:
                    path = shard_dir / f"date={shard['date']}" / f"{digest}.jsonl.gz"
                    write_shard(path, shard, rows, configuration["report_type"], configuration)
                    relative_path = str(path.relative_to(output_dir))
                state["completed"][key] = {
                    "rows": len(rows),
                    "path": relative_path,
                    "completed_at": utc_now(),
                    **telemetry,
                }
                if shard.get("page_start", 1) > 1:
                    state["paged"].pop(root_key, None)
                print(f"COMPLETE {key} rows={len(rows)}", flush=True)
            elif not direct_page and not should_page:
                children = split_capped_shard(shard)
                if children:
                    state["expanded"][key] = {
                        "children": [
                            checkpoint_key(configuration, shard_key(child)) for child in children
                        ],
                        "expanded_at": utc_now(),
                        "rows": len(rows),
                        **telemetry,
                    }
                    queue = children + queue
                    print(f"EXPAND {key} rows={len(rows)}", flush=True)
                    atomic_json(state_path, state)
                    time.sleep(random.uniform(delay_min, delay_max))
                    continue
                should_page = True

            if should_page or len(rows) == PAGE_SIZE:
                if (
                    not has_next_page
                    and reported_total is not None
                    and int(reported_total) <= returned_through
                ):
                    should_page = False
                if not should_page:
                    digest = hashlib.sha256(key.encode()).hexdigest()[:20]
                    relative_path = ""
                    if rows:
                        path = shard_dir / f"date={shard['date']}" / f"{digest}.jsonl.gz"
                        write_shard(path, shard, rows, configuration["report_type"], configuration)
                        relative_path = str(path.relative_to(output_dir))
                    state["completed"][key] = {
                        "rows": len(rows),
                        "path": relative_path,
                        "completed_at": utc_now(),
                        **telemetry,
                    }
                    if page_start > 1:
                        state["paged"].pop(root_key, None)
                    print(f"COMPLETE {key} rows={len(rows)}", flush=True)
                else:
                    digest = hashlib.sha256(key.encode()).hexdigest()[:20]
                    path = shard_dir / f"date={shard['date']}" / f"{digest}.jsonl.gz"
                    write_shard(path, shard, rows, configuration["report_type"], configuration)
                    state["completed"][key] = {
                        "rows": len(rows),
                        "path": str(path.relative_to(output_dir)),
                        "completed_at": utc_now(),
                        **telemetry,
                    }
                    next_page_start = next_page_start or page_start + PAGE_SIZE
                    state["paged"][root_key] = {
                        "next_page_start": next_page_start,
                        "paged_at": utc_now(),
                    }
                    queue = [{**shard, "page_start": next_page_start}] + queue
                    print(f"PAGE {key} rows={len(rows)} next={next_page_start}", flush=True)
            atomic_json(state_path, state)
            time.sleep(random.uniform(delay_min, delay_max))

        if not partition_failed:
            state["partitions"][day_key] = {
                "status": "complete",
                "completed_at": utc_now(),
            }
            atomic_json(state_path, state)
    return ("failed" if state["failed"] else "complete"), current_requests


def main() -> int:
    args = parse_args()
    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
    if start > end:
        raise ValueError("start date must be on or before end date")
    dates = list(dates_between(start, end, "asc"))
    explicit_selection = bool(args.profile_ids.strip() or args.location_ids.strip())
    if args.coverage_validation and explicit_selection:
        raise ValueError("--coverage-validation cannot be combined with explicit selections")
    if explicit_selection and not args.manifest_path:
        raise ValueError("explicit profile/location selections require --manifest-path")
    supplied_overrides = json.loads(args.filter_overrides_json)
    if not isinstance(supplied_overrides, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in supplied_overrides.items()
    ):
        raise ValueError("--filter-overrides-json must be a JSON object of string values")

    report = REPORTS[args.report]
    filter_overrides = {**DEFAULT_FILTER_OVERRIDES, **supplied_overrides}
    filter_overrides["P74_DEAL"] = report["deal"]
    location = {
        "id": args.location_id,
        "text": args.location_text,
        "slug": args.location_slug,
    }
    credentials_path = Path(args.credentials)
    account = args.account_id or credentials_path.stem
    if not account:
        raise ValueError("--account-id must not be blank")
    credentials = json.loads(credentials_path.read_text())
    if not credentials.get("email") or not credentials.get("password"):
        raise RuntimeError("credentials contain a blank email or password")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir.chmod(0o700)
    success_path = output_dir / "_SUCCESS"
    success_path.unlink(missing_ok=True)
    storage_path = Path(args.storage_state)
    manifest: dict[str, Any] | None = None
    if args.manifest_path and args.manifest_path.exists():
        manifest = json.loads(args.manifest_path.read_text())
        if int(manifest.get("manifest_version") or 0) != MANIFEST_VERSION:
            raise ValueError(
                f"unsupported rental manifest version: {manifest.get('manifest_version')}"
            )
        if manifest.get("manifest_hash") != manifest_hash(manifest):
            raise RuntimeError("rental manifest hash does not match its profile/location contents")
        if (
            args.report == "rentals"
            and not args.coverage_validation
            and not args.discover_manifest
            and not explicit_selection
            and (manifest.get("validation") or {}).get("status") != "complete"
        ):
            raise RuntimeError(
                "rental manifest has not passed broad/leaf and citywide/area validation"
            )
    elif args.manifest_path and not args.discover_manifest:
        raise FileNotFoundError(args.manifest_path)
    if (args.discover_manifest or args.coverage_validation) and args.report != "rentals":
        raise ValueError("rental manifest discovery and validation require --report rentals")
    if args.discover_manifest and not args.manifest_path:
        raise ValueError("--discover-manifest requires --manifest-path")

    configurations: list[dict[str, Any]] = []
    template_cache: dict[str, dict[str, str]] = {}
    total_requests = 0
    statuses: list[str] = []
    with virtual_display(), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.browser,
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context_kwargs: dict[str, Any] = {"user_agent": USER_AGENT}
        if storage_path.exists():
            context_kwargs["storage_state"] = str(storage_path)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_timeout(FETCH_EVAL_TIMEOUT_MS)
        page.set_default_navigation_timeout(FETCH_EVAL_TIMEOUT_MS)
        try:
            login(page, credentials, report)
            if args.page_url != DXBI_URL:
                page.goto(args.page_url, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(3_000)
            if args.area_slug:
                page.locator(f'a[href*="/dubai-house-prices/{args.area_slug}"]').first.click(
                    timeout=20_000
                )
                page.wait_for_timeout(4_000)
            context.storage_state(path=storage_path)
            storage_path.chmod(0o600)

            if args.report == "rentals" and (
                args.verify_manifest or args.discover_manifest or args.inspect_filter_items
            ):
                apply_report_profile(page, filter_overrides)

            if args.verify_manifest:
                if not manifest or args.report != "rentals":
                    raise ValueError("--verify-manifest requires a rental --manifest-path")
                discovered_options = discover_filter_options(page)
                validate_filter_discovery(discovered_options, filter_overrides)
                if filter_options_signature(discovered_options) != filter_options_signature(
                    manifest.get("filter_options") or {}
                ):
                    raise RuntimeError(
                        "authenticated rental filter options changed; rediscover and validate "
                        "the rental manifest"
                    )

            if args.inspect_filter_items:
                inspection = inspect_filter_page(page)
                inspection["filter_options"] = discover_filter_options(page)
                print(json.dumps(inspection, indent=2, sort_keys=True))
                return 0
            if args.discover_manifest:
                locations = read_location_inventory(args.location_inventory)
                discovered_options = discover_filter_options(page)
                validate_filter_discovery(discovered_options, filter_overrides)
                manifest = build_rental_manifest(
                    discovered_options=discovered_options,
                    default_filters=filter_overrides,
                    locations=locations,
                )
                atomic_json(args.manifest_path, manifest)
                print(
                    json.dumps({"status": "manifest_discovered", "path": str(args.manifest_path)})
                )
                return 0

            if manifest:
                def selected_ids(raw: str, records: list[dict[str, Any]]) -> set[str] | None:
                    values = {value.strip() for value in raw.split(",") if value.strip()}
                    if not values:
                        return None
                    if values == {"all"}:
                        return {str(record["id"]) for record in records}
                    if "all" in values:
                        raise ValueError("'all' cannot be combined with explicit IDs")
                    return values

                configurations = manifest_configurations(
                    manifest,
                    account=account,
                    validation_candidates=args.coverage_validation,
                    profile_ids=selected_ids(args.profile_ids, list(manifest.get("profiles") or [])),
                    location_ids=selected_ids(
                        args.location_ids, list(manifest.get("locations") or [])
                    ),
                )
            else:
                configurations = [
                    _singleton_configuration(
                        report=report,
                        report_name=args.report,
                        account=account,
                        filters=filter_overrides,
                        location=location,
                    )
                ]

            for configuration in configurations:
                configuration["source_run_id"] = args.run_id or output_dir.name.removeprefix("run=")
                configuration["collection_strategy"] = args.collection_strategy
                configuration["collector_version"] = COLLECTOR_VERSION
                configuration["configuration_hash"] = configuration_hash(configuration)
                remaining = None
                if args.max_requests:
                    remaining = max(args.max_requests - total_requests, 0)
                status, used = scrape_configuration(
                    page=page,
                    context=context,
                    credentials=credentials,
                    storage_path=storage_path,
                    output_dir=output_dir,
                    configuration=configuration,
                    dates=dates,
                    direction=args.direction,
                    template_date=args.template_date,
                    report=report,
                    delay_min=args.delay_min,
                    delay_max=args.delay_max,
                    request_limit=remaining,
                    collection_strategy=args.collection_strategy,
                    template_cache=template_cache,
                )
                total_requests += used
                statuses.append(status)
                if status == "incomplete":
                    break
        finally:
            context.close()
            browser.close()

    if args.coverage_validation and manifest and all(status == "complete" for status in statuses):
        manifest = select_marginal_coverage(manifest, _collected_fingerprints(output_dir))
        if not args.manifest_path:
            raise ValueError("--coverage-validation requires --manifest-path")
        atomic_json(args.manifest_path, manifest)

    status = "success"
    if any(item == "incomplete" for item in statuses):
        status = "incomplete"
    elif any(item == "failed" for item in statuses):
        status = "failed"
    reconciliation = write_run_reconciliation(
        output_dir=output_dir,
        configurations=configurations,
        dates=dates,
        status=status,
        run_requests=total_requests,
        manifest_hash=str((manifest or {}).get("manifest_hash") or "unmanaged"),
    )
    if (
        status == "success"
        and reconciliation["completed_partitions"] == reconciliation["expected_partitions"]
    ):
        success_path.touch()
        (output_dir / "_FAILURE").unlink(missing_ok=True)
        print(json.dumps(reconciliation, sort_keys=True))
        return 0

    atomic_json(
        output_dir / "_FAILURE",
        {"status": status, "failed_at": utc_now(), "reconciliation": reconciliation},
    )
    print(json.dumps(reconciliation, sort_keys=True))
    return 2 if status == "incomplete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
