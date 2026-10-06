import hashlib
import json
from collections.abc import Sequence
from typing import Any

import pytest

from holocron.sources.reelly_supply.bronze import load_release_to_clickhouse
from tests.fakes import FakeS3


class FakeClickHouse:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.insert_calls: list[dict[str, Any]] = []

    def command(self, sql: str) -> None:
        self.commands.append(sql)

    def insert_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
    ) -> None:
        self.insert_calls.append({"table": table, "rows": rows, "column_names": column_names})


def _jsonl_payload(rows: list[dict[str, Any]]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


def _file(path: str, key: str, payload: bytes, *, sha256: str | None = None) -> dict:
    return {
        "path": path,
        "s3_key": key,
        "sha256": sha256 or hashlib.sha256(payload).hexdigest(),
        "row_count": len(payload.splitlines()),
    }


def test_reelly_bronze_loads_projects_documents_and_availability() -> None:
    projects = _jsonl_payload(
        [
            {
                "scraped_at": "2026-05-05T00:00:00+00:00",
                "project_id": 123,
                "delta_reason": "new",
                "list_item": {"id": 123},
                "raw": {
                    "id": 123,
                    "name": "Project",
                    "Region": "Dubai",
                    "Area_name": "Business Bay",
                    "Coordinates": "25.186, 55.264",
                },
            }
        ]
    )
    documents = _jsonl_payload(
        [
            {
                "scraped_at": "2026-05-05T00:00:00+00:00",
                "project_id": 123,
                "endpoint": "projects",
                "field_path": "brochure",
                "name": "Brochure",
                "url": "https://api.reelly.io/file.pdf",
                "normalized_url": "https://api.reelly.io/file.pdf",
                "status": "download_skipped",
                "raw": {"url": "https://api.reelly.io/file.pdf"},
            }
        ]
    )
    availability = _jsonl_payload(
        [
            {
                "scraped_at": "2026-05-05T00:00:00+00:00",
                "project_id": 123,
                "endpoint": "evolutions/availability/floors",
                "candidate": 999,
                "status": "success",
                "raw": {"floors": []},
            }
        ]
    )
    clickhouse = FakeClickHouse()

    result = load_release_to_clickhouse(
        raw_manifest={
            "source": "reelly_supply",
            "run_id": "run-1",
            "files": [
                _file("reelly_supply_project_details.jsonl", "raw/projects.jsonl", projects),
                _file("reelly_supply_project_documents.jsonl", "raw/documents.jsonl", documents),
                _file(
                    "reelly_supply_matrix_availability.jsonl",
                    "raw/availability.jsonl",
                    availability,
                ),
            ],
        },
        s3=FakeS3(
            {
                "raw/projects.jsonl": projects,
                "raw/documents.jsonl": documents,
                "raw/availability.jsonl": availability,
            }
        ),
        clickhouse=clickhouse,
    )

    assert result["table_row_counts"] == {
        "reelly_projects_bronze": 1,
        "reelly_documents_bronze": 1,
        "reelly_matrix_availability_bronze": 1,
    }
    assert {call["table"] for call in clickhouse.insert_calls} == {
        "reelly_projects_bronze",
        "reelly_documents_bronze",
        "reelly_matrix_availability_bronze",
    }
    assert any(
        "ALTER TABLE `reelly_projects_bronze` DELETE WHERE `project_id` IN ('123')" in sql
        for sql in clickhouse.commands
    )
    assert any(
        "ALTER TABLE `reelly_documents_bronze` DELETE WHERE `project_id` IN ('123')" in sql
        for sql in clickhouse.commands
    )
    assert any(
        "ALTER TABLE `reelly_matrix_availability_bronze` DELETE WHERE `project_id` IN ('123')"
        in sql
        for sql in clickhouse.commands
    )
    project_call = next(
        call for call in clickhouse.insert_calls if call["table"] == "reelly_projects_bronze"
    )
    assert project_call["rows"][0][1:5] == (
        "run-1",
        "2026-05-05T00:00:00+00:00",
        "123",
        "new",
    )


def test_reelly_bronze_rejects_non_dubai_projects_and_their_children() -> None:
    projects = _jsonl_payload(
        [
            {
                "project_id": 123,
                "list_item": {"id": 123},
                "raw": {
                    "Region": "Dubai",
                    "Area_name": "Dubai Hills",
                    "Coordinates": "25.112,55.245",
                },
            },
            {
                "project_id": 456,
                "list_item": {"id": 456},
                "raw": {
                    "Region": "Dubai",
                    "Area_name": "Yas Island",
                    "Coordinates": "24.514,54.620",
                },
            },
            {
                "project_id": 789,
                "list_item": {"id": 789},
                "raw": {
                    "Region": "Bali",
                    "Area_name": "Ubud, Bali",
                    "Coordinates": "-8.55,115.24",
                },
            },
        ]
    )
    documents = _jsonl_payload(
        [
            {"project_id": project_id, "url": f"https://example.com/{project_id}.pdf"}
            for project_id in (123, 456, 789)
        ]
    )
    clickhouse = FakeClickHouse()

    result = load_release_to_clickhouse(
        raw_manifest={
            "source": "reelly_supply",
            "run_id": "dubai-only",
            "files": [
                _file("reelly_supply_project_details.jsonl", "raw/projects.jsonl", projects),
                _file("reelly_supply_project_documents.jsonl", "raw/documents.jsonl", documents),
            ],
        },
        s3=FakeS3({"raw/projects.jsonl": projects, "raw/documents.jsonl": documents}),
        clickhouse=clickhouse,
    )

    assert result["table_row_counts"]["reelly_projects_bronze"] == 1
    assert result["table_row_counts"]["reelly_documents_bronze"] == 1
    project_call = next(
        call for call in clickhouse.insert_calls if call["table"] == "reelly_projects_bronze"
    )
    document_call = next(
        call for call in clickhouse.insert_calls if call["table"] == "reelly_documents_bronze"
    )
    assert [row[3] for row in project_call["rows"]] == ["123"]
    assert [row[3] for row in document_call["rows"]] == ["123"]
    assert any("'123', '456', '789'" in sql for sql in clickhouse.commands)


def test_reelly_bronze_rejects_checksum_before_mutation() -> None:
    projects = _jsonl_payload([{"project_id": 123}])
    clickhouse = FakeClickHouse()

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_release_to_clickhouse(
            raw_manifest={
                "source": "reelly_supply",
                "run_id": "run-1",
                "files": [
                    _file(
                        "reelly_supply_project_details.jsonl",
                        "raw/projects.jsonl",
                        projects,
                        sha256="bad",
                    )
                ],
            },
            s3=FakeS3({"raw/projects.jsonl": projects}),
            clickhouse=clickhouse,
        )

    assert not clickhouse.commands
    assert not clickhouse.insert_calls
