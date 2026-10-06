import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from holocron.contracts import ClickHouseWriter, RawFileStore
from holocron.sources.dxbi.bronze import load_release_to_clickhouse


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def download_file(self, *, key: str, path: str | Path) -> None:
        payload = self._objects[key]
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)


class _FakeClickHouse:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.insert_calls: list[dict[str, Any]] = []
        self.replace_calls: list[dict[str, Any]] = []

    def command(self, sql: str) -> None:
        self.commands.append(sql)

    def insert_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
    ) -> None:
        self.insert_calls.append(
            {
                "table": table,
                "rows": rows,
                "column_names": tuple(column_names),
            }
        )

    def replace_table_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
        staging_suffix: str = "replace_rows",
    ) -> int:
        self.replace_calls.append(
            {
                "table": table,
                "rows": rows,
                "column_names": tuple(column_names),
                "staging_suffix": staging_suffix,
            }
        )
        return len(rows)


def _s3(fake: _FakeS3) -> RawFileStore:
    return fake


def _clickhouse(fake: _FakeClickHouse) -> ClickHouseWriter:
    return fake


def _jsonl_payload(rows: list[dict[str, Any]]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode("utf-8")


def test_load_release_to_clickhouse_loads_rows_and_clears_incremental_window() -> None:
    raw_rows = [
        {
            "table": "sales",
            "cells": ["A", "B"],
            "_run_id": "raw-run-1",
            "_scraped_at": "2026-04-30T12:00:00+00:00",
            "_slice_start_date": "2026-04-29",
            "_slice_end_date": "2026-04-29",
            "_source_url": "https://dxbinteract.com/",
            "_page_number": 1,
            "_row_number": 1,
        },
        {
            "table": "rentals",
            "cells": ["C", "D"],
            "_run_id": "raw-run-1",
            "_scraped_at": "2026-04-30T12:00:00+00:00",
            "_slice_start_date": "2026-04-30",
            "_slice_end_date": "2026-04-30",
            "_source_url": "https://dxbinteract.com/",
            "_page_number": 1,
            "_row_number": 2,
        },
    ]
    s3 = _FakeS3({"s3://raw/slice.jsonl": _jsonl_payload(raw_rows)})
    clickhouse = _FakeClickHouse()

    result = load_release_to_clickhouse(
        raw_manifest={
            "source": "dxbi_transactions",
            "run_id": "release-run-1",
            "files": [
                {"path": "slice_2026-04-29_2026-04-30.jsonl", "s3_key": "s3://raw/slice.jsonl"}
            ],
        },
        s3=_s3(s3),
        clickhouse=_clickhouse(clickhouse),
    )

    assert result["table_row_counts"] == {"dxbi_transactions_bronze": 2}
    assert result["table_count"] == 1
    assert result["total_rows"] == 2
    assert any(
        "CREATE TABLE IF NOT EXISTS dxbi_transactions_bronze" in sql for sql in clickhouse.commands
    )
    delete_sql = next(
        sql
        for sql in clickhouse.commands
        if "ALTER TABLE `dxbi_transactions_bronze` DELETE WHERE" in sql
    )
    assert "slice_start_date = toDate('2026-04-29')" in delete_sql
    assert "slice_end_date = toDate('2026-04-29')" in delete_sql
    assert "slice_start_date = toDate('2026-04-30')" in delete_sql
    assert "slice_end_date = toDate('2026-04-30')" in delete_sql
    assert len(clickhouse.insert_calls) == 1
    insert_call = clickhouse.insert_calls[0]
    assert insert_call["table"] == "dxbi_transactions_bronze"
    assert len(insert_call["rows"]) == 2


def test_load_release_to_clickhouse_loads_comprehensive_heatmap_rows() -> None:
    raw_rows = [
        {
            "endpoint": "heatmap_chessboard",
            "location_id": "1",
            "payload": {"Chessboard": {"Floors": []}},
            "status": 200,
            "request_url": "https://api.example.test/chessboard/1",
            "content_type": "application/json",
            "_run_id": "raw-run-1",
            "_scraped_at": "2026-05-04T16:00:00+00:00",
        }
    ]
    s3 = _FakeS3({"s3://raw/heatmap.jsonl": _jsonl_payload(raw_rows)})
    clickhouse = _FakeClickHouse()

    result = load_release_to_clickhouse(
        raw_manifest={
            "source": "dxbi_transactions",
            "run_id": "release-run-1",
            "files": [
                {"path": "dxbi_heatmap_chessboards.jsonl", "s3_key": "s3://raw/heatmap.jsonl"}
            ],
        },
        s3=_s3(s3),
        clickhouse=_clickhouse(clickhouse),
    )

    assert result["table_row_counts"] == {"dxbi_heatmap_chessboards_bronze": 1}
    assert result["total_rows"] == 1
    assert not clickhouse.insert_calls
    assert clickhouse.replace_calls[0]["table"] == "dxbi_heatmap_chessboards_bronze"
    assert clickhouse.replace_calls[0]["rows"][0][2:7] == (
        "2026-05-04T16:00:00+00:00",
        "1",
        "heatmap_chessboard",
        200,
        "https://api.example.test/chessboard/1",
    )


def test_load_release_to_clickhouse_rejects_checksum_mismatch_before_mutation() -> None:
    payload = _jsonl_payload([])
    clickhouse = _FakeClickHouse()

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_release_to_clickhouse(
            raw_manifest={
                "source": "dxbi_transactions",
                "run_id": "release-run-1",
                "files": [
                    {
                        "path": "slice_2026-04-29_2026-04-29.jsonl",
                        "s3_key": "s3://raw/slice.jsonl",
                        "sha256": "bad",
                        "row_count": 0,
                    }
                ],
            },
            s3=_s3(_FakeS3({"s3://raw/slice.jsonl": payload})),
            clickhouse=_clickhouse(clickhouse),
        )

    assert not clickhouse.commands
    assert not clickhouse.insert_calls
    assert not clickhouse.replace_calls


def test_load_release_to_clickhouse_rejects_row_count_mismatch_before_mutation() -> None:
    payload = _jsonl_payload(
        [
            {
                "table": "sales",
                "cells": ["A", "B"],
                "_slice_start_date": "2026-04-29",
                "_slice_end_date": "2026-04-29",
            }
        ]
    )
    clickhouse = _FakeClickHouse()

    with pytest.raises(ValueError, match="row_count mismatch"):
        load_release_to_clickhouse(
            raw_manifest={
                "source": "dxbi_transactions",
                "run_id": "release-run-1",
                "files": [
                    {
                        "path": "slice_2026-04-29_2026-04-29.jsonl",
                        "s3_key": "s3://raw/slice.jsonl",
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "row_count": 2,
                    }
                ],
            },
            s3=_s3(_FakeS3({"s3://raw/slice.jsonl": payload})),
            clickhouse=_clickhouse(clickhouse),
        )

    assert not clickhouse.commands
    assert not clickhouse.insert_calls
    assert not clickhouse.replace_calls


def test_load_release_to_clickhouse_rejects_non_dxbi_release() -> None:
    with pytest.raises(ValueError, match="Expected raw_manifest.source=dxbi_transactions"):
        load_release_to_clickhouse(
            raw_manifest={"source": "other_source", "run_id": "run-1", "files": []},
            s3=_s3(_FakeS3({})),
            clickhouse=_clickhouse(_FakeClickHouse()),
        )
