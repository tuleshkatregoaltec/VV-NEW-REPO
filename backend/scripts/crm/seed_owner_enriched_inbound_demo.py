"""Replace the legacy synthetic inbox with an owner-enriched QA campaign.

The generated enquiries are explicitly labelled as simulations. Identities and
contact-match evidence come from the organization's existing owner imports; no
owner records are changed. Raw contact data is held in memory and is never
written to a repository file.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.crm.inbound_service import delete_inbound_import, process_inbound_import

LEGACY_IMPORT_NAMES = {"lead-inbox-waterfront-campaign-demo"}
DEMO_IMPORT_NAME = "Owner intelligence QA — simulated inbound"
COMPANY_MARKERS = (
    "L.L.C",
    " LLC",
    "LIMITED",
    "DEVELOP",
    "PROPERT",
    "INVEST",
    "REAL ESTATE",
    "HOLDING",
    " FZE",
    " FZCO",
    " LTD",
    " PJSC",
    "FOUNDATION",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--rows", type=int, default=60)
    return parser.parse_args()


def _person_name(value: str) -> bool:
    upper = value.upper()
    return len(value.split()) >= 2 and not any(marker in upper for marker in COMPANY_MARKERS)


def _category(row: dict[str, Any]) -> str:
    if row["properties"] >= 2 and row["current_properties"]:
        return "current portfolio owner"
    if row["properties"] == 1 and row["rental_properties"]:
        return "rental owner"
    if row["properties"] == 1 and row["current_properties"]:
        return "current owner"
    if row["properties"] >= 2:
        return "prior portfolio owner"
    return "prior owner"


def _select_balanced(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    categories = (
        "current portfolio owner",
        "rental owner",
        "current owner",
        "prior portfolio owner",
        "prior owner",
    )
    buckets = {category: [] for category in categories}
    for row in rows:
        if _person_name(row["owner_name"]):
            buckets[_category(row)].append(row)

    selected: list[dict[str, Any]] = []
    used: set[str] = set()

    # Keep the user's explicit validation example when it is present.
    shahram = next(
        (row for row in rows if row["owner_name"].upper() == "SHAHRAM TAGHI SHAMSAEE"),
        None,
    )
    if shahram:
        selected.append(shahram)
        used.add(shahram["owner_name"].casefold())

    while len(selected) < limit:
        progressed = False
        for category in categories:
            while buckets[category]:
                candidate = buckets[category].pop(0)
                identity = candidate["owner_name"].casefold()
                if identity in used:
                    continue
                selected.append(candidate)
                used.add(identity)
                progressed = True
                break
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def _opportunity_value(row: dict[str, Any], intent: str, index: int) -> int:
    observed = int(row["max_property_value"] or 0)
    if intent in {"rent", "let"}:
        annual = observed * (5 + index % 3) // 100
        return max(75_000, min(1_500_000, annual or 180_000))
    multiplier = (90, 105, 120, 140)[index % 4]
    return max(1_000_000, min(40_000_000, observed * multiplier // 100 or 3_000_000))


def _csv_upload(rows: list[dict[str, Any]]) -> UploadFile:
    output = io.StringIO(newline="")
    headers = [
        "Full Name",
        "Phone",
        "Intent",
        "Source",
        "Campaign",
        "Lead ID",
        "Message",
        "Location",
        "Property Type",
        "Bedrooms",
        "Maximum Price",
        "Building",
        "Unit Number",
        "Lead Date",
        "Consent",
    ]
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    intents = ("buy", "sell")
    intent_labels = {"buy": "Buyer", "sell": "Seller"}
    intent_phrases = {
        "buy": "looking to buy",
        "sell": "want to sell",
    }
    locations = ("Dubai Marina", "Downtown Dubai", "Business Bay", "Palm Jumeirah")
    property_types = ("Apartment", "Villa", "Apartment", "Townhouse")
    now = datetime.now(timezone.utc)
    for index, owner in enumerate(rows):
        intent = intents[index % len(intents)]
        location = (
            str(owner.get("area_name") or locations[index % len(locations)])
            if intent == "sell"
            else locations[index % len(locations)]
        )
        raw_property_type = str(owner.get("property_type") or "").strip().casefold()
        generic_property_types = {
            "",
            "flat",
            "residential",
            "residential flat",
            "residential flats",
            "unit",
        }
        property_type = (
            property_types[index % len(property_types)]
            if intent == "buy" or raw_property_type in generic_property_types
            else str(owner["property_type"])
        )
        value = _opportunity_value(owner, intent, index)
        category = _category(owner)
        # One quarter intentionally uses name-only linkage to exercise the
        # verification-required path rather than pretending every match is exact.
        phone = "" if index % 4 == 3 else str(owner["phone"] or "")
        message = (
            f"Simulated QA enquiry: {intent_phrases[intent]} a {property_type.lower()} "
            f"in {location}; "
            f"budget AED {value:,}. Registry fixture category: {category}."
        )
        writer.writerow(
            {
                "Full Name": owner["owner_name"].title(),
                "Phone": phone,
                "Intent": intent_labels[intent],
                "Source": "QA simulation",
                "Campaign": DEMO_IMPORT_NAME,
                "Lead ID": f"OWNER-QA-{index + 1:03d}",
                "Message": message,
                "Location": location,
                "Property Type": property_type,
                "Bedrooms": 1 + index % 5,
                "Maximum Price": value,
                "Building": owner.get("building_name") if intent == "sell" else "",
                "Unit Number": owner.get("unit_number") if intent == "sell" else "",
                "Lead Date": (now - timedelta(minutes=index * 4)).isoformat(),
                "Consent": "unknown",
            }
        )
    payload = io.BytesIO(output.getvalue().encode("utf-8"))
    return UploadFile(file=payload, filename="owner-intelligence-qa-simulated-inbound.csv")


async def _run(args: argparse.Namespace) -> None:
    engine = create_async_engine(str(settings.POSTGRES_URL), pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            result = await db.exec(
                text(
                    """
                    select
                        lower(trim(contact_name)) as owner_norm,
                        min(contact_name) as owner_name,
                        (array_agg(phone_primary) filter (
                            where phone_primary is not null and phone_primary <> ''
                        ))[1] as phone,
                        count(distinct property_key) as properties,
                        count(distinct property_key) filter (
                            where ownership_status in ('verified_current_owner', 'probable_current_owner')
                        ) as current_properties,
                        count(distinct property_key) filter (
                            where ownership_status = 'former_owner'
                        ) as prior_properties,
                        count(distinct property_key) filter (
                            where ownership_status in ('verified_current_owner', 'probable_current_owner')
                              and (lease_end is not null or lead_id is not null)
                        ) as rental_properties,
                        max(coalesce(latest_sale_price_aed, transaction_price_aed, 0)) as max_property_value
                        ,(array_agg(area_name order by confidence_score desc) filter (
                            where area_name <> ''
                        ))[1] as area_name
                        ,(array_agg(building_name order by confidence_score desc) filter (
                            where building_name <> ''
                        ))[1] as building_name
                        ,(array_agg(unit_number order by confidence_score desc) filter (
                            where unit_number <> ''
                        ))[1] as unit_number
                        ,(array_agg(property_type order by confidence_score desc) filter (
                            where property_type <> ''
                        ))[1] as property_type
                    from crm_property_contact_claims
                    where organization_id = :organization_id
                      and phone_primary is not null
                      and phone_primary <> ''
                      and ownership_status in (
                          'verified_current_owner', 'probable_current_owner', 'former_owner'
                      )
                    group by lower(trim(contact_name))
                    order by
                        (lower(trim(contact_name)) = 'shahram taghi shamsaee') desc,
                        count(distinct property_key) desc,
                        max(coalesce(latest_sale_price_aed, transaction_price_aed, 0)) desc
                    limit 3000
                    """
                ),
                params={"organization_id": args.organization_id},
            )
            candidates = [dict(row._mapping) for row in result.all()]
            selected = _select_balanced(candidates, args.rows)
            if len(selected) < args.rows:
                raise RuntimeError(f"Only {len(selected)} suitable owner identities were found")

            imports = await db.exec(
                text(
                    """
                    select id, name from crm_inbound_imports
                    where organization_id = :organization_id
                    order by id
                    """
                ),
                params={"organization_id": args.organization_id},
            )
            removable = [
                int(row.id)
                for row in imports.all()
                if row.name in LEGACY_IMPORT_NAMES or row.name == DEMO_IMPORT_NAME
            ]
            for import_id in removable:
                await delete_inbound_import(db, import_id, args.organization_id)

            response = await process_inbound_import(
                db,
                upload=_csv_upload(selected),
                name=DEMO_IMPORT_NAME,
                user_id=args.user_id,
                organization_id=args.organization_id,
                campaign_context=(
                    "Simulated inbound enquiries for validating owner-registry enrichment and "
                    "commercial-priority ordering. The messages and intent are test fixtures."
                ),
            )
            if response.status != "completed":
                raise RuntimeError(response.error_message or "The QA import failed")
            await db.exec(
                text(
                    """
                    update crm_inbound_enquiries
                    set
                        status = 'qualified',
                        confirmed_data = observed_data,
                        qualification = jsonb_build_object(
                            'source', 'owner_intelligence_qa',
                            'fixture', true
                        ),
                        updated_at = now()
                    where source_import_id = :import_id
                    """
                ),
                params={"import_id": response.id},
            )
            await db.commit()
            print(
                f"Created import {response.id}: {response.summary.imported} rows, "
                f"{response.summary.owner_matches} owner matches, "
                f"{response.summary.high_priority} high priority."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run(_arguments()))
