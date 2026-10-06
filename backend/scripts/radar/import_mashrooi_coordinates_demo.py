"""Import DLD Mashrooi coordinates from object storage into ClickHouse demo tables.

Demo shortcut for the radar map. This intentionally materializes two simple local
tables from the latest object-storage export instead of building a production resolver.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

import aioboto3
import clickhouse_connect

from app.config import settings

SOURCE = "dld_mashrooi"
MANIFEST_PREFIX = f"raw/source={SOURCE}/manifests/"
PROJECT_COORDINATE_FILE = "dld_mashrooi_project_coordinate_candidates.csv"
DETAIL_POINTS_FILE = "dld_mashrooi_detail_points.csv"

PROJECT_TABLE = "demo_mashrooi_project_coordinates"
DETAIL_TABLE = "demo_mashrooi_detail_points"

PROJECT_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {PROJECT_TABLE}
(
    project_number String,
    project_name_en String,
    latitude Float64,
    longitude Float64,
    coord_method LowCardinality(String),
    detail_point_count UInt32,
    building_point_count UInt32,
    land_point_count UInt32,
    source_manifest_key String,
    source_run_id String,
    imported_at DateTime
)
ENGINE = MergeTree
ORDER BY project_number
"""

DETAIL_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {DETAIL_TABLE}
(
    project_number String,
    project_name_en String,
    point_type LowCardinality(String),
    point_index UInt32,
    point_number String,
    point_name_en String,
    latitude Float64,
    longitude Float64,
    floor_count Nullable(Int32),
    property_type LowCardinality(String),
    source_manifest_key String,
    source_run_id String,
    imported_at DateTime
)
ENGINE = MergeTree
ORDER BY (project_number, point_type, point_index)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import latest DLD Mashrooi coordinate export from object storage into ClickHouse."
    )
    parser.add_argument("--manifest-key", help="Specific manifest key to import instead of latest")
    parser.add_argument("--no-reset", action="store_true", help="Do not recreate demo tables")
    return parser.parse_args()


def object_storage_client_kwargs() -> dict[str, str]:
    kwargs = {
        "aws_access_key_id": settings.OBJECT_STORAGE_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.OBJECT_STORAGE_SECRET_ACCESS_KEY,
        "region_name": settings.OBJECT_STORAGE_REGION or "auto",
    }
    if settings.OBJECT_STORAGE_ENDPOINT_URL:
        kwargs["endpoint_url"] = str(settings.OBJECT_STORAGE_ENDPOINT_URL)
    return kwargs


async def list_objects(s3: Any, prefix: str) -> list[dict[str, Any]]:
    paginator = s3.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    async for page in paginator.paginate(Bucket=settings.OBJECT_STORAGE_BUCKET, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return objects


async def read_text_object(s3: Any, key: str) -> str:
    response = await s3.get_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=key)
    body = await response["Body"].read()
    return body.decode("utf-8-sig")


async def load_manifest(s3: Any, manifest_key: str | None) -> dict[str, Any]:
    if manifest_key:
        manifest = json.loads(await read_text_object(s3, manifest_key))
        manifest["s3_key"] = manifest_key
        return manifest

    candidates = [
        obj
        for obj in await list_objects(s3, MANIFEST_PREFIX)
        if obj["Key"].endswith(".json") and obj.get("Size", 0) > 0
    ]
    if not candidates:
        raise RuntimeError(f"No Mashrooi manifests found under {MANIFEST_PREFIX}")

    latest = max(
        candidates,
        key=lambda obj: obj.get("LastModified") or datetime.min.replace(tzinfo=timezone.utc),
    )
    manifest = json.loads(await read_text_object(s3, latest["Key"]))
    manifest["s3_key"] = latest["Key"]
    return manifest


def manifest_file(manifest: dict[str, Any], path: str) -> dict[str, Any]:
    for file in manifest.get("files", []):
        if file.get("path") == path and file.get("size_bytes", 0) > 0:
            return file
    raise RuntimeError(f"Manifest {manifest.get('s3_key')} does not contain {path}")


