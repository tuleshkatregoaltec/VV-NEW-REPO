"""DLD Mashrooi raw project extraction."""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from holocron.contracts import RawFile, RawRelease
from holocron.platform.execution import build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.platform.raw_files import write_jsonl_raw_file as _write_jsonl_raw_file
from holocron.sources.dld_mashrooi.source import DldMashrooiConfig, SOURCE

logger = logging.getLogger(__name__)

_SEARCH_FILE = "dld_mashrooi_search.jsonl"
_PROJECTS_FILE = "dld_mashrooi_projects.jsonl"
_DETAILS_FILE = "dld_mashrooi_project_details.jsonl"
_DETAIL_ERRORS_FILE = "dld_mashrooi_project_detail_errors.jsonl"


class DldMashrooiApi(Protocol):
    def fetch_projects(self, *, query_string: str) -> dict[str, Any] | list[Any]: ...

    def fetch_project_detail(self, *, project_number: str) -> dict[str, Any]: ...


class DldMashrooiApiClient:
    def __init__(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        consumer_id: str,
        user_agent: str,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._consumer_id = consumer_id
        self._user_agent = user_agent
        self._token = ""

    def fetch_projects(self, *, query_string: str) -> dict[str, Any] | list[Any]:
        path = "projects/searchlite"
        if query_string.strip():
            path = f"{path}?{query_string.strip().lstrip('?')}"
        return self._get_json(path)

    def fetch_project_detail(self, *, project_number: str) -> dict[str, Any]:
        payload = self._get_json(f"projects/{project_number}")
        if not isinstance(payload, dict):
            raise ValueError("DLD Mashrooi project detail response must be a JSON object")
        return payload

    def _get_json(self, path: str) -> dict[str, Any] | list[Any]:
        response = self._client.get(f"{self._base_url}/{path}", headers=self._headers())
        response.raise_for_status()
        token = response.headers.get("Token")
        if token:
            self._token = token
        payload = response.json()
        if not isinstance(payload, (dict, list)):
            raise ValueError("DLD Mashrooi response must be a JSON object or array")
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "consumer-id": self._consumer_id,
            "origin": "https://dubailand.gov.ae",
            "referer": "https://dubailand.gov.ae/",
            "user-agent": self._user_agent,
        }
        if self._token:
            headers["Token"] = self._token
        return headers


