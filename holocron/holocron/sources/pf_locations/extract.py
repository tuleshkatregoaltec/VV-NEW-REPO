"""Property Finder location hierarchy and filter settings extraction."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from holocron.contracts import RawFile, RawRelease
from holocron.platform.execution import build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.platform.raw_files import write_jsonl_raw_file as _write_jsonl_raw_file
from holocron.sources.pf_locations.source import PropertyFinderLocationsConfig, SOURCE

logger = logging.getLogger(__name__)

_LOCATIONS_PAGES_FILE = "pf_locations_pages.jsonl"
_LOCATIONS_FILE = "pf_locations.jsonl"
_FILTER_SETTINGS_FILE = "pf_filter_settings.jsonl"
_LOCATION_PAGE_LOG_INTERVAL = 5


class PropertyFinderLocationsApi(Protocol):
    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]: ...

    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]: ...


class PropertyFinderLocationsApiClient:
    def __init__(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        static_assets_base_url: str,
        country_code: str,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._static_assets_base_url = static_assets_base_url.rstrip("/")
        self._country_code = country_code

    def fetch_locations(self, *, page: int, limit: int, locale: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self._base_url}/api/pwa/locations",
            params={
                "locale": locale,
                "pagination.limit": limit,
                "pagination.page": page,
            },
            headers=_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Property Finder locations response must be a JSON object")
        return payload

    def fetch_filter_settings(self, *, category: int, locale: str) -> dict[str, Any]:
        response = self._client.get(
            (
                f"{self._static_assets_base_url}/filters/form-settings/v4/"
                f"{locale}/{category}.data.{self._country_code}.json"
            ),
            headers=_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Property Finder filter settings response must be a JSON object")
        return payload


def extract_release(
    output_dir: str | Path,
    *,
    config: PropertyFinderLocationsConfig | dict,
    now: datetime | None = None,
    api_client: PropertyFinderLocationsApi | None = None,
    progress_log: Any | None = None,
) -> RawRelease:
    parsed_config = (
        config
        if isinstance(config, PropertyFinderLocationsConfig)
        else PropertyFinderLocationsConfig.model_validate(config)
    )
    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    log = progress_log or logger

    with contextlib.ExitStack() as stack:
        if api_client is None:
            client = stack.enter_context(
                httpx.Client(timeout=parsed_config.timeout_seconds, follow_redirects=True)
            )
            api_client = PropertyFinderLocationsApiClient(
                client=client,
                base_url=parsed_config.base_url,
                static_assets_base_url=parsed_config.static_assets_base_url,
                country_code=parsed_config.country_code,
            )
        files = _extract_files(
            output_path=output_path,
            config=parsed_config,
            api_client=api_client,
            scraped_at=current_time.isoformat(),
            progress_log=log,
        )

    if not files:
        raise RuntimeError("Property Finder locations extraction produced no raw files")

    return build_raw_release(
        source=SOURCE,
        files=files,
        run_id=run_id,
        now=current_time,
        metadata={"config": safe_config_metadata(parsed_config)},
    )


def _extract_files(
    *,
    output_path: Path,
    config: PropertyFinderLocationsConfig,
    api_client: PropertyFinderLocationsApi,
    scraped_at: str,
    progress_log: Any,
) -> tuple[RawFile, ...]:
    location_page_rows, location_rows = _collect_locations(
        config=config,
        api_client=api_client,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )
    filter_rows = list(
        _filter_setting_rows(
            config=config,
            api_client=api_client,
            scraped_at=scraped_at,
            progress_log=progress_log,
        )
    )
    return (
        _write_jsonl_raw_file(output_path / _LOCATIONS_PAGES_FILE, location_page_rows),
        _write_jsonl_raw_file(output_path / _LOCATIONS_FILE, location_rows),
        _write_jsonl_raw_file(output_path / _FILTER_SETTINGS_FILE, filter_rows),
    )


def _collect_locations(
    *,
    config: PropertyFinderLocationsConfig,
    api_client: PropertyFinderLocationsApi,
    scraped_at: str,
    progress_log: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _log_info(
        progress_log,
        "pf_locations: collecting location hierarchy max_pages=%s page_limit=%s only_dubai=%s",
        config.max_location_pages,
        config.location_page_limit,
        config.only_dubai,
    )
    page_rows: list[dict[str, Any]] = []
    locations_by_id: dict[str, dict[str, Any]] = {}
    for page in range(1, config.max_location_pages + 1):
        payload = api_client.fetch_locations(
            page=page,
            limit=config.location_page_limit,
            locale=config.locale,
        )
        attributes = _location_attributes(payload)
        page_rows.append(
            {
                "endpoint": "pwa_locations",
                "scraped_at": scraped_at,
                "locale": config.locale,
                "page": page,
                "limit": config.location_page_limit,
                "response_count": len(attributes),
                "meta": payload.get("meta")
                if isinstance(payload.get("meta"), dict)
                else payload.get("data", {}).get("meta")
                if isinstance(payload.get("data"), dict)
                else None,
                "raw": payload,
            }
        )
        for location in attributes:
            location_id = _string_value(location.get("id"))
            if not location_id:
                continue
            if config.only_dubai and not _is_dubai_location(
                location,
                dubai_location_id=config.dubai_location_id,
            ):
                continue
            if location_id not in locations_by_id:
                locations_by_id[location_id] = _location_row(
                    location,
                    config=config,
                    scraped_at=scraped_at,
                )
        if page <= 2 or page % _LOCATION_PAGE_LOG_INTERVAL == 0:
            _log_info(
                progress_log,
                ("pf_locations: location progress page=%s response_count=%s distinct_locations=%s"),
                page,
                len(attributes),
                len(locations_by_id),
            )
        if not attributes or len(attributes) < config.location_page_limit:
            break
        if config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)
    _log_info(
        progress_log,
        "pf_locations: completed location hierarchy pages=%s distinct_locations=%s",
        len(page_rows),
        len(locations_by_id),
    )
    return page_rows, list(locations_by_id.values())


def _filter_setting_rows(
    *,
    config: PropertyFinderLocationsConfig,
    api_client: PropertyFinderLocationsApi,
    scraped_at: str,
    progress_log: Any,
) -> Iterable[dict[str, Any]]:
    _log_info(
        progress_log,
        "pf_locations: collecting filter settings categories=%s",
        list(config.categories),
    )
    for category in config.categories:
        payload = api_client.fetch_filter_settings(category=category, locale=config.locale)
        yield {
            "endpoint": "filter_settings",
            "scraped_at": scraped_at,
            "locale": config.locale,
            "country_code": config.country_code,
            "category_id": category,
            "property_type_choices": _choice_rows(payload, "filter[property_type_id]"),
            "bedroom_choices": _choice_rows(payload, "filter[number_of_bedrooms]"),
            "bathroom_choices": _choice_rows(payload, "filter[number_of_bathrooms]"),
            "sort_choices": _choice_rows(payload, "sort"),
            "raw": payload,
        }
        _log_info(
            progress_log,
            "pf_locations: fetched filter settings category=%s",
            category,
        )
        if config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)


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


def _location_row(
    location: dict[str, Any],
    *,
    config: PropertyFinderLocationsConfig,
    scraped_at: str,
) -> dict[str, Any]:
    path_ids = _path_ids(location.get("path"))
    location_id = _string_value(location.get("id"))
    parent_id = path_ids[-2] if len(path_ids) > 1 else None
    return {
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
        "url_slug": _string_value(location.get("url_slug")),
        "url_city_slug": _string_value(location.get("url_city_slug")),
        "coordinates": location.get("coordinates"),
        "center_points": location.get("center_points"),
        "children_count": location.get("children_count"),
        "top_location_id": location.get("top_location_id"),
        "published": location.get("published"),
        "is_dubai": _is_dubai_location(location, dubai_location_id=config.dubai_location_id),
        "raw": location,
    }


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


def _is_dubai_location(location: dict[str, Any], *, dubai_location_id: str) -> bool:
    location_id = _string_value(location.get("id"))
    if location_id == dubai_location_id:
        return True
    path_ids = _path_ids(location.get("path"))
    return bool(path_ids) and path_ids[0] == dubai_location_id


def _path_ids(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part for part in value.split(".") if part]


def _headers() -> dict[str, str]:
    return {
        "accept": "application/json,text/plain,*/*",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        ),
    }


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    progress_log.info(message, *args)


def _string_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
