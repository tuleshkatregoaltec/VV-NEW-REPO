from __future__ import annotations

import argparse
import os
import sys
import time

from clickhouse_driver import Client

CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_NATIVE_PORT", "9001"))
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "vitevue")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "vitevue_dev")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "vitevue")
CLICKHOUSE_SECURE = os.environ.get("CLICKHOUSE_SECURE", "false").lower() in {"1", "true", "yes"}

PROJECT_FACT_SOURCE = "ch_project_fact"
AREA_FACT_SOURCE = "ch_area_fact"
PROJECT_FACT_SERVING = "ch_project_fact__serving"
AREA_FACT_SERVING = "ch_area_fact__serving"
PROJECT_FACT_BACKUP = "ch_project_fact__source_view"
AREA_FACT_BACKUP = "ch_area_fact__source_view"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local ClickHouse serving fact tables.")
    parser.add_argument("--clickhouse-host", default=CLICKHOUSE_HOST)
    parser.add_argument("--clickhouse-port", type=int, default=CLICKHOUSE_PORT)
    parser.add_argument("--clickhouse-user", default=CLICKHOUSE_USER)
    parser.add_argument("--clickhouse-password", default=CLICKHOUSE_PASSWORD)
    parser.add_argument("--clickhouse-database", default=CLICKHOUSE_DATABASE)
    parser.add_argument(
        "--clickhouse-secure", action=argparse.BooleanOptionalAction, default=CLICKHOUSE_SECURE
    )
    return parser.parse_args()


def get_client(args: argparse.Namespace) -> Client:
    return Client(
        host=args.clickhouse_host,
        port=args.clickhouse_port,
        user=args.clickhouse_user,
        password=args.clickhouse_password,
        database=args.clickhouse_database,
        secure=args.clickhouse_secure,
    )


def build_fact_tables(client: Client) -> None:
    """Materialize the canonical fact views without changing their response contract.

    The local snapshot contains fact *views*.  They are accurate but each Radar
    request expands them into scans across the raw sales and rental tables.  A
    previous builder created tables with a different schema, which made it
    unsafe to run against the current application.  This routine materializes
    the existing canonical views first, then swaps them atomically.
    """
    start = time.time()
    client.execute(f"DROP TABLE IF EXISTS {PROJECT_FACT_SERVING}")
    client.execute(f"DROP TABLE IF EXISTS {AREA_FACT_SERVING}")
    client.execute(f"DROP TABLE IF EXISTS {PROJECT_FACT_BACKUP}")
    client.execute(f"DROP TABLE IF EXISTS {AREA_FACT_BACKUP}")

    print("Materializing ch_project_fact from the canonical source view...")
    client.execute(
        f"CREATE TABLE {PROJECT_FACT_SERVING} ENGINE = MergeTree ORDER BY project_id "
        f"AS SELECT * FROM {PROJECT_FACT_SOURCE}"
    )
    print("Materializing ch_area_fact from the canonical source view...")
    client.execute(
        f"CREATE TABLE {AREA_FACT_SERVING} ENGINE = MergeTree ORDER BY area_name_en "
        f"AS SELECT * FROM {AREA_FACT_SOURCE}"
    )

    client.execute(
        "RENAME TABLE "
        f"{PROJECT_FACT_SOURCE} TO {PROJECT_FACT_BACKUP}, "
        f"{AREA_FACT_SOURCE} TO {AREA_FACT_BACKUP}, "
        f"{PROJECT_FACT_SERVING} TO {PROJECT_FACT_SOURCE}, "
        f"{AREA_FACT_SERVING} TO {AREA_FACT_SOURCE}"
    )

    project_count = client.execute(f"SELECT count() FROM {PROJECT_FACT_SOURCE}")[0][0]
    area_count = client.execute(f"SELECT count() FROM {AREA_FACT_SOURCE}")[0][0]
    print(
        f"Built ch_project_fact ({project_count:,} rows) and "
        f"ch_area_fact ({area_count:,} rows) in {time.time() - start:.2f}s"
    )


def main() -> int:
    build_fact_tables(get_client(parse_args()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
