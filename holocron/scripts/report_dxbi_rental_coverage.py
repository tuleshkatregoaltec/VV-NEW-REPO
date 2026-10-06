#!/usr/bin/env python3
"""Publish monthly DXB Interact coverage with DLD as a scoped benchmark."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import clickhouse_connect

COMPARABLE_SCOPES = {"residential_home", "commercial"}


def coverage_sql(
    dxbi_table: str, benchmark_table: str = "silver_rent_contracts"
) -> str:
    return f"""
    WITH
    dxbi AS (
        SELECT
            toStartOfMonth(lease_start) AS month,
            multiIf(
                property_type IN ('Apartment', 'Villa', 'Townhouse', 'Hotel Apartment'),
                    'residential_home',
                property_type IN ('Commercial', 'Office', 'Shop', 'Warehouse', 'Land'),
                    'commercial',
                'other'
            ) AS market_scope,
            count() AS dxbi_rows
        FROM {dxbi_table} FINAL
        WHERE lease_start >= {{start_date:Date}} AND lease_start <= {{end_date:Date}}
        GROUP BY month, market_scope
    ),
    dld_project_multiplicity AS (
        SELECT
            toStartOfMonth(contract_start_date) AS month,
            market_scope,
            tuple(
                registration_date,
                contract_start_date,
                contract_end_date,
                property_type,
                property_sub_type,
                property_usage,
                rooms,
                parking,
                actual_area_sqm,
                annual_amount_aed,
                contract_amount_aed,
                total_properties,
                version_number,
                contract_version,
                parcel_id,
                area_name_en,
                property_id,
                land_property_id,
                is_free_hold,
                tenant_type,
                contract_reg_type,
                ejari_property_type_id,
                ejari_property_sub_type_id,
                ejari_business_property_type
            ) AS contract_signature,
            tuple(project_name_en, master_project_en) AS project_label,
            dateDiff('day', contract_start_date, registration_date) > 14
                AS registered_after_14_days,
            dateDiff('day', contract_start_date, registration_date) > 180
                AS registered_after_180_days,
            dateDiff('day', contract_start_date, registration_date) > 365
                AS registered_after_365_days,
            count() AS project_multiplicity
        FROM {benchmark_table} FINAL
        WHERE contract_start_date >= {{start_date:Date}}
          AND contract_start_date <= {{end_date:Date}}
        GROUP BY
            month,
            market_scope,
            contract_signature,
            project_label,
            registered_after_14_days,
            registered_after_180_days,
            registered_after_365_days
    ),
    dld_signatures AS (
        SELECT
            month,
            market_scope,
            contract_signature,
            sum(project_multiplicity) AS raw_rows_at_signature,
            max(project_multiplicity) AS defanned_rows_at_signature,
            max(project_multiplicity) * max(registered_after_14_days)
                AS registered_after_14_days,
            max(project_multiplicity) * max(registered_after_180_days)
                AS registered_after_180_days,
            max(project_multiplicity) * max(registered_after_365_days)
                AS registered_after_365_days
        FROM dld_project_multiplicity
        GROUP BY month, market_scope, contract_signature
    ),
    dld AS (
        SELECT
            month,
            market_scope,
            sum(raw_rows_at_signature) AS dld_raw_rows,
            sum(defanned_rows_at_signature) AS dld_rows,
            sum(raw_rows_at_signature - defanned_rows_at_signature)
                AS dld_project_fanout_rows,
            sum(registered_after_14_days) AS registered_after_14_days,
            sum(registered_after_180_days) AS registered_after_180_days,
            sum(registered_after_365_days) AS registered_after_365_days
        FROM dld_signatures
        GROUP BY month, market_scope
    ),
    all_keys AS (
        SELECT month, market_scope FROM dxbi
        UNION DISTINCT
        SELECT month, market_scope FROM dld
    )
    SELECT
        toString(all_keys.month) AS month,
        all_keys.market_scope AS market_scope,
        ifNull(dxbi.dxbi_rows, 0) AS dxbi_rows,
        ifNull(dld.dld_raw_rows, 0) AS dld_raw_rows,
        ifNull(dld.dld_rows, 0) AS dld_rows,
        ifNull(dld.dld_project_fanout_rows, 0) AS dld_project_fanout_rows,
        ifNull(dld.registered_after_14_days, 0) AS registered_after_14_days,
        ifNull(dld.registered_after_180_days, 0) AS registered_after_180_days,
        ifNull(dld.registered_after_365_days, 0) AS registered_after_365_days
    FROM all_keys
    LEFT JOIN dxbi
      ON all_keys.month = dxbi.month AND all_keys.market_scope = dxbi.market_scope
    LEFT JOIN dld
      ON all_keys.month = dld.month AND all_keys.market_scope = dld.market_scope
    ORDER BY month, market_scope
    """


def classify_rows(rows: list[dict[str, Any]], quarantine_rows: int) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    remaining_quarantine = quarantine_rows
    for row in rows:
        dxbi_rows = int(row.get("dxbi_rows") or 0)
        dld_rows = int(row.get("dld_rows") or 0)
        delta = dxbi_rows - dld_rows
        scope = str(row.get("market_scope") or "other")
        if scope not in COMPARABLE_SCOPES:
            lag = parsing = 0
            source_scope = abs(delta)
        else:
            source_scope = 0
            lag = min(max(-delta, 0), int(row.get("registered_after_365_days") or 0))
            parsing = min(max(abs(delta) - lag, 0), remaining_quarantine)
            remaining_quarantine -= parsing
        unresolved = max(abs(delta) - lag - parsing - source_scope, 0)
        classified.append(
            {
                **row,
                "delta_dxbi_minus_dld": delta,
                "residual_classification": {
                    "dxbi_source_scope": source_scope,
                    "registration_lag": lag,
                    "parsing_quarantine": parsing,
                    "unresolved": unresolved,
                },
            }
        )
    return classified


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CLICKHOUSE_PORT", "8123")))
    parser.add_argument("--database", default=os.getenv("CLICKHOUSE_DATABASE", "vitevue"))
    parser.add_argument(
        "--benchmark-database",
        default="",
        help="Database containing silver_rent_contracts; defaults to --database.",
    )
    parser.add_argument("--username", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--table", default="dxbi_rental_events_v2")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.start_date > args.end_date:
        raise ValueError("start date must be on or before end date")
    if args.table not in {"dxbi_rental_events", "dxbi_rental_events_v2"}:
        raise ValueError("--table must be a canonical DXB rental event table")
    benchmark_database = args.benchmark_database or args.database
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", benchmark_database):
        raise ValueError("--benchmark-database must be a ClickHouse identifier")

    client = clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        database=args.database,
        username=args.username,
        password=args.password,
    )
    rows = client.query(
        coverage_sql(args.table, f"`{benchmark_database}`.`silver_rent_contracts`"),
        parameters={
            "start_date": args.start_date.isoformat(),
            "end_date": args.end_date.isoformat(),
        },
    ).named_results()
    quarantine_rows = int(
        client.query(
            """
            SELECT ifNull(argMax(quarantined_rows, finished_at), 0)
            FROM dxbi_rental_run_reconciliation FINAL
            WHERE report_type = 'rentals'
            """
        ).result_rows[0][0]
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date": args.start_date.isoformat(),
        "end_date": args.end_date.isoformat(),
        "dxbi_table": args.table,
        "benchmark": (
            "DLD/Ejari silver_rent_contracts conservatively de-fanned across project labels; "
            "count parity is not assumed"
        ),
        "quarantined_rows_in_latest_load": quarantine_rows,
        "months": classify_rows(list(rows), quarantine_rows),
    }
    if args.output:
        _atomic_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
