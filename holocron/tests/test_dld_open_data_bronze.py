import hashlib
import importlib
import json
from collections.abc import Sequence
from datetime import date
from typing import Any

import pytest

from tests.fakes import FakeS3

_CATEGORIES = (
    "transactions rents projects valuations lands buildings units brokers developers".split()
)
SOURCE_MODULES = tuple(
    (f"dld_od_{c}", f"dld_od_{c}_rows.jsonl", f"dld_od_{c}_bronze") for c in _CATEGORIES
)


class FakeClickHouse:
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
        self.insert_calls.append({"table": table, "rows": rows, "column_names": column_names})

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
                "column_names": column_names,
                "staging_suffix": staging_suffix,
            }
        )
        return len(rows)


def _jsonl_payload(rows: list[dict[str, Any]]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


def _release(source: str, row_file: str, payload: bytes, *, sha256: str | None = None) -> dict:
    return {
        "source": source,
        "run_id": "run-1",
        "files": [
            {
                "path": row_file,
                "s3_key": f"raw/{source}/{row_file}",
                "sha256": sha256 or hashlib.sha256(payload).hexdigest(),
                "row_count": 1,
            }
        ],
    }


def _release_with_pages(
    source: str,
    row_file: str,
    page_file: str,
    rows_payload: bytes,
    pages_payload: bytes,
    *,
    metadata: dict[str, Any],
) -> dict:
    return {
        "source": source,
        "run_id": "run-1",
        "metadata": metadata,
        "files": [
            {
                "path": row_file,
                "s3_key": f"raw/{source}/{row_file}",
                "sha256": hashlib.sha256(rows_payload).hexdigest(),
                "row_count": len(rows_payload.splitlines()),
            },
            {
                "path": page_file,
                "s3_key": f"raw/{source}/{page_file}",
                "sha256": hashlib.sha256(pages_payload).hexdigest(),
                "row_count": len(pages_payload.splitlines()),
            },
        ],
    }


@pytest.mark.parametrize(("source", "row_file", "table"), SOURCE_MODULES)
def test_dld_open_data_bronze_loaders_map_rows(source: str, row_file: str, table: str) -> None:
    payload = _jsonl_payload(
        [
            {
                "endpoint": source.removeprefix("dld_od_"),
                "category": source.removeprefix("dld_od_"),
                "scraped_at": "2026-05-06T12:00:00+00:00",
                "mode": "incremental",
                "date_window": {"start_date": "2026-05-05", "end_date": "2026-05-06"},
                "page_index": 1,
                "row_index": 3,
                "raw": {"TOTAL": 1, "ID": "row-1"},
            }
        ]
    )
    clickhouse = FakeClickHouse()
    module = importlib.import_module(f"holocron.sources.{source}.bronze")
    result = module.load_release_to_clickhouse(
        raw_manifest=_release(source, row_file, payload),
        s3=FakeS3({f"raw/{source}/{row_file}": payload}),
        clickhouse=clickhouse,
    )

    assert result["table_row_counts"] == {table: 1}
    assert any(f"CREATE TABLE IF NOT EXISTS {table}" in sql for sql in clickhouse.commands)
    delete_sql = next(sql for sql in clickhouse.commands if f"ALTER TABLE `{table}` DELETE" in sql)
    assert "source_system = 'dld_open_data'" in delete_sql
    replace_date_columns = {
        "dld_od_transactions": "instance_date",
        "dld_od_rents": "start_date",
    }
    if source in replace_date_columns:
        date_column = replace_date_columns[source]
        assert f"toDate(`{date_column}`) >= toDate('2026-05-05')" in delete_sql
        assert f"toDate(`{date_column}`) <= toDate('2026-05-06')" in delete_sql
    else:
        assert "date_window_start = toDate('2026-05-05')" in delete_sql
        assert "date_window_end = toDate('2026-05-06')" in delete_sql
    assert "run_id = 'run-1'" not in delete_sql
    assert clickhouse.insert_calls[0]["table"] == table
    # All sources share the same envelope layout at positions 1-7.
    row = clickhouse.insert_calls[0]["rows"][0]
    assert row[1:8] == (
        "run-1",
        "2026-05-06T12:00:00+00:00",
        "incremental",
        date(2026, 5, 5),
        date(2026, 5, 6),
        1,
        3,
    )


def test_dld_rents_bronze_can_replace_by_manifest_configured_registration_date() -> None:
    source = "dld_od_rents"
    row_file = "dld_od_rents_rows.jsonl"
    table = "dld_od_rents_bronze"
    payload = _jsonl_payload(
        [
            {
                "endpoint": "rents",
                "category": "rents",
                "scraped_at": "2026-05-06T12:00:00+00:00",
                "mode": "incremental",
                "date_window": {"start_date": "2026-05-05", "end_date": "2026-05-06"},
                "page_index": 1,
                "row_index": 3,
                "raw": {"TOTAL": 1, "ID": "row-1"},
            }
        ]
    )
    release = _release(source, row_file, payload)
    release["metadata"] = {"config": {"replace_date_column": "registration_date"}}
    clickhouse = FakeClickHouse()

    result = importlib.import_module(
        "holocron.sources.dld_od_rents.bronze"
    ).load_release_to_clickhouse(
        raw_manifest=release,
        s3=FakeS3({f"raw/{source}/{row_file}": payload}),
        clickhouse=clickhouse,
    )

    assert result["table_row_counts"] == {table: 1}
    delete_sql = next(sql for sql in clickhouse.commands if f"ALTER TABLE `{table}` DELETE" in sql)
    assert "toDate(`registration_date`) >= toDate('2026-05-05')" in delete_sql
    assert "toDate(`registration_date`) <= toDate('2026-05-06')" in delete_sql
    assert "toDate(`start_date`)" not in delete_sql


def test_dld_open_data_units_bronze_maps_unit_columns() -> None:
    source = "dld_od_units"
    row_file = "dld_od_units_rows.jsonl"
    payload = _jsonl_payload(
        [
            {
                "endpoint": "units",
                "category": "units",
                "scraped_at": "2026-05-06T12:00:00+00:00",
                "mode": "incremental",
                "date_window": {"start_date": "2026-05-05", "end_date": "2026-05-06"},
                "page_index": 1,
                "row_index": 3,
                "raw": {
                    "PROPERTY_ID": 111,
                    "PARENT_PROPERTY_ID": 222,
                    "GRANDPARENT_PROPERTY_ID": 333,
                    "AREA_ID": 10,
                    "AREA_EN": "Downtown Dubai",
                    "AREA_AR": "وسط مدينة دبي",
                    "LAND_NUMBER": "L-1",
                    "LAND_SUB_NUMBER": "2",
                    "BUILDING_NUMBER": "B-1",
                    "UNIT_NUMBER": "101",
                    "UNIT_BALCONY_AREA": "4.5",
                    "UNIT_PARKING_NUMBER": "P1",
                    "PARKING_ALLOCATION_TYPE_EN": "Allocated",
                    "COMMON_AREA": "12.5",
                    "ACTUAL_COMMON_AREA": "11.5",
                    "FLOOR": "10",
                    "ROOMS_EN": "2 B/R",
                    "ACTUAL_AREA": "98.7",
                    "PROPERTY_TYPE_ID": 1,
                    "PROPERTY_TYPE_EN": "Unit",
                    "PROPERTY_SUB_TYPE_ID": 4,
                    "PROP_SUB_TYPE_EN": "Flat",
                    "CREATION_DATE": "2026-05-01T00:00:00",
                    "MUNICIPALITY_NUMBER": "M-1",
                    "PARCEL_ID": "PARCEL-1",
                    "IS_FREE_HOLD": "Y",
                    "IS_LEASE_HOLD": "N",
                    "IS_REGISTERED": "1",
                    "MASTER_PROJECT_ID": 44,
                    "MASTER_PROJECT_EN": "Master",
                    "PROJECT_ID": 55,
                    "PROJECT_EN": "Project",
                    "LAND_TYPE_ID": 6,
                    "LAND_TYPE_EN": "Commercial",
                },
            }
        ]
    )
    clickhouse = FakeClickHouse()
    module = importlib.import_module("holocron.sources.dld_od_units.bronze")

    module.load_release_to_clickhouse(
        raw_manifest=_release(source, row_file, payload),
        s3=FakeS3({f"raw/{source}/{row_file}": payload}),
        clickhouse=clickhouse,
    )

    insert = clickhouse.insert_calls[0]
    unit = dict(zip(insert["column_names"], insert["rows"][0]))
    assert unit["raw_json"]
    assert unit["source_system"] == "dld_open_data"
    assert unit["source_file"] == row_file
    assert unit["source_row_index"] == 3
    assert unit["raw_manifest_s3_key"] == "raw/source=dld_od_units/manifests/run-1.json"
    assert unit["property_id"] == 111
    assert unit["parent_property_id"] == 222
    assert unit["grandparent_property_id"] == 333
    assert unit["area_en"] == "Downtown Dubai"
    assert unit["building_number"] == "B-1"
    assert unit["unit_number"] == "101"
    assert unit["unit_balcony_area"] == 4.5
    assert unit["actual_area"] == 98.7
    assert unit["property_type_en"] == "Unit"
    assert unit["prop_sub_type_en"] == "Flat"
    assert unit["parcel_id"] == "PARCEL-1"
    assert unit["is_free_hold"] == 1
    assert unit["is_lease_hold"] == 0
    assert unit["is_registered"] == 1
    assert unit["project_id"] == 55
    assert unit["project_en"] == "Project"


def test_dld_open_data_bronze_clears_zero_row_windows_from_page_metadata() -> None:
    source = "dld_od_transactions"
    row_file = "dld_od_transactions_rows.jsonl"
    page_file = "dld_od_transactions_pages.jsonl"
    table = "dld_od_transactions_bronze"
    rows_payload = b""
    pages_payload = _jsonl_payload(
        [
            {
                "endpoint": "transactions",
                "category": "transactions",
                "date_window": {"start_date": "2026-05-05", "end_date": "2026-05-05"},
                "row_count": 0,
            }
        ]
    )
    clickhouse = FakeClickHouse()
    module = importlib.import_module(f"holocron.sources.{source}.bronze")

    result = module.load_release_to_clickhouse(
        raw_manifest={
            "source": source,
            "run_id": "run-1",
            "metadata": {"completed_result_set": True},
            "files": [
                {
                    "path": row_file,
                    "s3_key": f"raw/{source}/{row_file}",
                    "sha256": hashlib.sha256(rows_payload).hexdigest(),
                    "row_count": 0,
                },
                {
                    "path": page_file,
                    "s3_key": f"raw/{source}/{page_file}",
                    "sha256": hashlib.sha256(pages_payload).hexdigest(),
                    "row_count": 1,
                },
            ],
        },
        s3=FakeS3(
            {
                f"raw/{source}/{row_file}": rows_payload,
                f"raw/{source}/{page_file}": pages_payload,
            }
        ),
        clickhouse=clickhouse,
    )

    assert result["table_row_counts"] == {table: 0}
    delete_sql = next(sql for sql in clickhouse.commands if f"ALTER TABLE `{table}` DELETE" in sql)
    assert "source_system = 'dld_open_data'" in delete_sql
    assert "toDate(`instance_date`) >= toDate('2026-05-05')" in delete_sql
    assert not clickhouse.insert_calls


def test_dld_open_data_bronze_rejects_incomplete_chunks_before_mutation() -> None:
    source = "dld_od_transactions"
    row_file = "dld_od_transactions_rows.jsonl"
    payload = _jsonl_payload(
        [{"date_window": {"start_date": "2026-05-05", "end_date": "2026-05-05"}}]
    )
    clickhouse = FakeClickHouse()
    module = importlib.import_module(f"holocron.sources.{source}.bronze")

    with pytest.raises(ValueError, match="incomplete raw result set"):
        module.load_release_to_clickhouse(
            raw_manifest={
                **_release(source, row_file, payload),
                "metadata": {"completed_result_set": False},
            },
            s3=FakeS3({f"raw/{source}/{row_file}": payload}),
            clickhouse=clickhouse,
        )

    assert not clickhouse.commands
    assert not clickhouse.insert_calls


def test_dld_open_data_bronze_loads_first_manual_snapshot_chunk_as_replacement() -> None:
    source = "dld_od_units"
    row_file = "dld_od_units_rows.jsonl"
    page_file = "dld_od_units_pages.jsonl"
    rows_payload = _jsonl_payload(
        [
            {
                "endpoint": "units",
                "category": "units",
                "mode": "snapshot",
                "date_window": None,
                "page_index": 1,
                "row_index": 1,
                "raw": {"ID": "row-1"},
            }
        ]
    )
    pages_payload = _jsonl_payload(
        [{"endpoint": "units", "category": "units", "date_window": None, "skip": 0}]
    )
    clickhouse = FakeClickHouse()
    module = importlib.import_module(f"holocron.sources.{source}.bronze")

    module.load_release_to_clickhouse(
        raw_manifest=_release_with_pages(
            source,
            row_file,
            page_file,
            rows_payload,
            pages_payload,
            metadata={"stage": "snapshot", "completed_result_set": False},
        ),
        s3=FakeS3(
            {
                f"raw/{source}/{row_file}": rows_payload,
                f"raw/{source}/{page_file}": pages_payload,
            }
        ),
        clickhouse=clickhouse,
    )

    delete_sql = next(
        sql for sql in clickhouse.commands if "ALTER TABLE `dld_od_units_bronze` DELETE" in sql
    )
    assert "source_system = 'dld_open_data'" in delete_sql
    assert "1 = 1" in delete_sql
    assert clickhouse.insert_calls[0]["table"] == "dld_od_units_bronze"


def test_dld_open_data_bronze_loads_later_manual_snapshot_chunk_by_row_key() -> None:
    source = "dld_od_units"
    row_file = "dld_od_units_rows.jsonl"
    page_file = "dld_od_units_pages.jsonl"
    rows_payload = _jsonl_payload(
        [
            {
                "endpoint": "units",
                "category": "units",
                "mode": "snapshot",
                "date_window": None,
                "page_index": 1,
                "row_index": 1,
                "raw": {"ID": "row-1"},
            }
        ]
    )
    pages_payload = _jsonl_payload(
        [{"endpoint": "units", "category": "units", "date_window": None, "skip": 10000}]
    )
    clickhouse = FakeClickHouse()
    module = importlib.import_module(f"holocron.sources.{source}.bronze")

    module.load_release_to_clickhouse(
        raw_manifest=_release_with_pages(
            source,
            row_file,
            page_file,
            rows_payload,
            pages_payload,
            metadata={"stage": "snapshot", "completed_result_set": True},
        ),
        s3=FakeS3(
            {
                f"raw/{source}/{row_file}": rows_payload,
                f"raw/{source}/{page_file}": pages_payload,
            }
        ),
        clickhouse=clickhouse,
    )

    delete_sql = next(
        sql for sql in clickhouse.commands if "ALTER TABLE `dld_od_units_bronze` DELETE" in sql
    )
    assert "source_system = 'dld_open_data'" in delete_sql
    assert "`row_key` IN" in delete_sql
    assert "1 = 1" not in delete_sql
    assert clickhouse.insert_calls[0]["table"] == "dld_od_units_bronze"


@pytest.mark.parametrize(("source", "row_file", "_table"), SOURCE_MODULES)
def test_dld_open_data_bronze_rejects_checksum_before_mutation(
    source: str,
    row_file: str,
    _table: str,
) -> None:
    payload = _jsonl_payload([{"raw": {"ID": "row-1"}}])
    clickhouse = FakeClickHouse()
    module = importlib.import_module(f"holocron.sources.{source}.bronze")

    with pytest.raises(ValueError, match="checksum mismatch"):
        module.load_release_to_clickhouse(
            raw_manifest=_release(source, row_file, payload, sha256="bad"),
            s3=FakeS3({f"raw/{source}/{row_file}": payload}),
            clickhouse=clickhouse,
        )

    assert not clickhouse.commands
    assert not clickhouse.insert_calls
