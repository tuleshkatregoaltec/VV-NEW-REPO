from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from holocron.sources import DLD_MASHROOI_SOURCE, registry
from holocron.sources.dld_mashrooi.extract import extract_release
from holocron.sources.dld_mashrooi.source import DldMashrooiConfig


class FakeDldMashrooiApi:
    def __init__(self) -> None:
        self.search_calls: list[str] = []
        self.detail_calls: list[str] = []
        self.detail_errors: set[str] = set()

    def fetch_projects(self, *, query_string: str) -> dict[str, Any]:
        self.search_calls.append(query_string)
        return {
            "responseCode": "Success",
            "response": {
                "projects": [
                    {"number": "53", "name": {"englishName": "Mayfair Tower"}},
                    {"number": "1333", "name": {"englishName": "Fountain Views"}},
                    {"number": "3548", "name": {"englishName": "Peninsula Tower 2"}},
                ]
            },
        }

    def fetch_project_detail(self, *, project_number: str) -> dict[str, Any]:
        self.detail_calls.append(project_number)
        if project_number in self.detail_errors:
            raise RuntimeError(f"detail failed for {project_number}")
        return {
            "responseCode": "Success",
            "response": {
                "project": {
                    "title": {
                        "number": project_number,
                        "name": {"englishName": f"Project {project_number}"},
                    },
                    "location": {"googleCoordinates": {"latitude": 25.1, "longitude": 55.2}},
                    "buidlings": [
                        {
                            "number": "B1",
                            "name": {"englishName": "Building One"},
                            "location": {"latitude": 55.2, "longitude": 25.1},
                        }
                    ],
                    "lands": [],
                },
                "inspections": [],
                "media": [],
            },
        }


def test_dld_mashrooi_source_is_registered() -> None:
    assert registry.get("dld_mashrooi") is DLD_MASHROOI_SOURCE


def test_dld_mashrooi_extract_writes_search_projects_and_details(tmp_path: Path) -> None:
    api_client = FakeDldMashrooiApi()

    release = extract_release(
        tmp_path,
        config=DldMashrooiConfig(max_projects=2, max_details=1),
        now=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert release.source == "dld_mashrooi"
    assert release.metadata["response_project_count"] == 3
    assert release.metadata["selected_project_count"] == 2
    assert release.metadata["detail_count"] == 1
    assert release.metadata["detail_error_count"] == 0
    assert release.metadata["config"]["consumer_id"] == "***"
    assert files_by_name["dld_mashrooi_search.jsonl"].row_count == 1
    assert files_by_name["dld_mashrooi_projects.jsonl"].row_count == 2
    assert files_by_name["dld_mashrooi_project_details.jsonl"].row_count == 1
    assert files_by_name["dld_mashrooi_project_detail_errors.jsonl"].row_count == 0
    assert api_client.search_calls == [""]
    assert api_client.detail_calls == ["53"]

    project_rows = _read_jsonl(Path(files_by_name["dld_mashrooi_projects.jsonl"].path))
    assert [row["project_number"] for row in project_rows] == ["53", "1333"]

    detail_rows = _read_jsonl(Path(files_by_name["dld_mashrooi_project_details.jsonl"].path))
    assert detail_rows[0]["project_number"] == "53"
    assert detail_rows[0]["raw_project"]["buidlings"][0]["location"] == {
        "latitude": 55.2,
        "longitude": 25.1,
    }


def test_dld_mashrooi_extract_records_detail_errors(tmp_path: Path) -> None:
    api_client = FakeDldMashrooiApi()
    api_client.detail_errors.add("1333")

    release = extract_release(
        tmp_path,
        config=DldMashrooiConfig(max_projects=2),
        now=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        api_client=api_client,
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}
    assert files_by_name["dld_mashrooi_project_details.jsonl"].row_count == 1
    assert files_by_name["dld_mashrooi_project_detail_errors.jsonl"].row_count == 1

    error_rows = _read_jsonl(Path(files_by_name["dld_mashrooi_project_detail_errors.jsonl"].path))
    assert error_rows[0]["project_number"] == "1333"
    assert "detail failed for 1333" in error_rows[0]["error"]


def test_dld_mashrooi_extract_can_fail_on_detail_errors(tmp_path: Path) -> None:
    api_client = FakeDldMashrooiApi()
    api_client.detail_errors.add("53")

    with pytest.raises(RuntimeError, match="detail failed for 53"):
        extract_release(
            tmp_path,
            config=DldMashrooiConfig(max_projects=1, continue_on_detail_error=False),
            now=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
            api_client=api_client,
        )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
