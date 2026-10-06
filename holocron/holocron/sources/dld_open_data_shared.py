"""Shared extraction primitives for DLD open-data category sources."""

from __future__ import annotations

from contextlib import ExitStack
from importlib import import_module
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import httpx
from pydantic import Field, field_validator, model_validator

from holocron.contracts import (
    BronzeTable,
    RawFile,
    RawRelease,
    SourceSpec,
)
from holocron.platform.execution import build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.platform.raw_files import build_raw_file_from_path, string_value
from holocron.pydantic_helpers import HolocronModel, NonBlankStr

logger = logging.getLogger(__name__)

_PARAM_TAKE = "P_TAKE"
_PARAM_SKIP = "P_SKIP"
_PARAM_SORT = "P_SORT"
_NDJSON_CONTENT_TYPE = "application/x-ndjson"
_DATE_WINDOW_MODES = frozenset({"incremental", "backfill"})

DLD_OPEN_DATA_BASE_URL = "https://gateway.dubailand.gov.ae/open-data"
DLD_OPEN_DATA_REFERER = "https://dubailand.gov.ae/en/open-data/real-estate-data/"
DLD_OPEN_DATA_CONSUMER_ID = "gkb3WvEG0rY9eilwXC0P2pTz8UzvLj9F"

_HEADERS = {
    "Accept": "application/json, */*",
    "Content-Type": "application/json; charset=utf-8",
    "Origin": "https://dubailand.gov.ae",
    "Referer": DLD_OPEN_DATA_REFERER,
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "AppUser": "",
}


@dataclass(frozen=True, slots=True)
class DldOpenDataEndpointSpec:
    source_name: str
    category: str
    command: str
    row_file_name: str
    page_file_name: str
    default_sort: str
    default_filters: Mapping[str, str]
    date_field_names: tuple[str, str] | None = ("P_FROM_DATE", "P_TO_DATE")
    snapshot_omits_date_filters: bool = False
    snapshot_blank_date_filters: bool = False
    request_to_date_offset_days: int = 0
    row_date_field: str | None = None
    description: str = ""

    @property
    def supports_date_windows(self) -> bool:
        return self.date_field_names is not None


def build_open_data_endpoint(
    *,
    category: str,
    source_name: str | None = None,
    command: str | None = None,
    default_sort: str,
    default_filters: Mapping[str, str],
    date_field_names: tuple[str, str] | None = ("P_FROM_DATE", "P_TO_DATE"),
    snapshot_omits_date_filters: bool = False,
    snapshot_blank_date_filters: bool = False,
    request_to_date_offset_days: int = 0,
    row_date_field: str | None = None,
    description: str = "",
) -> DldOpenDataEndpointSpec:
    source_name = source_name or f"dld_od_{category}"
    command = command or category
    return DldOpenDataEndpointSpec(
        source_name=source_name,
        category=category,
        command=command,
        row_file_name=f"{source_name}_rows.jsonl",
        page_file_name=f"{source_name}_pages.jsonl",
        default_sort=default_sort,
        default_filters=default_filters,
        date_field_names=date_field_names,
        snapshot_omits_date_filters=snapshot_omits_date_filters,
        snapshot_blank_date_filters=snapshot_blank_date_filters,
        request_to_date_offset_days=request_to_date_offset_days,
        row_date_field=row_date_field,
        description=description,
    )


def build_open_data_source(
    *, endpoint: DldOpenDataEndpointSpec, extractor_module: str
) -> SourceSpec:
    def extract_release(*args: Any, **kwargs: Any) -> RawRelease:
        return import_module(extractor_module).extract_release(*args, **kwargs)

    package = extractor_module.rsplit(".", 1)[0]
    bronze_module_name = f"{package}.bronze"

    def bronze_loader(**kwargs: Any) -> Any:
        return import_module(bronze_module_name).load_release_to_clickhouse(**kwargs)

    return SourceSpec(
        name=endpoint.source_name,
        provider="dld",
        extractor=extract_release,
        bronze_loader=bronze_loader,
        bronze_tables=(BronzeTable(name=f"{endpoint.source_name}_bronze"),),
        checkpoint_strategy="date_window",
        cadence="daily",
        description=endpoint.description,
    )


