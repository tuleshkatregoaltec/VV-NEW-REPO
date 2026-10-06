#!/usr/bin/env python3
"""Flatten Property Finder raw listing manifests into one spreadsheet-ready CSV."""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from holocron.platform.object_storage import ObjectStorageClient
from holocron.platform.settings import settings

MANIFEST_PREFIX = "raw/source=pf_listings/manifests/"
PF_BASE_URL = "https://www.propertyfinder.ae"
CSV_COLUMNS = [
    "listing_id", "listing_mode", "category_id", "property_type_id", "property_type", "title",
    "reference", "share_url", "price_value_aed", "price_currency", "price_period",
    "size_value_sqft", "size_unit", "price_per_sqft_aed", "bedrooms", "bathrooms",
    "city_name", "area_name", "subcommunity_name", "tower_name", "location_name", "latitude",
    "longitude", "is_available", "is_verified", "is_featured", "is_premium", "listed_date",
    "scraped_at", "agent_name", "agent_phone", "broker_name", "broker_phone", "image_count",
    "floorplan_count", "furnished", "completion_status", "rera", "number_of_cheques", "video_url",
    "view_360_url", "source_run_id", "source_manifest_key",
]
DECODER = json.JSONDecoder()


def iter_json_objects(text: str) -> Iterable[dict[str, Any]]:
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = DECODER.raw_decode(text, index)
        if isinstance(value, dict):
            yield value


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def number(value: Any) -> int | float | str:
    if value in (None, ""):
        return ""
    try:
        parsed = float(value)
        return int(parsed) if parsed.is_integer() else parsed
    except (TypeError, ValueError):
        return ""


def url(value: Any) -> str:
    value = text(value)
    if not value or value.startswith(("http://", "https://")):
        return value
    return f"{PF_BASE_URL}{value}" if value.startswith("/") else value


def names_for(row: dict[str, Any]) -> list[str]:
    names = [text(value) for value in as_list(row.get("listing_location_names")) if text(value)]
    if names:
        return names
    return [
        text(as_dict(item).get("name"))
        for item in as_list(row.get("location_tree"))
        if as_dict(item).get("name")
    ]


def listing_mode(row: dict[str, Any], raw: dict[str, Any]) -> str:
    candidate = " ".join((text(raw.get("offering_type")), text(row.get("details_path")), text(row.get("share_url")))).lower()
    if any(token in candidate for token in ("sale", "/buy/", "for-sale")):
        return "sale"
    if any(token in candidate for token in ("rent", "for-rent")):
        return "rent"
    return "sale" if row.get("category_id") in (1, 3) else "rent" if row.get("category_id") in (2, 4) else ""