def int_value(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def nullable_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def valid_dubai_coordinate(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and 20 <= latitude <= 30
        and 50 <= longitude <= 60
    )


def read_project_rows(
    text_value: str,
    *,
    manifest_key: str,
    run_id: str,
    imported_at: datetime,
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for row in csv.DictReader(io.StringIO(text_value)):
        latitude = float_value(row.get("latitude"))
        longitude = float_value(row.get("longitude"))
        if not valid_dubai_coordinate(latitude, longitude):
            continue
        rows.append(
            (
                row.get("project_number") or "",
                row.get("project_name_en") or "",
                latitude,
                longitude,
                row.get("coord_method") or "",
                int_value(row.get("detail_point_count")),
                int_value(row.get("building_point_count")),
                int_value(row.get("land_point_count")),
                manifest_key,
                run_id,
                imported_at,
            )
        )
    return rows


def read_detail_rows(
    text_value: str,
    *,
    manifest_key: str,
    run_id: str,
    imported_at: datetime,
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for row in csv.DictReader(io.StringIO(text_value)):
        latitude = float_value(row.get("latitude"))
        longitude = float_value(row.get("longitude"))
        if not valid_dubai_coordinate(latitude, longitude):
            continue
        rows.append(
            (
                row.get("project_number") or "",
                row.get("project_name_en") or "",
                row.get("point_type") or "",
                int_value(row.get("point_index")),
                row.get("point_number") or "",
                row.get("point_name_en") or "",
                latitude,
                longitude,
                nullable_int(row.get("floor_count")),
                row.get("property_type") or "",
                manifest_key,
                run_id,
                imported_at,
            )
        )
    return rows


def clickhouse_client():
    return clickhouse_connect.get_client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
        connect_timeout=10,
        send_receive_timeout=300,
    )


def insert_chunks(
    client: Any,
    *,
    table: str,
    rows: list[tuple[Any, ...]],
    column_names: list[str],
    chunk_size: int = 10_000,
) -> None:
    for start in range(0, len(rows), chunk_size):
        client.insert(table, rows[start : start + chunk_size], column_names=column_names)


async def import_mashrooi_coordinates(manifest_key: str | None, reset: bool) -> None:
    session = aioboto3.Session()
    async with session.client("s3", **object_storage_client_kwargs()) as s3:
        manifest = await load_manifest(s3, manifest_key)
        project_file = manifest_file(manifest, PROJECT_COORDINATE_FILE)
        detail_file = manifest_file(manifest, DETAIL_POINTS_FILE)
        project_text, detail_text = await asyncio.gather(
            read_text_object(s3, project_file["s3_key"]),
            read_text_object(s3, detail_file["s3_key"]),
        )

    imported_at = datetime.now(timezone.utc)
    run_id = str(manifest.get("run_id") or "")
    manifest_source_key = str(manifest.get("s3_key") or manifest_key or "")
    project_rows = read_project_rows(
        project_text,
        manifest_key=manifest_source_key,
        run_id=run_id,
        imported_at=imported_at,
    )
    detail_rows = read_detail_rows(
        detail_text,
        manifest_key=manifest_source_key,
        run_id=run_id,
        imported_at=imported_at,
    )

    client = clickhouse_client()
    if reset:
        client.command(f"DROP TABLE IF EXISTS {PROJECT_TABLE}")
        client.command(f"DROP TABLE IF EXISTS {DETAIL_TABLE}")
    client.command(PROJECT_SCHEMA)
    client.command(DETAIL_SCHEMA)
    if reset:
        client.command(f"TRUNCATE TABLE {PROJECT_TABLE}")
        client.command(f"TRUNCATE TABLE {DETAIL_TABLE}")

    insert_chunks(
        client,
        table=PROJECT_TABLE,
        rows=project_rows,
        column_names=[
            "project_number",
            "project_name_en",
            "latitude",
            "longitude",
            "coord_method",
            "detail_point_count",
            "building_point_count",
            "land_point_count",
            "source_manifest_key",
            "source_run_id",
            "imported_at",
        ],
    )
    insert_chunks(
        client,
        table=DETAIL_TABLE,
        rows=detail_rows,
        column_names=[
            "project_number",
            "project_name_en",
            "point_type",
            "point_index",
            "point_number",
            "point_name_en",
            "latitude",
            "longitude",
            "floor_count",
            "property_type",
            "source_manifest_key",
            "source_run_id",
            "imported_at",
        ],
    )

    matched_result = client.query(
        f"""
        SELECT count() AS matched
        FROM ch_projects
        WHERE project_number IN (
            SELECT project_number FROM {PROJECT_TABLE}
        )
        """
    )
    matched = matched_result.result_rows[0][0] if matched_result.result_rows else 0
    print(
        f"Imported {len(project_rows):,} project coordinates and {len(detail_rows):,} "
        f"detail points from {manifest_source_key}; {matched:,} match ch_projects."
    )


def main() -> None:
    args = parse_args()
    asyncio.run(import_mashrooi_coordinates(args.manifest_key, reset=not args.no_reset))


if __name__ == "__main__":
    main()