def build_open_data_extractor(
    *,
    source: SourceSpec,
    endpoint: DldOpenDataEndpointSpec,
) -> Callable[..., RawRelease]:
    def extract_release(*args: Any, **kwargs: Any) -> RawRelease:
        return extract_open_data_release(*args, source=source, endpoint=endpoint, **kwargs)

    return extract_release


def build_open_data_package_extractor(package_name: str | None) -> Callable[..., RawRelease]:
    if not package_name:
        raise ValueError("DLD open-data extractor package name is required")
    source_module = import_module(f"{package_name}.source")
    return build_open_data_extractor(
        source=cast(SourceSpec, source_module.SOURCE),
        endpoint=cast(DldOpenDataEndpointSpec, source_module.ENDPOINT),
    )


class DldOpenDataConfig(HolocronModel):
    mode: Literal["snapshot", "incremental", "backfill"] = "incremental"
    start_date: date | None = None
    end_date: date | None = None
    checkpointed_incremental: bool = False
    incremental_overlap_days: int = Field(default=0, ge=0)
    lookback_days: int = Field(default=3, ge=0)
    slice_days: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=10000)
    max_pages: int | None = Field(default=None, ge=1)
    window_cursor: int = Field(default=0, ge=0)
    skip_cursor: int = Field(default=0, ge=0)
    checkpoint_explicit_date_window: bool | None = Field(default=None, exclude=True)
    row_date_field: str = ""
    request_to_date_offset_days: int | None = Field(default=None, ge=0)
    replace_date_column: str = ""
    sort: str = ""
    filters: dict[str, str] = Field(default_factory=dict)
    base_url: NonBlankStr = DLD_OPEN_DATA_BASE_URL
    consumer_id: NonBlankStr = DLD_OPEN_DATA_CONSUMER_ID
    request_pause_seconds: float = Field(default=0, ge=0)
    request_retry_attempts: int = Field(default=3, ge=0)
    request_retry_seconds: float = Field(default=2, ge=0)
    timeout_seconds: float = Field(default=60, ge=1)

    @field_validator("filters", mode="before")
    @classmethod
    def coerce_filters(cls, value: object) -> object:
        if value is None or value == "":
            return {}
        return value

    @model_validator(mode="after")
    def validate_config(self) -> "DldOpenDataConfig":
        if self.mode == "backfill" and (self.start_date is None or self.end_date is None):
            raise ValueError("backfill mode requires start_date and end_date")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class DldOpenDataApi(Protocol):
    def fetch(
        self,
        *,
        command: str,
        payload: Mapping[str, str],
    ) -> dict[str, Any]: ...


