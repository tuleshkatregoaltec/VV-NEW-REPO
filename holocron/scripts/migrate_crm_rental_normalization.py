#!/usr/bin/env python3
"""Upgrade the derived CRM rental tables without touching source scrape files."""

from __future__ import annotations

import argparse
import logging
import os

import clickhouse_connect

logger = logging.getLogger("crm_rental_normalization")

TABLES = ("dxbi_rental_events", "dxbi_rental_unit_candidates")
ALTERS = (
    "ADD COLUMN IF NOT EXISTS contract_amount_aed UInt64 DEFAULT 0 AFTER size_sqft",
    "ADD COLUMN IF NOT EXISTS contract_term_days UInt32 DEFAULT 0 AFTER contract_amount_aed",
    "ADD COLUMN IF NOT EXISTS contract_term_months Float32 DEFAULT 0 AFTER contract_term_days",
    "ADD COLUMN IF NOT EXISTS rent_normalization_version UInt8 DEFAULT 0 AFTER annual_rent_aed",
    "ADD COLUMN IF NOT EXISTS address_normalization_version UInt8 DEFAULT 0 AFTER rent_normalization_version",
)


def _canonical_area(expression: str) -> str:
    cleaned = (
        "trimBoth(replaceRegexpAll(replaceRegexpAll("
        f"{expression}, '(?i)\\s+Building\\s*$', ''), "
        "'(?i)\\s*\\((?:JVC|JLT|JVT|DSO|IMPZ|JBR|TECOM)\\)\\s*$', ''))"
    )
    cleaned = f"trimBoth(replaceRegexpAll({cleaned}, '\\)+$', ''))"
    for ordinal, number in {
        "first": "1",
        "second": "2",
        "third": "3",
        "fourth": "4",
        "fifth": "5",
        "sixth": "6",
    }.items():
        cleaned = f"replaceRegexpAll({cleaned}, '(?i)\\\\b{ordinal}\\\\b', '{number}')"
    key = f"lowerUTF8({cleaned})"
    return f"""
        multiIf(
            startsWith({key}, 'international city'), 'International City',
            {key} IN ('jvc', 'jumeirah village circle'), 'Jumeirah Village Circle',
            {key} IN ('jlt', 'jumeirah lake towers'), 'Jumeirah Lake Towers',
            {key} IN ('jvt', 'jumeirah village triangle'), 'Jumeirah Village Triangle',
            {key} IN ('dso', 'dubai silicon oasis'), 'Dubai Silicon Oasis',
            {key} IN (
                'impz',
                'international media production zone',
                'dubai production city'
            ), 'Dubai Production City',
            {key} IN ('jbr', 'jumeirah beach residence'), 'Jumeirah Beach Residence',
            {key} IN ('tecom', 'barsha heights'), 'Barsha Heights',
            {key} IN ('dubai hills', 'dubai hills estate'), 'Dubai Hills Estate',
            {key} IN ('dip', 'dubai investment park'), 'Dubai Investment Park',
            {key} IN ('difc', 'dubai international financial center'), 'DIFC',
            {key} = 'mirdif', 'Mirdif',
            {cleaned}
        )
    """


def migrate(client) -> None:
    for table in TABLES:
        for alter in ALTERS:
            client.command(f"ALTER TABLE {table} {alter}")

        client.command(
            f"""
            ALTER TABLE {table} UPDATE
                contract_amount_aed = annual_rent_aed,
                contract_term_days = toUInt32(dateDiff('day', lease_start, lease_end) + 1),
                contract_term_months = toFloat32(
                    round((dateDiff('day', lease_start, lease_end) + 1) / 30.4375, 2)
                ),
                annual_rent_aed = toUInt64(round(
                    annual_rent_aed * 365.25
                    / greatest(dateDiff('day', lease_start, lease_end) + 1, 1)
                )),
                rent_normalization_version = 1
            WHERE rent_normalization_version = 0
            SETTINGS mutations_sync = 2
            """
        )

        client.command(
            f"""
            ALTER TABLE {table} UPDATE
                area_name = if(
                    property_type IN ('Villa', 'Townhouse') AND project_name != '',
                    project_name,
                    area_name
                ),
                project_name = if(
                    property_type IN ('Villa', 'Townhouse'),
                    building_name,
                    project_name
                ),
                building_name = if(
                    property_type IN ('Villa', 'Townhouse'),
                    '',
                    building_name
                ),
                address_normalization_version = 1
            WHERE address_normalization_version = 0
            SETTINGS mutations_sync = 2
            """
        )
        client.command(
            f"""
            ALTER TABLE {table} UPDATE
                area_name = {_canonical_area("if(property_type IN ('Villa', 'Townhouse') AND match(area_name, '^[0-9]+$'), trimBoth(arrayElement(splitByChar(',', location_name), -1)), area_name)")},
                address_normalization_version = 5
            WHERE address_normalization_version < 5
            SETTINGS mutations_sync = 2
            """
        )
        logger.info("Normalized %s", table)

    client.command(
        """
        ALTER TABLE dxbi_sales_unit_events
        ADD COLUMN IF NOT EXISTS address_normalization_version UInt8 DEFAULT 0 AFTER area_key
        """
    )
    client.command(
        f"""
        ALTER TABLE dxbi_sales_unit_events UPDATE
            area_name = {_canonical_area('area_name')},
            area_key = replaceRegexpAll(
                replaceAll(lowerUTF8({_canonical_area('area_name')}), 'jumeriah', 'jumeirah'),
                '[^a-z0-9]+',
                ''
            ),
            address_normalization_version = 5
        WHERE area_name != '' AND address_normalization_version < 5
        SETTINGS mutations_sync = 2
        """
    )
    logger.info("Normalized dxbi_sales_unit_events areas")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CLICKHOUSE_PORT", "8123")))
    parser.add_argument("--database", default=os.getenv("CLICKHOUSE_DATABASE", "vitevue"))
    parser.add_argument("--username", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("CLICKHOUSE_PASSWORD", ""))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        database=args.database,
        username=args.username,
        password=args.password,
    )
    migrate(client)


if __name__ == "__main__":
    main()