def extract_release(
    output_dir: str | Path,
    *,
    config: DldMashrooiConfig | dict,
    now: datetime | None = None,
    api_client: DldMashrooiApi | None = None,
    progress_log: Any | None = None,
) -> RawRelease:
    parsed_config = (
        config
        if isinstance(config, DldMashrooiConfig)
        else DldMashrooiConfig.model_validate(config)
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
            api_client = DldMashrooiApiClient(
                client=client,
                base_url=parsed_config.base_url,
                consumer_id=parsed_config.consumer_id,
                user_agent=parsed_config.user_agent,
            )
        files, extraction_metadata = _extract_files(
            output_path=output_path,
            config=parsed_config,
            api_client=api_client,
            scraped_at=current_time.isoformat(),
            progress_log=log,
        )

    return build_raw_release(
        source=SOURCE,
        files=files,
        run_id=run_id,
        now=current_time,
        metadata={
            "config": safe_config_metadata(parsed_config),
            **extraction_metadata,
        },
    )


def _extract_files(
    *,
    output_path: Path,
    config: DldMashrooiConfig,
    api_client: DldMashrooiApi,
    scraped_at: str,
    progress_log: Any,
) -> tuple[tuple[RawFile, ...], dict[str, Any]]:
    _log_info(progress_log, "dld_mashrooi: fetching project searchlite response")
    search_payload = api_client.fetch_projects(query_string=config.search_query)
    projects = _project_items(search_payload)
    response_project_count = len(projects)
    if config.max_projects is not None:
        projects = projects[: config.max_projects]

    search_rows = [
        {
            "endpoint": "projects/searchlite",
            "scraped_at": scraped_at,
            "query_string": config.search_query,
            "response_project_count": response_project_count,
            "selected_project_count": len(projects),
            "raw_response": search_payload,
        }
    ]
    project_rows = [
        {
            "endpoint": "projects/searchlite",
            "scraped_at": scraped_at,
            "row_index": index,
            "project_number": _project_number(project),
            "project_name_en": _project_name(project),
            "raw_project": project,
        }
        for index, project in enumerate(projects)
    ]
    detail_rows, error_rows = _collect_detail_rows(
        projects=projects,
        config=config,
        api_client=api_client,
        scraped_at=scraped_at,
        progress_log=progress_log,
    )

    files = (
        _write_jsonl_raw_file(
            output_path / _SEARCH_FILE,
            search_rows,
            metadata={"endpoint": "projects/searchlite"},
        ),
        _write_jsonl_raw_file(
            output_path / _PROJECTS_FILE,
            project_rows,
            metadata={"endpoint": "projects/searchlite"},
        ),
        _write_jsonl_raw_file(
            output_path / _DETAILS_FILE,
            detail_rows,
            metadata={"endpoint": "projects/{projectNumber}"},
        ),
        _write_jsonl_raw_file(
            output_path / _DETAIL_ERRORS_FILE,
            error_rows,
            metadata={"endpoint": "projects/{projectNumber}"},
        ),
    )
    return files, {
        "response_project_count": response_project_count,
        "selected_project_count": len(projects),
        "detail_count": len(detail_rows),
        "detail_error_count": len(error_rows),
    }


def _collect_detail_rows(
    *,
    projects: list[dict[str, Any]],
    config: DldMashrooiConfig,
    api_client: DldMashrooiApi,
    scraped_at: str,
    progress_log: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detail_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    if not config.fetch_details:
        return detail_rows, error_rows

    detail_projects = projects
    if config.max_details is not None:
        detail_projects = detail_projects[: config.max_details]
    _log_info(progress_log, "dld_mashrooi: fetching details for %s projects", len(detail_projects))
    for index, project in enumerate(detail_projects):
        project_number = _project_number(project)
        if not project_number:
            error_rows.append(
                {
                    "endpoint": "projects/{projectNumber}",
                    "scraped_at": scraped_at,
                    "row_index": index,
                    "project_number": "",
                    "project_name_en": _project_name(project),
                    "error": "missing project number",
                    "raw_project": project,
                }
            )
            continue
        try:
            payload = api_client.fetch_project_detail(project_number=project_number)
        except Exception as exc:
            if not config.continue_on_detail_error:
                raise
            error_rows.append(
                {
                    "endpoint": f"projects/{project_number}",
                    "scraped_at": scraped_at,
                    "row_index": index,
                    "project_number": project_number,
                    "project_name_en": _project_name(project),
                    "error": repr(exc),
                    "raw_project": project,
                }
            )
            continue
        detail_project = _detail_project(payload)
        detail_rows.append(
            {
                "endpoint": f"projects/{project_number}",
                "scraped_at": scraped_at,
                "row_index": index,
                "project_number": project_number,
                "project_name_en": _project_name(detail_project) or _project_name(project),
                "raw_project": detail_project,
                "raw_response": payload,
            }
        )
        if (index + 1) % 250 == 0:
            _log_info(
                progress_log,
                "dld_mashrooi: detail progress fetched=%s errors=%s",
                len(detail_rows),
                len(error_rows),
            )
        if config.request_pause_seconds:
            time.sleep(config.request_pause_seconds)
    return detail_rows, error_rows


def _project_items(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    response = _response_payload(payload)
    if isinstance(response, list):
        values = response
    elif isinstance(response, dict):
        values = []
        for key in ("projects", "items", "data", "results"):
            item = response.get(key)
            if isinstance(item, list):
                values = item
                break
    else:
        values = []
    if not values:
        return []
    rows: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _detail_project(payload: dict[str, Any]) -> dict[str, Any]:
    response = _response_payload(payload)
    if isinstance(response, dict) and isinstance(response.get("project"), dict):
        return response["project"]
    if isinstance(response, dict):
        return response
    return {}


def _response_payload(payload: dict[str, Any] | list[Any]) -> Any:
    if isinstance(payload, dict) and "response" in payload:
        return payload["response"]
    return payload


def _project_number(project: dict[str, Any]) -> str:
    for key in ("number", "projectNumber", "project_number", "projectNo", "id"):
        value = project.get(key)
        if value not in (None, ""):
            return str(value).strip()
    title = project.get("title")
    if isinstance(title, dict):
        value = title.get("number")
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _project_name(project: dict[str, Any]) -> str:
    for key in ("name", "title"):
        value = project.get(key)
        name = _english_name(value)
        if name:
            return name
    return ""


def _english_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    nested_name = value.get("name")
    if isinstance(nested_name, dict):
        name = _english_name(nested_name)
        if name:
            return name
    for key in ("englishName", "english", "en"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def _log_info(progress_log: Any, message: str, *args: Any) -> None:
    if hasattr(progress_log, "info"):
        progress_log.info(message, *args)