def row_for(raw_row: dict[str, Any], source_manifest_key: str) -> dict[str, Any] | None:
    raw = as_dict(as_dict(raw_row.get("raw_wrapper")).get("property"))
    listing_id = text(raw_row.get("listing_id") or raw_row.get("property_key") or raw.get("id"))
    mode = listing_mode(raw_row, raw)
    if not listing_id or not mode:
        return None
    price = as_dict(raw_row.get("price")) or as_dict(raw.get("price"))
    size = as_dict(raw_row.get("size")) or as_dict(raw.get("size"))
    location = as_dict(raw_row.get("location"))
    coordinates = as_dict(location.get("coordinates"))
    agent, broker = as_dict(raw_row.get("agent")) or as_dict(raw.get("agent")), as_dict(raw_row.get("broker")) or as_dict(raw.get("broker"))
    names = names_for(raw_row)
    price_value, size_value = number(price.get("value")), number(size.get("value"))
    price_per_sqft = round(float(price_value) / float(size_value), 2) if price_value != "" and size_value not in ("", 0) else ""
    images = as_list(raw_row.get("images")) or as_list(raw.get("images"))
    return {
        "listing_id": listing_id, "listing_mode": mode, "category_id": number(raw_row.get("category_id") or raw.get("category_id")),
        "property_type_id": number(raw_row.get("property_type_id") or raw.get("property_type_id")),
        "property_type": text(raw.get("property_type") or raw_row.get("type") or raw_row.get("property_type_id")),
        "title": text(raw_row.get("title") or raw.get("title")), "reference": text(raw_row.get("reference") or raw.get("reference")),
        "share_url": url(raw_row.get("share_url") or raw_row.get("details_path") or raw.get("details_path")),
        "price_value_aed": price_value, "price_currency": text(price.get("currency")), "price_period": text(price.get("period")),
        "size_value_sqft": size_value, "size_unit": text(size.get("unit")), "price_per_sqft_aed": price_per_sqft,
        "bedrooms": text(raw_row.get("bedrooms") or raw.get("bedrooms")), "bathrooms": text(raw_row.get("bathrooms") or raw.get("bathrooms")),
        "city_name": names[0] if len(names) > 0 else "", "area_name": names[1] if len(names) > 1 else "",
        "subcommunity_name": names[2] if len(names) > 2 else "", "tower_name": names[3] if len(names) > 3 else "",
        "location_name": text(location.get("full_name")) or ", ".join(names),
        "latitude": number(raw_row.get("latitude") or coordinates.get("lat")), "longitude": number(raw_row.get("longitude") or coordinates.get("lon")),
        "is_available": raw_row.get("is_available"), "is_verified": raw_row.get("is_verified"), "is_featured": raw_row.get("is_featured"), "is_premium": raw_row.get("is_premium"),
        "listed_date": text(raw.get("listed_date")), "scraped_at": text(raw_row.get("scraped_at")),
        "agent_name": text(agent.get("name")), "agent_phone": text(agent.get("phone")), "broker_name": text(broker.get("name")), "broker_phone": text(broker.get("phone")),
        "image_count": number(raw.get("images_count")) or len(images), "floorplan_count": len(as_list(raw.get("floor_plans"))),
        "furnished": text(raw.get("furnished")), "completion_status": text(raw.get("completion_status")), "rera": text(raw.get("rera")),
        "number_of_cheques": number(raw.get("number_of_cheques")), "video_url": url(raw.get("video_url")), "view_360_url": url(raw.get("view_360")),
        "source_run_id": Path(source_manifest_key).stem, "source_manifest_key": source_manifest_key,
    }


def manifest_sort_key(manifest: dict[str, Any]) -> str:
    return text(manifest.get("created_at") or manifest.get("finished_at") or manifest.get("run_id"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    storage = ObjectStorageClient(settings)
    manifests = []
    for key in storage.list_keys(prefix=MANIFEST_PREFIX):
        if key.endswith(".json"):
            manifest = storage.get_json(key=key)
            if manifest:
                manifest["_key"] = key
                manifests.append(manifest)
    records: dict[str, dict[str, Any]] = {}
    source_files = 0
    for manifest in sorted(manifests, key=manifest_sort_key, reverse=True):
        properties = next((file for file in manifest.get("files", []) if file.get("path") == "pf_listing_properties.jsonl"), None)
        if not isinstance(properties, dict) or not properties.get("s3_key"):
            continue
        source_files += 1
        for raw_row in iter_json_objects(storage.read_text(key=properties["s3_key"])):
            record = row_for(raw_row, manifest["_key"])
            if record and record["listing_id"] not in records:
                records[record["listing_id"]] = record
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in sorted(records.values(), key=lambda value: value["listing_id"]):
            writer.writerow(record)
    os.replace(temporary, args.output)
    modes = {mode: sum(row["listing_mode"] == mode for row in records.values()) for mode in ("sale", "rent")}
    metadata = {"generated_at": datetime.now(timezone.utc).isoformat(), "total_rows": len(records), "rows_by_mode": modes, "source_manifest_files": source_files, "source": "Property Finder raw listing manifests", "deduplication_key": "listing_id", "columns": CSV_COLUMNS}
    args.output.with_suffix(".manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
