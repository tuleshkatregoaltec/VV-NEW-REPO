#!/usr/bin/env python3
"""Validate and atomically exchange the DXB rental v2 tables into canonical names."""

from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import date

import clickhouse_connect

logger = logging.getLogger("dxbi_rental_v2_cutover")

EVENTS = "dxbi_rental_events"
EVENTS_V2 = "dxbi_rental_events_v2"
CANDIDATES = "dxbi_rental_unit_candidates"
CANDIDATES_V2 = "dxbi_rental_unit_candidates_v2"


def _scalar(client, sql: str) -> int:
    return int(client.query(sql).result_rows[0][0])


def validate(client, *, backfill_run_id: str, cutover_date: date) -> dict[str, int | str]:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", backfill_run_id):
        raise ValueError("backfill run id contains unsupported characters")
    required_tables = (EVENTS, EVENTS_V2, CANDIDATES, CANDIDATES_V2)
    quoted = ", ".join(f"'{table}'" for table in required_tables)
    if _scalar(
        client,
        f"SELECT count() FROM system.tables "
        f"WHERE database = currentDatabase() AND name IN ({quoted})",
    ) != len(required_tables):
        raise RuntimeError("canonical and v2 rental tables must all exist before cutover")
    if _scalar(
        client,
        f"SELECT count() FROM system.columns WHERE database = currentDatabase() "
        f"AND table = '{EVENTS}' AND name = 'contract_key'",
    ):
        raise RuntimeError("canonical rental table already exposes contract_key; v2 appears active")

    event_rows = _scalar(client, f"SELECT count() FROM {EVENTS_V2} FINAL")
    event_keys = _scalar(client, f"SELECT uniqExact(contract_key) FROM {EVENTS_V2} FINAL")
    candidate_rows = _scalar(client, f"SELECT count() FROM {CANDIDATES_V2} FINAL")
    valid_backfill_runs = _scalar(
        client,
        f"""
        SELECT count()
        FROM dxbi_rental_run_reconciliation FINAL
        WHERE run_id = '{backfill_run_id}'
          AND report_type = 'rentals'
          AND status = 'success'
          AND quarantined_rows = 0
          AND expected_partitions > 0
          AND completed_partitions = expected_partitions
        """,
    )
    if event_rows == 0 or candidate_rows == 0:
        raise RuntimeError("v2 rental tables must be non-empty")
    if event_rows != event_keys:
        raise RuntimeError(f"v2 event identity is not unique: rows={event_rows} keys={event_keys}")
    if valid_backfill_runs != 1:
        raise RuntimeError(f"backfill run {backfill_run_id} is missing or incomplete")
    coverage = client.query(
        f"SELECT toString(min(source_shard_date)), toString(max(source_shard_date)) "
        f"FROM {EVENTS_V2} FINAL"
    ).result_rows[0]
    if not coverage[0] or date.fromisoformat(str(coverage[0])) > date(2025, 1, 1):
        raise RuntimeError(f"v2 rentals do not start at 2025-01-01: {coverage[0] or 'empty'}")
    if not coverage[1] or date.fromisoformat(str(coverage[1])) < cutover_date:
        raise RuntimeError(
            f"v2 rentals end at {coverage[1] or 'empty'}, before cutover {cutover_date}"
        )
    return {
        "event_rows": event_rows,
        "event_keys": event_keys,
        "candidate_rows": candidate_rows,
        "backfill_run_id": backfill_run_id,
        "coverage_start": str(coverage[0]),
        "coverage_end": str(coverage[1]),
    }


def activate(client, *, backfill_run_id: str, cutover_date: date) -> dict[str, int | str]:
    summary = validate(client, backfill_run_id=backfill_run_id, cutover_date=cutover_date)
    client.command(f"EXCHANGE TABLES {EVENTS} AND {EVENTS_V2}")
    try:
        client.command(f"EXCHANGE TABLES {CANDIDATES} AND {CANDIDATES_V2}")
    except Exception:
        client.command(f"EXCHANGE TABLES {EVENTS} AND {EVENTS_V2}")
        raise
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CLICKHOUSE_PORT", "8123")))
    parser.add_argument("--database", default=os.getenv("CLICKHOUSE_DATABASE", "vitevue"))
    parser.add_argument("--username", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--backfill-run-id", required=True)
    parser.add_argument("--cutover-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Perform the exchanges. Without this flag the script only validates.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        database=args.database,
        username=args.username,
        password=args.password,
    )
    kwargs = {"backfill_run_id": args.backfill_run_id, "cutover_date": args.cutover_date}
    summary = activate(client, **kwargs) if args.activate else validate(client, **kwargs)
    logger.info("%s validation passed: %s", "Cutover" if args.activate else "Pre-cutover", summary)


if __name__ == "__main__":
    main()
