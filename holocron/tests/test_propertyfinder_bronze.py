import hashlib
import json
from collections.abc import Sequence
from typing import Any

import pytest

from holocron.sources.pf_listings.bronze import load_release_to_clickhouse as load_listings
from holocron.sources.pf_locations.bronze import load_release_to_clickhouse as load_locations
from tests.fakes import FakeS3


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


def _file(path: str, key: str, payload: bytes, *, row_count: int | None = None) -> dict:
    return {
        "path": path,
        "s3_key": key,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "row_count": len(payload.splitlines()) if row_count is None else row_count,
    }


def test_pf_locations_bronze_replaces_location_rows() -> None:
    payload = _jsonl_payload(
        [
            {
                "scraped_at": "2026-05-05T00:00:00+00:00",
                "locale": "en",
                "location_id": "42",
                "parent_location_id": "1",
                "path": "1.42",
                "path_ids": ["1", "42"],
                "path_name": "Dubai, Marina",
                "name": "Dubai Marina",
                "level": 1,
                "location_type": "community",
                "coordinates": {"lat": 25.08, "lon": 55.14},
                "children_count": 7,
                "published": True,
                "is_dubai": True,
                "raw": {"id": "42"},
            }
        ]
    )
    clickhouse = FakeClickHouse()

    result = load_locations(
        raw_manifest={
            "source": "pf_locations",
            "run_id": "run-1",
            "files": [_file("pf_locations.jsonl", "raw/pf_locations.jsonl", payload)],
        },
        s3=FakeS3({"raw/pf_locations.jsonl": payload}),
        clickhouse=clickhouse,
    )

    assert result["table_row_counts"] == {"pf_locations_bronze": 1}
    assert any(
        "CREATE TABLE IF NOT EXISTS pf_locations_bronze" in sql for sql in clickhouse.commands
    )
    assert clickhouse.replace_calls[0]["table"] == "pf_locations_bronze"
    assert clickhouse.replace_calls[0]["rows"][0][0:5] == (
        "42",
        "1",
        "2026-05-05T00:00:00+00:00",
        "en",
        "1.42",
    )


def test_pf_locations_bronze_rejects_row_count_before_mutation() -> None:
    payload = _jsonl_payload([{"location_id": "42"}])
    clickhouse = FakeClickHouse()

    with pytest.raises(ValueError, match="row_count mismatch"):
        load_locations(
            raw_manifest={
                "source": "pf_locations",
                "run_id": "run-1",
                "files": [
                    _file("pf_locations.jsonl", "raw/pf_locations.jsonl", payload, row_count=2)
                ],
            },
            s3=FakeS3({"raw/pf_locations.jsonl": payload}),
            clickhouse=clickhouse,
        )

    assert not clickhouse.commands
    assert not clickhouse.replace_calls


def test_pf_listings_bronze_loads_property_and_detail_rows() -> None:
    property_payload = _jsonl_payload(
        [
            {
                "scraped_at": "2026-05-05T00:00:00+00:00",
                "query_signature": "q1",
                "category_id": 1,
                "location_id": "1",
                "property_type_id": 1,
                "bedroom": 2,
                "page": 1,
                "wrapper_index": 1,
                "listing_id": "listing-1",
                "property_key": "listing_id:listing-1",
                "title": "Test apartment",
                "latitude": 25.1,
                "longitude": 55.2,
                "is_available": True,
                "listing_location_ids": ["1", "42"],
                "listing_location_names": ["Dubai", "Dubai Marina"],
                "raw_property": {"id": "listing-1"},
                "raw_wrapper": {"property": {"id": "listing-1"}},
            }
        ]
    )
    detail_payload = _jsonl_payload(
        [
            {
                "scraped_at": "2026-05-05T00:01:00+00:00",
                "listing_id": "listing-1",
                "property_key": "listing_id:listing-1",
                "details_path": "/en/plp/test.html",
                "status": "ok",
                "detail_property": {"id": "listing-1", "amenities": []},
                "raw": {"property": {"id": "listing-1"}},
            }
        ]
    )
    clickhouse = FakeClickHouse()

    result = load_listings(
        raw_manifest={
            "source": "pf_listings",
            "run_id": "run-1",
            "files": [
                _file(
                    "pf_listing_properties.jsonl",
                    "raw/pf_listing_properties.jsonl",
                    property_payload,
                ),
                _file("pf_listing_details.jsonl", "raw/pf_listing_details.jsonl", detail_payload),
            ],
        },
        s3=FakeS3(
            {
                "raw/pf_listing_properties.jsonl": property_payload,
                "raw/pf_listing_details.jsonl": detail_payload,
            }
        ),
        clickhouse=clickhouse,
    )

    assert result["table_row_counts"] == {
        "pf_listings_bronze": 1,
        "pf_listing_details_bronze": 1,
    }
    assert {call["table"] for call in clickhouse.insert_calls} == {
        "pf_listings_bronze",
        "pf_listing_details_bronze",
    }
    assert any(
        "ALTER TABLE `pf_listings_bronze` DELETE WHERE `property_key` "
        "IN ('listing_id:listing-1')" in sql
        for sql in clickhouse.commands
    )
    assert any(
        "ALTER TABLE `pf_listing_details_bronze` DELETE WHERE `property_key` "
        "IN ('listing_id:listing-1')" in sql
        for sql in clickhouse.commands
    )
    listing_call = next(
        call for call in clickhouse.insert_calls if call["table"] == "pf_listings_bronze"
    )
    assert listing_call["rows"][0][0:4] == (
        "listing_id:listing-1",
        "run-1",
        "2026-05-05T00:00:00+00:00",
        "q1",
    )


def test_pf_listings_bronze_rejects_detail_row_count_before_mutation() -> None:
    property_payload = _jsonl_payload([{"property_key": "listing-1"}])
    detail_payload = _jsonl_payload([{"property_key": "listing-1"}])
    clickhouse = FakeClickHouse()

    with pytest.raises(ValueError, match="row_count mismatch"):
        load_listings(
            raw_manifest={
                "source": "pf_listings",
                "run_id": "run-1",
                "files": [
                    _file("pf_listing_properties.jsonl", "raw/properties.jsonl", property_payload),
                    _file(
                        "pf_listing_details.jsonl", "raw/details.jsonl", detail_payload, row_count=2
                    ),
                ],
            },
            s3=FakeS3(
                {"raw/properties.jsonl": property_payload, "raw/details.jsonl": detail_payload}
            ),
            clickhouse=clickhouse,
        )

    assert not clickhouse.commands
    assert not clickhouse.insert_calls