class DldOpenDataApiClient:
    def __init__(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        consumer_id: str,
        retry_attempts: int = 3,
        retry_seconds: float = 2,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._headers = {**_HEADERS, "consumer-id": consumer_id}
        self._retry_attempts = retry_attempts
        self._retry_seconds = retry_seconds

    def fetch(
        self,
        *,
        command: str,
        payload: Mapping[str, str],
    ) -> dict[str, Any]:
        for attempt in range(self._retry_attempts + 1):
            try:
                response = self._client.post(
                    f"{self._base_url}/{command}",
                    json=dict(payload),
                    headers=self._headers,
                )
                response.raise_for_status()
                parsed = response.json()
                if not isinstance(parsed, dict):
                    raise TypeError(f"DLD open-data {command} response must be a JSON object")
                _raise_for_open_data_errors(parsed, command=command)
                return parsed
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                if not _retryable_request_error(exc) or attempt >= self._retry_attempts:
                    raise
                if self._retry_seconds > 0:
                    time.sleep(self._retry_seconds * (attempt + 1))
        raise RuntimeError(f"DLD open-data {command} request retry loop exited unexpectedly")


def extract_open_data_release(
    output_dir: str | Path,
    *,
    source: SourceSpec,
    endpoint: DldOpenDataEndpointSpec,
    config: DldOpenDataConfig | dict,
    now: datetime | None = None,
    api_client: DldOpenDataApi | None = None,
    progress_log: Any | None = None,
) -> RawRelease:
    parsed_config = (
        config
        if isinstance(config, DldOpenDataConfig)
        else DldOpenDataConfig.model_validate(config)
    )
    _validate_config_for_endpoint(config=parsed_config, endpoint=endpoint)
    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    log = progress_log or logger

    with ExitStack() as stack:
        if api_client is None:
            client = stack.enter_context(
                httpx.Client(timeout=parsed_config.timeout_seconds, follow_redirects=True)
            )
            api_client = DldOpenDataApiClient(
                client=client,
                base_url=parsed_config.base_url,
                consumer_id=parsed_config.consumer_id,
                retry_attempts=parsed_config.request_retry_attempts,
                retry_seconds=parsed_config.request_retry_seconds,
            )
        files, metadata = _extract_files(
            output_path=output_path,
            endpoint=endpoint,
            config=parsed_config,
            api_client=api_client,
            scraped_at=current_time.isoformat(),
            today=current_time.date(),
            progress_log=log,
        )

    if not files:
        raise RuntimeError(f"DLD open-data {endpoint.category} extraction produced no raw files")

    return build_raw_release(
        source=source,
        files=files,
        run_id=run_id,
        now=current_time,
        metadata={"config": safe_config_metadata(parsed_config), **metadata},
    )


def _extract_files(
    *,
    output_path: Path,
    endpoint: DldOpenDataEndpointSpec,
    config: DldOpenDataConfig,
    api_client: DldOpenDataApi,
    scraped_at: str,
    today: date,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    row_path = output_path / endpoint.row_file_name
    page_path = output_path / endpoint.page_file_name
    page_count = 0
    row_count = 0
    completed = True
    next_window_index = config.window_cursor
    next_skip = config.skip_cursor
    started_at = time.monotonic()
    windows = _request_windows(config=config, endpoint=endpoint, today=today)
    log = progress_log

    log.info(
        "dld_open_data: starting category=%s command=%s mode=%s",
        endpoint.category,
        endpoint.command,
        config.mode,
    )
    with (
        row_path.open("w", encoding="utf-8") as row_handle,
        page_path.open("w", encoding="utf-8") as page_handle,
    ):
        for window_index, window in enumerate(windows):
            if window_index < config.window_cursor:
                continue
            skip = config.skip_cursor if window_index == config.window_cursor else 0
            next_window_index = window_index
            next_skip = skip
            while True:
                if config.max_pages is not None and page_count >= config.max_pages:
                    next_window_index = window_index
                    next_skip = skip
                    break
                payload = _request_payload(
                    config=config,
                    endpoint=endpoint,
                    window=window,
                    skip=skip,
                )
                raw_response = api_client.fetch(command=endpoint.command, payload=payload)
                api_rows = _result_rows(raw_response, command=endpoint.command)
                rows = _filter_rows_to_window(
                    rows=api_rows,
                    config=config,
                    endpoint=endpoint,
                    window=window,
                )
                total = _total_from_rows(api_rows)
                page_count += 1

                window_meta = _window_metadata(window)
                page_row = {
                    "endpoint": endpoint.command,
                    "category": endpoint.category,
                    "scraped_at": scraped_at,
                    "mode": config.mode,
                    "request": payload,
                    "date_window": window_meta,
                    "page_index": page_count,
                    "skip": skip,
                    "take": config.page_size,
                    "row_count": len(rows),
                    "api_row_count": len(api_rows),
                    "filtered_out_row_count": len(api_rows) - len(rows),
                    "total": total,
                    "raw": raw_response,
                }
                _write_json_line(page_handle, page_row)

                for row in rows:
                    row_count += 1
                    _write_json_line(
                        row_handle,
                        {
                            "endpoint": endpoint.command,
                            "category": endpoint.category,
                            "scraped_at": scraped_at,
                            "mode": config.mode,
                            "date_window": window_meta,
                            "page_index": page_count,
                            "skip": skip,
                            "take": config.page_size,
                            "row_index": row_count,
                            "raw": row,
                        },
                    )
                log.info(
                    "dld_open_data: page category=%s window=%s skip=%s rows=%s total=%s pages=%s",
                    endpoint.category,
                    window_meta,
                    skip,
                    len(rows),
                    total,
                    page_count,
                )

                if not api_rows:
                    next_window_index = window_index + 1
                    next_skip = 0
                    break
                skip += len(api_rows)
                next_window_index = window_index
                next_skip = skip
                if total is not None and skip >= total:
                    next_window_index = window_index + 1
                    next_skip = 0
                    break
                if len(api_rows) < config.page_size:
                    next_window_index = window_index + 1
                    next_skip = 0
                    break
                _pause(config)
            if config.max_pages is not None and page_count >= config.max_pages:
                break
        else:
            next_window_index = len(windows)
            next_skip = 0
    completed = next_window_index >= len(windows)

    files = (
        _build_raw_file(row_path, row_count=row_count, command=endpoint.command),
        _build_raw_file(page_path, row_count=page_count, command=endpoint.command),
    )
    log.info(
        "dld_open_data: completed category=%s pages=%s rows=%s completed=%s elapsed=%.1fs",
        endpoint.category,
        page_count,
        row_count,
        completed,
        time.monotonic() - started_at,
    )
    return files, {
        "stage": config.mode,
        "category": endpoint.category,
        "command": endpoint.command,
        "page_count": page_count,
        "row_count": row_count,
        "completed_result_set": completed,
        "supports_date_windows": endpoint.supports_date_windows,
        "uses_date_windows": _uses_date_windows(windows),
        "explicit_date_window": (
            config.checkpoint_explicit_date_window
            if config.checkpoint_explicit_date_window is not None
            else _config_has_explicit_date_window(config)
        ),
        "effective_start_date": _date_metadata(windows[0][0]) if windows else None,
        "effective_end_date": _date_metadata(windows[-1][1]) if windows else None,
        "window_count": len(windows),
        "window_cursor": config.window_cursor,
        "skip_cursor": config.skip_cursor,
        "next_window_index": next_window_index,
        "next_skip": next_skip,
    }


def _request_windows(
    *,
    config: DldOpenDataConfig,
    endpoint: DldOpenDataEndpointSpec,
    today: date,
) -> tuple[tuple[date | None, date | None], ...]:
    if not endpoint.supports_date_windows:
        return ((None, None),)

    if (
        config.mode == "snapshot"
        and (endpoint.snapshot_omits_date_filters or endpoint.snapshot_blank_date_filters)
        and config.start_date is None
        and config.end_date is None
    ):
        return ((None, None),)

    if config.mode == "snapshot":
        start_date = config.start_date or date(today.year, 1, 1)
        end_date = config.end_date or today
    elif config.mode == "backfill":
        start_date = config.start_date
        end_date = config.end_date
    else:
        end_date = config.end_date or today
        start_date = config.start_date or end_date - timedelta(days=config.lookback_days)
    if start_date is None or end_date is None:
        raise ValueError("DLD open-data date-window mode requires start_date and end_date")

    windows: list[tuple[date | None, date | None]] = []
    current = start_date
    while current <= end_date:
        window_end = min(current + timedelta(days=config.slice_days - 1), end_date)
        windows.append((current, window_end))
        current = window_end + timedelta(days=1)
    return tuple(windows)


def _request_payload(
    *,
    config: DldOpenDataConfig,
    endpoint: DldOpenDataEndpointSpec,
    window: tuple[date | None, date | None],
    skip: int,
) -> dict[str, str]:
    payload = {key: str(value) for key, value in endpoint.default_filters.items()}
    payload.update({key: str(value) for key, value in config.filters.items()})
    if endpoint.date_field_names is not None:
        from_key, to_key = endpoint.date_field_names
        start_date, end_date = window
        if start_date is not None and end_date is not None:
            request_to_date_offset_days = (
                config.request_to_date_offset_days
                if config.request_to_date_offset_days is not None
                else endpoint.request_to_date_offset_days
            )
            payload[from_key] = _dld_date(start_date)
            payload[to_key] = _dld_date(end_date + timedelta(days=request_to_date_offset_days))
        elif endpoint.snapshot_blank_date_filters:
            payload[from_key] = ""
            payload[to_key] = ""
    payload[_PARAM_TAKE] = str(config.page_size)
    payload[_PARAM_SKIP] = str(skip)
    payload[_PARAM_SORT] = config.sort.strip() or endpoint.default_sort
    return payload


def _validate_config_for_endpoint(
    *,
    config: DldOpenDataConfig,
    endpoint: DldOpenDataEndpointSpec,
) -> None:
    if not endpoint.supports_date_windows and config.mode in _DATE_WINDOW_MODES:
        raise ValueError(
            f"DLD open-data category {endpoint.category!r} only supports snapshot mode"
        )
    if endpoint.request_to_date_offset_days and not endpoint.row_date_field:
        raise ValueError(
            f"DLD open-data category {endpoint.category!r} requires row_date_field "
            "when request_to_date_offset_days is set"
        )
    if config.request_to_date_offset_days and not _effective_row_date_field(
        config=config,
        endpoint=endpoint,
    ):
        raise ValueError(
            f"DLD open-data category {endpoint.category!r} requires row_date_field "
            "when request_to_date_offset_days is configured"
        )


def _uses_date_windows(windows: Sequence[tuple[date | None, date | None]]) -> bool:
    return any(start is not None or end is not None for start, end in windows)


def _config_has_explicit_date_window(config: DldOpenDataConfig) -> bool:
    return config.start_date is not None or config.end_date is not None


def _result_rows(payload: Mapping[str, Any], *, command: str) -> list[dict[str, Any]]:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        raise ValueError(f"DLD open-data {command} payload missing response object")
    result = response.get("result")
    if result is None:
        return []
    if not isinstance(result, list):
        raise ValueError(f"DLD open-data {command} response.result must be a list")
    if not all(isinstance(row, dict) for row in result):
        raise ValueError(f"DLD open-data {command} response.result rows must be objects")
    return [dict(row) for row in result]


def _total_from_rows(rows: Sequence[Mapping[str, Any]]) -> int | None:
    if not rows:
        return None
    total = rows[0].get("TOTAL")
    if isinstance(total, int):
        return total
    if isinstance(total, float):
        return int(total)
    if isinstance(total, str) and total.strip().isdigit():
        return int(total.strip())
    return None


def _filter_rows_to_window(
    *,
    rows: Sequence[dict[str, Any]],
    config: DldOpenDataConfig,
    endpoint: DldOpenDataEndpointSpec,
    window: tuple[date | None, date | None],
) -> list[dict[str, Any]]:
    row_date_field = _effective_row_date_field(config=config, endpoint=endpoint)
    if not row_date_field:
        return [dict(row) for row in rows]
    start_date, end_date = window
    if start_date is None or end_date is None:
        return [dict(row) for row in rows]

    filtered_rows: list[dict[str, Any]] = []
    for row in rows:
        row_date = _row_date(row.get(row_date_field))
        if row_date is None or start_date <= row_date <= end_date:
            filtered_rows.append(dict(row))
    return filtered_rows


def _effective_row_date_field(
    *,
    config: DldOpenDataConfig,
    endpoint: DldOpenDataEndpointSpec,
) -> str:
    return config.row_date_field.strip() or string_value(endpoint.row_date_field)


def _row_date(value: Any) -> date | None:
    if value is None:
        return None
    parsed = str(value).strip()
    if not parsed:
        return None
    try:
        return datetime.fromisoformat(parsed.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(parsed[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _raise_for_open_data_errors(payload: Mapping[str, Any], *, command: str) -> None:
    errors = payload.get("validationErrorsList")
    if errors:
        raise RuntimeError(f"DLD open-data {command} returned validation errors: {errors}")
    response_code = payload.get("responseCode")
    if response_code not in (None, 200):
        raise RuntimeError(f"DLD open-data {command} returned responseCode={response_code}")


def _retryable_request_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _build_raw_file(path: Path, *, row_count: int, command: str) -> RawFile:
    return build_raw_file_from_path(
        path=path,
        row_count=row_count,
        content_type=_NDJSON_CONTENT_TYPE,
        metadata={"endpoint": command},
    )


def _write_json_line(handle: Any, row: Mapping[str, Any]) -> None:
    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str))
    handle.write("\n")


def _window_metadata(window: tuple[date | None, date | None]) -> dict[str, str] | None:
    start_date, end_date = window
    if start_date is None or end_date is None:
        return None
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}


def _date_metadata(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _dld_date(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def _pause(config: DldOpenDataConfig) -> None:
    if config.request_pause_seconds > 0:
        time.sleep(config.request_pause_seconds)
