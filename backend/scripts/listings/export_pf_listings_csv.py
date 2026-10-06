#!/usr/bin/env python3
"""Export the deduplicated Property Finder listing snapshot as a flat CSV.

The raw source stays in object storage; this produces a consumer-friendly, auditable
snapshot with scalar columns suitable for spreadsheets, BI tools, or loading into a
database.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from import_pf_listings_demo import collect_listing_records

CSV_COLUMNS = [
    "listing_id",
    "listing_mode",
    "category_id",
    "property_type_id",
    "property_type",
    "title",
    "reference",
    "share_url",
    "price_value_aed",
    "price_currency",
    "price_period",
    "size_value_sqft",
    "size_unit",
    "price_per_sqft_aed",
    "bedrooms",
    "bathrooms",
    "city_name",
    "area_name",
    "subcommunity_name",
    "tower_name",
    "location_name",
    "latitude",
    "longitude",
    "is_available",
    "is_verified",
    "is_featured",
    "is_premium",
    "listed_date",
    "scraped_at",
    "agent_name",
    "agent_phone",
    "broker_name",
    "broker_phone",
    "image_count",
    "floorplan_count",
    "furnished",
    "completion_status",
    "rera",
    "number_of_cheques",
    "video_url",
    "view_360_url",
    "source_run_id",
    "source_manifest_key",
]


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""


def _value(record: dict[str, Any], key: str) -> Any:
    if key == "price_value_aed":
        return record.get("price_value")
    if key == "size_value_sqft":
        return record.get("size_value")
    if key == "price_per_sqft_aed":
        price, size = record.get("price_value"), record.get("size_value")
        return round(price / size, 2) if isinstance(price, int | float) and size else ""
    if key == "agent_name":
        return record["agent"].get("name")
    if key == "agent_phone":
        return record["agent"].get("phone")
    if key == "broker_name":
        return record["broker"].get("name")
    if key == "broker_phone":
        return record["broker"].get("phone")
    if key in {"listed_date", "scraped_at"}:
        return _iso(record.get(key))
    return record.get(key, "")


def flat_record(record: dict[str, Any]) -> dict[str, Any]:
    return {column: _value(record, column) for column in CSV_COLUMNS}


async def export_csv(output_path: Path) -> None:
    records, counts = await collect_listing_records(max_per_mode=0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(flat_record(record))
    os.replace(temporary_path, output_path)

    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "file": output_path.name,
        "total_rows": len(records),
        "rows_by_mode": counts,
        "columns": CSV_COLUMNS,
        "deduplication_key": "listing_id",
        "source": "Property Finder raw listing manifests in object storage",
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="Destination .csv file")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".csv":
        parser.error("output must end with .csv")
    asyncio.run(export_csv(args.output))


if __name__ == "__main__":
    main()
