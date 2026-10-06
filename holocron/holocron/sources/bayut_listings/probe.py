"""Bounded Playwright experiments for measuring Bayut access challenges."""

from __future__ import annotations

import hashlib
import json
import os
import random
import statistics
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    Request,
    Route,
    sync_playwright,
)
from pydantic import Field, model_validator

from holocron.pydantic_helpers import CsvTuple, HolocronModel, NonBlankStr
from holocron.sources.bayut_listings.extract import (
    _BLOCKED_RESOURCE_TYPES,
    _DETAIL_URL_RE,
    _PRICE_RE,
    _SIZE_RE,
    _is_captcha_page,
    _listing_cards,
    _search_url,
)
from holocron.sources.bayut_listings.source import (
    BAYUT_BASE_URL,
    BAYUT_DEFAULT_SEARCH_PATHS,
)

_EVENTS_FILE = "events.jsonl"
_PLAN_FILE = "plan.json"
_SUMMARY_FILE = "summary.json"
_PROXY_SERVER_ENV = "BAYUT_PROBE_PROXY_SERVER"
_PROXY_USERNAME_ENV = "BAYUT_PROBE_PROXY_USERNAME"
_PROXY_PASSWORD_ENV = "BAYUT_PROBE_PROXY_PASSWORD"
_SESSION_PLACEHOLDER = "{session}"
_TERMINAL_OUTCOMES = frozenset(
    {
        "captcha",
        "forbidden",
        "rate_limited",
        "http_error",
        "navigation_error",
        "empty",
        "duplicate",
    }
)


class BayutProbeCohort(HolocronModel):
    """One controlled combination of network identity and browser state."""

    name: NonBlankStr
    trials: int = Field(default=1, ge=1, le=20)
    proxy: Literal["direct", "residential"] = "direct"
    proxy_session_scope: Literal["provider_default", "trial", "page"] = "provider_default"
    isolation: Literal["reuse_context", "fresh_context", "fresh_browser"] = "reuse_context"
    browser_state: Literal["reset", "carry"] = "reset"
    identity_check_scope: Literal["off", "trial", "page"] = "off"
    pause_seconds: float = Field(default=3, ge=0, le=300)
    jitter_seconds: float = Field(default=0, ge=0, le=300)
    block_media_requests: bool = True

    @model_validator(mode="after")
    def validate_cohort(self) -> "BayutProbeCohort":
        if self.proxy == "direct" and self.proxy_session_scope != "provider_default":
            raise ValueError("direct cohorts must use proxy_session_scope=provider_default")
        if self.proxy_session_scope == "page" and self.isolation == "reuse_context":
            raise ValueError("page-scoped proxy sessions require a fresh context or browser")
        if self.browser_state == "carry" and self.isolation == "reuse_context":
            raise ValueError("reuse_context already preserves state; use browser_state=reset")
        return self


