#!/usr/bin/env python3
"""Re-match imported CRM owner claims against the current DXBI registry."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.clickhouse.client import close_clickhouse
from app.crm.import_service import (
    refresh_contact_import_match_summaries,
    refresh_property_contact_rentals,
    rematch_property_contact_claims,
)
from app.postgres import close_postgres, get_postgres_engine


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--import-id", type=int)
    parser.add_argument(
        "--include-matched",
        action="store_true",
        help="Re-evaluate every claim rather than only unmatched claims.",
    )
    parser.add_argument(
        "--audit-unique-transactions",
        action="store_true",
        help=(
            "Re-evaluate claims previously resolved solely from a globally unique "
            "sale date/price, using their original source address."
        ),
    )
    refresh_mode = parser.add_mutually_exclusive_group()
    refresh_mode.add_argument(
        "--summary-only",
        action="store_true",
        help="Refresh persisted import-card counts without re-running matching.",
    )
    refresh_mode.add_argument(
        "--rentals-only",
        action="store_true",
        help="Refresh rental links for all claims, preserving contacts and ownership assessments.",
    )
    args = parser.parse_args()

    session_factory = async_sessionmaker(
        get_postgres_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with session_factory() as db:
            if args.summary_only:
                result = await refresh_contact_import_match_summaries(
                    db,
                    organization_id=args.organization_id,
                    import_id=args.import_id,
                )
            elif args.rentals_only:
                result = await refresh_property_contact_rentals(
                    db,
                    organization_id=args.organization_id,
                    import_id=args.import_id,
                )
            else:
                result = await rematch_property_contact_claims(
                    db,
                    organization_id=args.organization_id,
                    import_id=args.import_id,
                    only_unmatched=not args.include_matched,
                    audit_resolution_methods=(
                        {"unique_transaction_signature"} if args.audit_unique_transactions else None
                    ),
                )
    finally:
        await close_clickhouse()
        await close_postgres()
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
