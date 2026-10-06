#!/usr/bin/env python3
"""Atomically replace PF bronze listings with one current raw-scrape snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from holocron.platform.clickhouse import ClickHouseClient
from holocron.platform.object_storage import ObjectStorageClient
from holocron.platform.settings import settings
from holocron.sources.pf_listings.bronze import _LISTING_COLUMNS, _listing_row_tuple

PREFIX = "raw/source=pf_listings/manifests/"
TABLE = "pf_listings_bronze"


def iter_json_objects(text: str):
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = decoder.raw_decode(text, index)
        if isinstance(value, dict):
            yield value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True, help="Inclusive YYYY-MM-DD scraped_at")
    parser.add_argument("--expected-count", type=int, required=True)
    args = parser.parse_args()
    storage, clickhouse = ObjectStorageClient(settings), ClickHouseClient(settings)
    staging = f"{TABLE}_staging_{args.start_date.replace('-', '')}"
    clickhouse.command(f"DROP TABLE IF EXISTS `{staging}`")
    clickhouse.command(f"CREATE TABLE `{staging}` AS `{TABLE}`")
    seen: set[str] = set()
    batch = []
    files = rows = 0
    try:
        for key in storage.list_keys(prefix=PREFIX):
            if not key.endswith(".json"):
                continue
            manifest = storage.get_json(key=key) or {}
            properties = next(
                (item for item in manifest.get("files", []) if item.get("path") == "pf_listing_properties.jsonl"),
                None,
            )
            if not isinstance(properties, dict) or not properties.get("s3_key"):
                continue
            files += 1
            run_id = str(manifest.get("run_id") or Path(key).stem)
            for raw in iter_json_objects(storage.read_text(key=properties["s3_key"])):
                if str(raw.get("scraped_at") or "")[:10] < args.start_date:
                    continue
                row = _listing_row_tuple(raw, fallback_run_id=run_id)
                if not row[0] or row[0] in seen:
                    continue
                seen.add(row[0])
                batch.append(row)
                if len(batch) >= 5_000:
                    clickhouse.insert_rows(table=staging, rows=batch, column_names=_LISTING_COLUMNS)
                    rows += len(batch)
                    batch.clear()
        if batch:
            clickhouse.insert_rows(table=staging, rows=batch, column_names=_LISTING_COLUMNS)
            rows += len(batch)
        actual = clickhouse.query(f"SELECT count() FROM `{staging}`").result_rows[0][0]
        if actual != args.expected_count:
            raise RuntimeError(f"Snapshot count mismatch: expected={args.expected_count} actual={actual}")
        clickhouse.command(f"EXCHANGE TABLES `{TABLE}` AND `{staging}`")
        print(json.dumps({"status": "replaced", "rows": rows, "files": files, "start_date": args.start_date}))
    finally:
        clickhouse.command(f"DROP TABLE IF EXISTS `{staging}`")


if __name__ == "__main__":
    main()