class BayutProbePlan(HolocronModel):
    """Validated experiment plan without proxy credentials."""

    base_url: NonBlankStr = BAYUT_BASE_URL
    search_paths: CsvTuple = BAYUT_DEFAULT_SEARCH_PATHS
    start_page: int = Field(default=1, ge=1)
    max_pages_per_trial: int = Field(default=10, ge=1, le=500)
    timeout_seconds: float = Field(default=60, ge=1, le=300)
    settle_milliseconds: int = Field(default=750, ge=0, le=30_000)
    headless: bool = True
    browser: Literal["chromium", "firefox", "webkit"] = "chromium"
    chrome_path: str = ""
    storage_state_path: str = ""
    identity_url: str = ""
    expected_country: str = ""
    require_identity_success: bool = True
    correlation_header_name: str = ""
    evidence: Literal["none", "challenge", "all"] = "challenge"
    random_seed: int = 20260829
    cohorts: tuple[BayutProbeCohort, ...]

    @model_validator(mode="after")
    def validate_plan(self) -> "BayutProbePlan":
        if not self.cohorts:
            raise ValueError("cohorts must contain at least one experiment cohort")
        if not self.search_paths:
            raise ValueError("search_paths must contain at least one search path")
        names = [cohort.name for cohort in self.cohorts]
        if len(names) != len(set(names)):
            raise ValueError("cohort names must be unique")
        if self.chrome_path and self.browser != "chromium":
            raise ValueError("chrome_path is only valid with browser=chromium")
        if any(cohort.identity_check_scope != "off" for cohort in self.cohorts):
            if not self.identity_url:
                raise ValueError("identity_url is required when identity checks are enabled")
            if "REPLACE-" in self.identity_url.upper():
                raise ValueError("replace the identity_url placeholder before running the plan")
        if self.require_identity_success:
            for cohort in self.cohorts:
                if cohort.proxy == "residential" and cohort.identity_check_scope == "off":
                    raise ValueError(f"residential cohort {cohort.name!r} requires identity checks")
                if cohort.proxy_session_scope == "page" and cohort.identity_check_scope != "page":
                    raise ValueError(
                        f"page-rotating cohort {cohort.name!r} requires page identity checks"
                    )
        if self.correlation_header_name and not all(
            character.isalnum() or character == "-" for character in self.correlation_header_name
        ):
            raise ValueError("correlation_header_name may only contain letters, numbers, and -")
        total_pages = (
            sum(cohort.trials for cohort in self.cohorts)
            * len(self.search_paths)
            * self.max_pages_per_trial
        )
        if total_pages > 2_000:
            raise ValueError("experiment plan exceeds the 2,000 top-level page safety limit")
        return self


@dataclass(frozen=True, slots=True)
class TrialTask:
    cohort: BayutProbeCohort
    trial: int
    search_path: str


@dataclass(slots=True)
class NetworkMeter:
    requested: Counter[str] = field(default_factory=Counter)
    finished: Counter[str] = field(default_factory=Counter)
    failed: Counter[str] = field(default_factory=Counter)
    blocked: Counter[str] = field(default_factory=Counter)
    request_bytes: int = 0
    response_bytes: int = 0

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
            "finished_by_type": dict(sorted(self.finished.items())),
            "failed_by_type": dict(sorted(self.failed.items())),
            "blocked_by_type": dict(sorted(self.blocked.items())),
        }


@dataclass(slots=True)
class BrowserResources:
    browser: Browser
    context: BrowserContext
    page: Page

    def close_context(self) -> None:
        self.context.close()

    def close_all(self) -> None:
        self.context.close()
        self.browser.close()


def load_probe_plan(path: str | Path) -> BayutProbePlan:
    plan_path = Path(path)
    return BayutProbePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))


def build_trial_schedule(plan: BayutProbePlan) -> list[TrialTask]:
    tasks = [
        TrialTask(cohort=cohort, trial=trial, search_path=search_path)
        for cohort in plan.cohorts
        for trial in range(1, cohort.trials + 1)
        for search_path in plan.search_paths
    ]
    random.Random(plan.random_seed).shuffle(tasks)
    return tasks


def validate_proxy_environment(plan: BayutProbePlan, env: Mapping[str, str] | None = None) -> None:
    values = env if env is not None else os.environ
    proxied = [cohort for cohort in plan.cohorts if cohort.proxy == "residential"]
    if not proxied:
        return
    server = values.get(_PROXY_SERVER_ENV, "").strip()
    if not server:
        raise ValueError(f"{_PROXY_SERVER_ENV} is required for residential cohorts")
    templates = (
        server,
        values.get(_PROXY_USERNAME_ENV, ""),
        values.get(_PROXY_PASSWORD_ENV, ""),
    )
    needs_session = any(cohort.proxy_session_scope in {"trial", "page"} for cohort in proxied)
    if needs_session and not any(_SESSION_PLACEHOLDER in value for value in templates):
        raise ValueError(
            "trial/page proxy rotation requires {session} in the proxy server, username, "
            "or password environment value"
        )


