#!/usr/bin/env python3
"""Load date-partitioned, normalized DXB Interact sales CSVs into CRM ClickHouse."""

from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import date
from pathlib import Path

import clickhouse_connect

from load_dxbi_sales_units import COLUMNS, CREATE_SALES_SQL, MATCH_ALTERS, SALES_TABLE, refresh_matches
from holocron.sources.dxbi.sales_units import location_key


def number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def integer(value: str | None) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None else None


def event(row: dict[str, str], source_file: str) -> dict[str, object] | None:
    transaction_date, building, area = row.get("transaction_date", ""), row.get("property_name", ""), row.get("area_name", "")
    amount, size = integer(row.get("sale_amount_aed")), number(row.get("transaction_size_sqft"))
    if not transaction_date or not building or not area or not amount or not size:
        return None
    unit = row.get("unit_number", "")
    return {
        "sale_key": row.get("record_key") or hashlib.sha256(f"{transaction_date}|{unit}|{building}|{amount}|{size}".encode()).hexdigest()[:24],
        "transaction_date": date.fromisoformat(transaction_date),
        "unit_number": unit,
        "building_name": building,
        "building_key": location_key(building),
        "project_name": "",
        "area_name": area,
        "area_key": location_key(area),
        "property_type": row.get("property_type", ""),
        "market_status": row.get("status", ""),
        "bedrooms": row.get("bedroom_label", ""),
        "size_sqft": size,
        "size_key": round(size),
        "built_up_area_sqft": number(row.get("bua_sqft")),
        "balcony_sqft": number(row.get("balcony_sqft")),
        "sale_amount_aed": amount,
        "price_per_sqft_aed": number(row.get("sale_price_per_sqft_aed")),
        "capital_gain_pct": None,
        "ltv_pct": None,
        "seller_type": row.get("sold_by", ""),
        "seller_transaction_count": None,
        "agent_side": "",
        "detail_url": row.get("detail_url", ""),
        "source_file": source_file,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--database", default="vitevue")
    parser.add_argument("--username", default="default")
    parser.add_argument("--password", default="")
    args = parser.parse_args()
    client = clickhouse_connect.get_client(host=args.host, port=args.port, database=args.database, username=args.username, password=args.password)
    client.command(CREATE_SALES_SQL)
    for statement in MATCH_ALTERS:
        client.command(statement)
    batch: list[list[object]] = []
    loaded = skipped = 0
    for path in sorted(args.input.glob("date=*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                value = event(row, path.name)
                if not value:
                    skipped += 1
                    continue
                batch.append([value[column] for column in COLUMNS])
                if len(batch) >= 5_000:
                    client.insert(SALES_TABLE, batch, column_names=COLUMNS)
                    loaded += len(batch)
                    batch.clear()
    if batch:
        client.insert(SALES_TABLE, batch, column_names=COLUMNS)
        loaded += len(batch)
    client.command(f"OPTIMIZE TABLE {SALES_TABLE} FINAL")
    refresh_matches(client)
    print(f"loaded={loaded} skipped={skipped}")


if __name__ == "__main__":
    main()