def sanitized_plan(plan: BayutProbePlan) -> dict[str, Any]:
    payload = plan.model_dump(mode="json")
    payload["proxy_environment"] = {
        "server": _PROXY_SERVER_ENV,
        "username": _PROXY_USERNAME_ENV,
        "password": _PROXY_PASSWORD_ENV,
    }
    payload["credentials_recorded"] = False
    return payload


def run_probe(
    *,
    plan: BayutProbePlan,
    output_root: str | Path,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Run a bounded plan and return its unique evidence directory."""

    values = env if env is not None else os.environ
    validate_proxy_environment(plan, values)
    if plan.storage_state_path and not Path(plan.storage_state_path).is_file():
        raise FileNotFoundError(f"Bayut storage state not found: {plan.storage_state_path}")

    run_id = f"bayut-probe-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / _PLAN_FILE).write_text(
        json.dumps(sanitized_plan(plan), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    events_path = run_dir / _EVENTS_FILE

    with sync_playwright() as playwright, events_path.open("a", encoding="utf-8") as events:
        for schedule_index, task in enumerate(build_trial_schedule(plan), start=1):
            rows = _run_trial(
                playwright=playwright,
                plan=plan,
                task=task,
                run_id=run_id,
                run_dir=run_dir,
                schedule_index=schedule_index,
                env=values,
            )
            for row in rows:
                events.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
                events.flush()

    summary = summarize_probe_events(load_probe_events(events_path))
    (run_dir / _SUMMARY_FILE).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run_dir


def load_probe_events(path: str | Path) -> list[dict[str, Any]]:
    event_path = Path(path)
    if event_path.is_dir():
        event_path = event_path / _EVENTS_FILE
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        event_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"expected object at {event_path}:{line_number}")
        rows.append(row)
    return rows


def summarize_probe_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[str(event.get("cohort") or "unknown")].append(event)

    cohorts: dict[str, Any] = {}
    for cohort_name, rows in sorted(grouped.items()):
        trials: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            trial_key = (
                str(row.get("search_path") or "unknown"),
                int(row.get("trial") or 0),
            )
            trials[trial_key].append(row)

        observed_onsets: list[int] = []
        challenged_trials = 0
        for trial_rows in trials.values():
            challenge_rows = [row for row in trial_rows if row.get("outcome") == "captcha"]
            if challenge_rows:
                challenged_trials += 1
                observed_onsets.append(
                    min(int(row.get("page_in_trial") or 0) for row in challenge_rows)
                )

        cards = sum(int(row.get("card_count") or 0) for row in rows)
        new_cards = sum(int(row.get("new_listing_count") or 0) for row in rows)
        successful_rows = [row for row in rows if row.get("outcome") in {"ok", "duplicate"}]
        successful_cards = sum(int(row.get("card_count") or 0) for row in successful_rows)
        latencies = [float(row.get("latency_ms") or 0) for row in rows]
        identity_samples = {
            str(row.get("identity", {}).get("sample_id")): row.get("identity", {})
            for row in rows
            if isinstance(row.get("identity"), Mapping) and row.get("identity", {}).get("sample_id")
        }
        successful_identity_samples = [
            sample
            for sample in identity_samples.values()
            if sample.get("ip") and not sample.get("error")
        ]
        observed_ips = {str(sample.get("ip")) for sample in successful_identity_samples}
        observed_asns = [
            str(sample.get("asn")) for sample in successful_identity_samples if sample.get("asn")
        ]
        countries = [
            str(sample.get("country"))
            for sample in successful_identity_samples
            if sample.get("country")
        ]
        expected_country = next(
            (str(row.get("expected_country")) for row in rows if row.get("expected_country")),
            "",
        )
        country_matches = (
            sum(country.upper() == expected_country.upper() for country in countries)
            if expected_country
            else 0
        )
        field_counts: Counter[str] = Counter()
        for row in rows:
            coverage = row.get("card_field_counts")
            if isinstance(coverage, Mapping):
                for key, value in coverage.items():
                    field_counts[str(key)] += int(value or 0)
        response_bytes = sum(
            int(row.get("network", {}).get("response_bytes") or 0)
            for row in rows
            if isinstance(row.get("network"), Mapping)
        )
        request_count = sum(
            int(row.get("network", {}).get("request_count") or 0)
            for row in rows
            if isinstance(row.get("network"), Mapping)
        )
        outcome_counts = Counter(str(row.get("outcome") or "unknown") for row in rows)
        page_errors = sum(outcome_counts[outcome] for outcome in ("http_error", "navigation_error"))
        search_path_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            search_path_rows[str(row.get("search_path") or "unknown")].append(row)
        cohorts[cohort_name] = {
            "trials": len(trials),
            "page_attempts": len(rows),
            "outcomes": dict(sorted(outcome_counts.items())),
            "challenged_trials": challenged_trials,
            "censored_trials_without_challenge": len(trials) - challenged_trials,
            "median_observed_challenge_page": (
                statistics.median(observed_onsets) if observed_onsets else None
            ),
            "observed_challenge_pages": observed_onsets,
            "latency_ms_p50": _percentile(latencies, 0.50),
            "latency_ms_p95": _percentile(latencies, 0.95),
            "page_error_rate": round(page_errors / len(rows), 6) if rows else None,
            "mean_cards_per_successful_page": round(successful_cards / len(successful_rows), 3)
            if successful_rows
            else None,
            "duplicate_card_rate": round((cards - new_cards) / cards, 6) if cards else None,
            "card_field_availability": {
                key: round(value / cards, 6) if cards else None
                for key, value in sorted(field_counts.items())
            },
            "network_request_count": request_count,
            "mean_network_requests_per_page": round(request_count / len(rows), 3) if rows else None,
            "network_response_megabytes": round(response_bytes / 1_000_000, 3),
            "identity_samples": len(identity_samples),
            "identity_error_samples": sum(
                bool(sample.get("error")) for sample in identity_samples.values()
            ),
            "unique_observed_ips": len(observed_ips),
            "proxy_ip_uniqueness_ratio": (
                round(len(observed_ips) / len(successful_identity_samples), 6)
                if successful_identity_samples
                else None
            ),
            "observed_countries": dict(sorted(Counter(countries).items())),
            "observed_asns": dict(sorted(Counter(observed_asns).items())),
            "expected_country_match_rate": (
                round(country_matches / len(countries), 6)
                if expected_country and countries
                else None
            ),
            "search_paths": {
                search_path: _summarize_search_path(path_rows)
                for search_path, path_rows in sorted(search_path_rows.items())
            },
        }

    return {
        "schema_version": 1,
        "event_count": len(events),
        "cohorts": cohorts,
        "interpretation_note": (
            "Trials without a challenge are right-censored. Compare challenge onset only after "
            "checking observed IP uniqueness, country consistency, errors, cadence, and bandwidth."
        ),
    }


def _summarize_search_path(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    trials: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        trials[int(row.get("trial") or 0)].append(row)
    observed_onsets: list[int] = []
    for trial_rows in trials.values():
        challenge_pages = [
            int(row.get("page_in_trial") or 0)
            for row in trial_rows
            if row.get("outcome") == "captcha"
        ]
        if challenge_pages:
            observed_onsets.append(min(challenge_pages))
    outcome_counts = Counter(str(row.get("outcome") or "unknown") for row in rows)
    successful_rows = [row for row in rows if row.get("outcome") in {"ok", "duplicate"}]
    cards = sum(int(row.get("card_count") or 0) for row in successful_rows)
    response_bytes = sum(
        int(row.get("network", {}).get("response_bytes") or 0)
        for row in rows
        if isinstance(row.get("network"), Mapping)
    )
    latencies = [float(row.get("latency_ms") or 0) for row in rows]
    return {
        "trials": len(trials),
        "page_attempts": len(rows),
        "outcomes": dict(sorted(outcome_counts.items())),
        "challenged_trials": len(observed_onsets),
        "censored_trials_without_challenge": len(trials) - len(observed_onsets),
        "median_observed_challenge_page": (
            statistics.median(observed_onsets) if observed_onsets else None
        ),
        "latency_ms_p50": _percentile(latencies, 0.50),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "mean_cards_per_successful_page": (
            round(cards / len(successful_rows), 3) if successful_rows else None
        ),
        "network_response_megabytes": round(response_bytes / 1_000_000, 3),
    }


def _run_trial(
    *,
    playwright: Playwright,
    plan: BayutProbePlan,
    task: TrialTask,
    run_id: str,
    run_dir: Path,
    schedule_index: int,
    env: Mapping[str, str],
) -> Iterator[dict[str, Any]]:
    cohort = task.cohort
    trial_session = _new_session_id() if cohort.proxy_session_scope == "trial" else ""
    seen_listing_ids: set[str] = set()
    identity_cache: dict[str, Any] | None = None
    shared_resources: BrowserResources | None = None
    shared_browser: Browser | None = None
    jitter = random.Random(f"{plan.random_seed}:{schedule_index}")

    with tempfile.TemporaryDirectory(prefix="bayut-probe-state-") as state_dir:
        carried_state_path = Path(state_dir) / "storage-state.json"
        current_state_path = plan.storage_state_path or ""
        try:
            if cohort.isolation == "reuse_context":
                shared_resources = _new_resources(
                    playwright=playwright,
                    plan=plan,
                    proxy=_proxy_settings(
                        cohort=cohort,
                        session_id=trial_session,
                        env=env,
                    ),
                    storage_state_path=current_state_path,
                )
            elif cohort.isolation == "fresh_context":
                shared_browser = _launch_browser(playwright=playwright, plan=plan)

            for page_in_trial in range(1, plan.max_pages_per_trial + 1):
                page_number = plan.start_page + page_in_trial - 1
                page_session = (
                    _new_session_id() if cohort.proxy_session_scope == "page" else trial_session
                )
                resources, close_mode = _resources_for_observation(
                    playwright=playwright,
                    plan=plan,
                    cohort=cohort,
                    shared_resources=shared_resources,
                    shared_browser=shared_browser,
                    proxy=_proxy_settings(cohort=cohort, session_id=page_session, env=env),
                    storage_state_path=current_state_path,
                )
                try:
                    if cohort.identity_check_scope == "page" or (
                        cohort.identity_check_scope == "trial" and identity_cache is None
                    ):
                        identity_cache = _check_identity(
                            context=resources.context,
                            url=plan.identity_url,
                            timeout_seconds=plan.timeout_seconds,
                        )
                        if plan.require_identity_success:
                            validate_identity_result(
                                identity_cache,
                                expected_country=plan.expected_country,
                            )
                    observation_id = (
                        f"{run_id}-{schedule_index:03d}-{task.trial:02d}-{page_in_trial:03d}"
                    )
                    row = _observe_page(
                        resources=resources,
                        plan=plan,
                        cohort=cohort,
                        run_id=run_id,
                        observation_id=observation_id,
                        schedule_index=schedule_index,
                        trial=task.trial,
                        page_in_trial=page_in_trial,
                        page_number=page_number,
                        search_path=task.search_path,
                        proxy_session_id=page_session,
                        identity=identity_cache,
                        seen_listing_ids=seen_listing_ids,
                        run_dir=run_dir,
                    )
                    yield row
                    if (
                        cohort.browser_state == "carry"
                        and cohort.isolation != "reuse_context"
                        and row["outcome"] not in _TERMINAL_OUTCOMES
                    ):
                        resources.context.storage_state(path=carried_state_path)
                        current_state_path = str(carried_state_path)
                finally:
                    if close_mode == "context":
                        resources.close_context()
                    elif close_mode == "all":
                        resources.close_all()

                if row["outcome"] in _TERMINAL_OUTCOMES:
                    break
                if cohort.pause_seconds or cohort.jitter_seconds:
                    pause = cohort.pause_seconds + jitter.uniform(0, cohort.jitter_seconds)
                    time.sleep(pause)
        finally:
            if shared_resources is not None:
                shared_resources.close_all()
            if shared_browser is not None:
                shared_browser.close()


def _resources_for_observation(
    *,
    playwright: Playwright,
    plan: BayutProbePlan,
    cohort: BayutProbeCohort,
    shared_resources: BrowserResources | None,
    shared_browser: Browser | None,
    proxy: dict[str, str] | None,
    storage_state_path: str,
) -> tuple[BrowserResources, Literal["none", "context", "all"]]:
    if cohort.isolation == "reuse_context":
        if shared_resources is None:
            raise RuntimeError("missing shared browser context")
        return shared_resources, "none"
    if cohort.isolation == "fresh_context":
        if shared_browser is None:
            raise RuntimeError("missing shared browser")
        context = _new_context(
            browser=shared_browser,
            proxy=proxy,
            storage_state_path=storage_state_path,
        )
        return BrowserResources(shared_browser, context, context.new_page()), "context"
    resources = _new_resources(
        playwright=playwright,
        plan=plan,
        proxy=proxy,
        storage_state_path=storage_state_path,
    )
    return resources, "all"


def _new_resources(
    *,
    playwright: Playwright,
    plan: BayutProbePlan,
    proxy: dict[str, str] | None,
    storage_state_path: str,
) -> BrowserResources:
    browser = _launch_browser(playwright=playwright, plan=plan)
    try:
        context = _new_context(
            browser=browser,
            proxy=proxy,
            storage_state_path=storage_state_path,
        )
    except Exception:
        browser.close()
        raise
    return BrowserResources(browser=browser, context=context, page=context.new_page())


def _launch_browser(*, playwright: Playwright, plan: BayutProbePlan) -> Browser:
    browser_type = getattr(playwright, plan.browser)
    launch_kwargs: dict[str, Any] = {"headless": plan.headless}
    if plan.chrome_path:
        launch_kwargs["executable_path"] = plan.chrome_path
    return browser_type.launch(**launch_kwargs)


def _new_context(
    *,
    browser: Browser,
    proxy: dict[str, str] | None,
    storage_state_path: str,
) -> BrowserContext:
    kwargs: dict[str, Any] = {"service_workers": "block"}
    if proxy:
        kwargs["proxy"] = proxy
    if storage_state_path:
        kwargs["storage_state"] = storage_state_path
    return browser.new_context(**kwargs)


def _observe_page(
    *,
    resources: BrowserResources,
    plan: BayutProbePlan,
    cohort: BayutProbeCohort,
    run_id: str,
    observation_id: str,
    schedule_index: int,
    trial: int,
    page_in_trial: int,
    page_number: int,
    search_path: str,
    proxy_session_id: str,
    identity: Mapping[str, Any] | None,
    seen_listing_ids: set[str],
    run_dir: Path,
) -> dict[str, Any]:
    page = resources.page
    meter = NetworkMeter()
    bayut_host = urlsplit(plan.base_url).hostname

    def block_resources(route: Route) -> None:
        request = route.request
        resource_type = request.resource_type
        if cohort.block_media_requests and resource_type in _BLOCKED_RESOURCE_TYPES:
            meter.blocked[resource_type] += 1
            route.abort()
            return
        if plan.correlation_header_name and urlsplit(request.url).hostname == bayut_host:
            headers = dict(request.headers)
            headers[plan.correlation_header_name] = observation_id
            route.continue_(headers=headers)
            return
        route.continue_()

    def on_request(request: Request) -> None:
        meter.on_request(request)

    def on_finished(request: Request) -> None:
        meter.on_finished(request)

    def on_failed(request: Request) -> None:
        meter.on_failed(request)

    page.on("request", on_request)
    page.on("requestfinished", on_finished)
    page.on("requestfailed", on_failed)
    page.route("**/*", block_resources)

    requested_url = _search_url(
        base_url=plan.base_url,
        search_path=search_path,
        page_number=page_number,
    )
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    status_code = 0
    navigation_error = ""
    html = ""
    cards: list[dict[str, str]] = []
    try:
        response = page.goto(
            requested_url,
            wait_until="domcontentloaded",
            timeout=int(plan.timeout_seconds * 1000),
        )
        status_code = response.status if response is not None else 0
        if plan.settle_milliseconds:
            page.wait_for_timeout(plan.settle_milliseconds)
        html = page.content()
        cards = _listing_cards(page)
    except PlaywrightError as exc:
        navigation_error = f"{type(exc).__name__}: {exc}"[:500]
        try:
            html = page.content()
        except PlaywrightError:
            html = ""
    finally:
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        page.unroute("**/*", block_resources)
        page.remove_listener("request", on_request)
        page.remove_listener("requestfinished", on_finished)
        page.remove_listener("requestfailed", on_failed)

    final_url = page.url
    outcome = classify_probe_outcome(
        final_url=final_url,
        html=html,
        status_code=status_code,
        card_count=len(cards),
        navigation_error=navigation_error,
    )
    listing_ids = _listing_ids(cards)
    new_listing_ids = [
        listing_id for listing_id in listing_ids if listing_id not in seen_listing_ids
    ]
    if outcome == "ok" and listing_ids and not new_listing_ids:
        outcome = "duplicate"
    seen_listing_ids.update(listing_ids)
    evidence = _write_evidence(
        page=page,
        html=html,
        observation_id=observation_id,
        run_dir=run_dir,
        evidence_mode=plan.evidence,
        outcome=outcome,
    )

    return {
        "schema_version": 1,
        "event": "page_observation",
        "run_id": run_id,
        "observation_id": observation_id,
        "cohort": cohort.name,
        "schedule_index": schedule_index,
        "trial": trial,
        "page_in_trial": page_in_trial,
        "page_number": page_number,
        "search_path": search_path,
        "started_at": started_at,
        "latency_ms": latency_ms,
        "requested_url": requested_url,
        "final_url": final_url,
        "status_code": status_code,
        "outcome": outcome,
        "navigation_error": navigation_error,
        "proxy": cohort.proxy,
        "proxy_session_scope": cohort.proxy_session_scope,
        "proxy_session_id": proxy_session_id,
        "isolation": cohort.isolation,
        "browser_state": cohort.browser_state,
        "pause_seconds": cohort.pause_seconds,
        "jitter_seconds": cohort.jitter_seconds,
        "block_media_requests": cohort.block_media_requests,
        "correlation_header_name": plan.correlation_header_name,
        "identity": dict(identity or {}),
        "expected_country": plan.expected_country,
        "card_count": len(cards),
        "listing_ids": listing_ids,
        "new_listing_count": len(new_listing_ids),
        "duplicate_listing_count": len(listing_ids) - len(new_listing_ids),
        "card_field_counts": _card_field_counts(cards),
        "cards": cards,
        "network": meter.as_dict(),
        "html_bytes": len(html.encode("utf-8")),
        "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "evidence": evidence,
    }


def classify_probe_outcome(
    *,
    final_url: str,
    html: str,
    status_code: int,
    card_count: int,
    navigation_error: str,
) -> str:
    if _is_captcha_page(final_url=final_url, html=html):
        return "captcha"
    if status_code == 429:
        return "rate_limited"
    if status_code == 403:
        return "forbidden"
    if status_code >= 400:
        return "http_error"
    if navigation_error:
        return "navigation_error"
    if card_count == 0:
        return "empty"
    return "ok"


def _proxy_settings(
    *, cohort: BayutProbeCohort, session_id: str, env: Mapping[str, str]
) -> dict[str, str] | None:
    if cohort.proxy == "direct":
        return None
    values = {
        "server": env.get(_PROXY_SERVER_ENV, "").strip(),
        "username": env.get(_PROXY_USERNAME_ENV, ""),
        "password": env.get(_PROXY_PASSWORD_ENV, ""),
    }
    if cohort.proxy_session_scope in {"trial", "page"}:
        values = {
            key: value.replace(_SESSION_PLACEHOLDER, session_id) for key, value in values.items()
        }
    return {key: value for key, value in values.items() if value}


def _check_identity(*, context: BrowserContext, url: str, timeout_seconds: float) -> dict[str, Any]:
    sample_id = uuid.uuid4().hex
    started = time.monotonic()
    try:
        response = context.request.get(url, timeout=int(timeout_seconds * 1000))
        status_code = response.status
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("identity endpoint did not return a JSON object")
        identity: dict[str, Any] = dict(parse_identity_payload(payload))
        identity.update(
            {
                "sample_id": sample_id,
                "status_code": status_code,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "error": "" if response.ok else f"HTTP {status_code}",
            }
        )
        return identity
    except Exception as exc:
        return {
            "sample_id": sample_id,
            "status_code": 0,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "ip": "",
            "country": "",
            "asn": "",
            "org": "",
            "error": f"{type(exc).__name__}: {exc}"[:500],
        }


def parse_identity_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    ip = payload.get("ip") or payload.get("query") or payload.get("origin") or ""
    country = payload.get("country") or payload.get("countryCode") or ""
    raw_asn = payload.get("asn") or ""
    if isinstance(raw_asn, Mapping):
        asn = raw_asn.get("asn") or raw_asn.get("id") or raw_asn.get("name") or ""
    else:
        asn = raw_asn
    org = payload.get("org") or payload.get("organization") or ""
    return {
        "ip": str(ip),
        "country": str(country),
        "asn": str(asn),
        "org": str(org),
    }


def validate_identity_result(identity: Mapping[str, Any], *, expected_country: str = "") -> None:
    error = str(identity.get("error") or "")
    if error:
        raise RuntimeError(f"egress identity check failed: {error}")
    if not identity.get("ip"):
        raise RuntimeError("egress identity check did not return an IP address")
    observed_country = str(identity.get("country") or "")
    if expected_country and observed_country.upper() != expected_country.upper():
        raise RuntimeError(
            "egress identity country mismatch: "
            f"expected={expected_country.upper()} observed={observed_country or 'missing'}"
        )


def _listing_ids(cards: Sequence[Mapping[str, str]]) -> list[str]:
    values: list[str] = []
    for card in cards:
        match = _DETAIL_URL_RE.search(str(card.get("listing_url") or ""))
        if match:
            values.append(match.group("listing_id"))
    return values


def _card_field_counts(cards: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter[str]()
    for card in cards:
        text = str(card.get("text") or "")
        if card.get("listing_url"):
            counts["listing_url"] += 1
        if card.get("title"):
            counts["title"] += 1
        if _PRICE_RE.search(text):
            counts["price_aed"] += 1
        if _SIZE_RE.search(text):
            counts["size_sqft"] += 1
    return dict(sorted(counts.items()))


def _write_evidence(
    *,
    page: Page,
    html: str,
    observation_id: str,
    run_dir: Path,
    evidence_mode: str,
    outcome: str,
) -> dict[str, str]:
    should_write = evidence_mode == "all" or (
        evidence_mode == "challenge" and outcome in _TERMINAL_OUTCOMES
    )
    if not should_write:
        return {}
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    html_path = evidence_dir / f"{observation_id}.html"
    screenshot_path = evidence_dir / f"{observation_id}.png"
    html_path.write_text(html, encoding="utf-8")
    result = {"html": str(html_path.relative_to(run_dir))}
    try:
        page.screenshot(path=screenshot_path, full_page=True)
    except PlaywrightError:
        return result
    result["screenshot"] = str(screenshot_path.relative_to(run_dir))
    return result


def _new_session_id() -> str:
    return uuid.uuid4().hex[:16]


def _percentile(values: Sequence[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * proportion)))
    return round(ordered[index], 3)


__all__ = [
    "BayutProbeCohort",
    "BayutProbePlan",
    "build_trial_schedule",
    "classify_probe_outcome",
    "load_probe_events",
    "load_probe_plan",
    "parse_identity_payload",
    "run_probe",
    "sanitized_plan",
    "summarize_probe_events",
    "validate_identity_result",
    "validate_proxy_environment",
]
