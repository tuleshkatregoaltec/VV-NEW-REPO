"""Import PropertyFinder listings from object storage into local demo tables.

This intentionally mirrors the supply/news demo shortcut. It samples the latest available
object-storage listing manifests into a local `demo_pf_listings` table so the frontend can render a
listings website-style page without building the production ingestion pipeline first.
"""

import argparse
import asyncio
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aioboto3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.postgres import close_postgres, get_postgres_engine

JSON_DECODER = json.JSONDecoder()
PF_LISTINGS_MANIFEST_PREFIX = "raw/source=pf_listings/manifests/"
PF_BASE_URL = "https://www.propertyfinder.ae"


def iter_json_objects(text_value: str) -> Iterable[dict[str, Any]]:
    """Read newline-ish JSON streams, tolerating embedded newlines in strings."""
    index = 0
    length = len(text_value)
    while index < length:
        while index < length and text_value[index].isspace():
            index += 1
        if index >= length:
            break
        obj, end = JSON_DECODER.raw_decode(text_value, index)
        if isinstance(obj, dict):
            yield obj
        index = end


def first_json_object(text_value: str) -> dict[str, Any] | None:
    return next(iter_json_objects(text_value), None)


def nested_dict(value: Any, *keys: str) -> dict[str, Any]:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def parse_int(value: Any) -> int | None:
    if value in (None, "", []):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def clip_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    if len(text_value) <= limit:
        return text_value
    return text_value[: limit - 3].rstrip() + "..."


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def listing_mode(row: dict[str, Any]) -> str | None:
    property_data = nested_dict(row, "raw_wrapper", "property")
    candidates = [
        property_data.get("offering_type"),
        row.get("details_path"),
        row.get("share_url"),
    ]
    for candidate in candidates:
        text_value = str(candidate or "").lower()
        if "sale" in text_value or "/buy/" in text_value or "for-sale" in text_value:
            return "sale"
        if "rent" in text_value or "for-rent" in text_value:
            return "rent"
    if row.get("category_id") in (1, 3):
        return "sale"
    if row.get("category_id") in (2, 4):
        return "rent"
    return None


def absolute_pf_url(value: Any) -> str | None:
    text_value = clip_text(value, 500)
    if not text_value:
        return None
    if text_value.startswith("http://") or text_value.startswith("https://"):
        return text_value
    if text_value.startswith("/"):
        return f"{PF_BASE_URL}{text_value}"
    return text_value


def contact_value(contact_options: list[Any], contact_type: str) -> str | None:
    for option in contact_options:
        if not isinstance(option, dict):
            continue
        if option.get("type") == contact_type and option.get("value"):
            return str(option["value"])
    return None


def normalize_party(value: Any, contact_options: list[Any] | None = None) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    contacts = contact_options or []
    return {
        "id": None if data.get("id") is None else str(data.get("id")),
        "name": clip_text(data.get("name"), 255),
        "email": clip_text(data.get("email") or contact_value(contacts, "email"), 255),
        "phone": clip_text(data.get("phone") or contact_value(contacts, "phone"), 80),
        "whatsapp": clip_text(contact_value(contacts, "whatsapp"), 80),
        "image_url": absolute_pf_url(data.get("image")),
        "logo_url": absolute_pf_url(data.get("logo")),
        "address": clip_text(data.get("address"), 500),
        "slug": clip_text(data.get("slug"), 255),
        "is_super_agent": data.get("is_super_agent"),
        "languages": [str(item) for item in as_list(data.get("languages")) if item],
    }


def normalize_images(value: Any) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for image in as_list(value):
        if not isinstance(image, dict):
            continue
        images.append(
            {
                "small_url": absolute_pf_url(image.get("small")),
                "medium_url": absolute_pf_url(image.get("medium")),
                "original_url": absolute_pf_url(image.get("original") or image.get("large")),
                "url": absolute_pf_url(image.get("url")),
                "label": clip_text(image.get("classification_label") or image.get("label"), 120),
            }
        )
    return images


def normalize_floorplans(value: Any) -> list[dict[str, Any]]:
    floorplans: list[dict[str, Any]] = []
    for floorplan in as_list(value):
        if not isinstance(floorplan, dict):
            continue
        floorplans.append(
            {
                "title": clip_text(floorplan.get("title") or floorplan.get("name"), 160),
                "image_url": absolute_pf_url(floorplan.get("image_url") or floorplan.get("url")),
                "area_sqft": parse_float(floorplan.get("area")),
                "floor_number": parse_int(floorplan.get("floor_number")),
                "unit_number": clip_text(floorplan.get("unit_number"), 80),
                "dimension": clip_text(floorplan.get("dimension"), 40),
            }
        )
    return floorplans


def location_names(row: dict[str, Any]) -> list[str]:
    names = [str(item) for item in as_list(row.get("listing_location_names")) if item]
    if names:
        return names
    names = []
    for item in as_list(row.get("location_tree")):
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def listing_record(row: dict[str, Any], source_manifest_key: str) -> dict[str, Any] | None:
    listing_id = clip_text(row.get("listing_id") or row.get("property_key"), 180)
    mode = listing_mode(row)
    if not listing_id or mode not in {"sale", "rent"}:
        return None

    property_data = nested_dict(row, "raw_wrapper", "property")
    contact_options = as_list(property_data.get("contact_options"))
    price = row.get("price") if isinstance(row.get("price"), dict) else property_data.get("price")
    price = price if isinstance(price, dict) else {}
    size = row.get("size") if isinstance(row.get("size"), dict) else property_data.get("size")
    size = size if isinstance(size, dict) else {}
    location = row.get("location") if isinstance(row.get("location"), dict) else {}
    coordinates = (
        location.get("coordinates") if isinstance(location.get("coordinates"), dict) else {}
    )
    names = location_names(row)
    images = normalize_images(row.get("images") or property_data.get("images"))
    floorplans = normalize_floorplans(property_data.get("floor_plans"))
    amenities = [
        str(item)
        for item in as_list(property_data.get("amenity_names") or property_data.get("amenities"))
        if item
    ]

    details_path = clip_text(row.get("details_path") or property_data.get("details_path"), 500)
    source_run_id = Path(source_manifest_key).stem

    return {
        "listing_id": listing_id,
        "listing_mode": mode,
        "category_id": parse_int(row.get("category_id") or property_data.get("category_id")),
        "property_type_id": parse_int(
            row.get("property_type_id") or property_data.get("property_type_id")
        ),
        "property_type": clip_text(
            property_data.get("property_type") or row.get("type") or row.get("property_type_id"),
            120,
        ),
        "title": clip_text(row.get("title") or property_data.get("title"), 500)
        or "Untitled listing",
        "description": property_data.get("description"),
        "reference": clip_text(row.get("reference") or property_data.get("reference"), 120),
        "details_path": details_path,
        "share_url": absolute_pf_url(row.get("share_url") or details_path),
        "price_value": parse_int(price.get("value")),
        "price_currency": clip_text(price.get("currency"), 12),
        "price_period": clip_text(price.get("period"), 40),
        "size_value": parse_float(size.get("value")),
        "size_unit": clip_text(size.get("unit"), 40),
        "bedrooms": clip_text(row.get("bedrooms") or property_data.get("bedrooms"), 40),
        "bathrooms": clip_text(row.get("bathrooms") or property_data.get("bathrooms"), 40),
        "city_name": clip_text(names[0] if len(names) > 0 else None, 160),
        "area_name": clip_text(names[1] if len(names) > 1 else None, 160),
        "subcommunity_name": clip_text(names[2] if len(names) > 2 else None, 160),
        "tower_name": clip_text(names[3] if len(names) > 3 else None, 160),
        "location_name": clip_text(location.get("full_name") or ", ".join(names), 500),
        "location_id": clip_text(location.get("id"), 80),
        "latitude": parse_float(row.get("latitude") or coordinates.get("lat")),
        "longitude": parse_float(row.get("longitude") or coordinates.get("lon")),
        "is_available": row.get("is_available") if row.get("is_available") is not None else None,
        "is_verified": row.get("is_verified") if row.get("is_verified") is not None else None,
        "is_featured": row.get("is_featured") if row.get("is_featured") is not None else None,
        "is_premium": row.get("is_premium") if row.get("is_premium") is not None else None,
        "listed_date": parse_datetime(property_data.get("listed_date")),
        "scraped_at": parse_datetime(row.get("scraped_at")),
        "agent": normalize_party(row.get("agent") or property_data.get("agent"), contact_options),
        "broker": normalize_party(row.get("broker") or property_data.get("broker")),
        "client": normalize_party(row.get("client") or property_data.get("client")),
        "images": images,
        "floorplans": floorplans,
        "amenities": amenities,
        "image_count": parse_int(property_data.get("images_count")) or len(images),
        "floorplan_count": len(floorplans),
        "furnished": clip_text(property_data.get("furnished"), 80),
        "completion_status": clip_text(property_data.get("completion_status"), 120),
        "rera": clip_text(property_data.get("rera"), 120),
        "number_of_cheques": parse_int(property_data.get("number_of_cheques")),
        "payment_method": [str(item) for item in as_list(property_data.get("payment_method"))],
        "video_url": absolute_pf_url(property_data.get("video_url")),
        "view_360_url": absolute_pf_url(property_data.get("view_360")),
        "source_manifest_key": source_manifest_key,
        "source_run_id": source_run_id,
    }


async def list_objects(s3: Any, prefix: str) -> list[dict[str, Any]]:
    paginator = s3.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    async for page in paginator.paginate(
        Bucket=settings.OBJECT_STORAGE_BUCKET,
        Prefix=prefix,
        PaginationConfig={"PageSize": 1000},
    ):
        objects.extend(page.get("Contents", []))
    return objects


async def read_text_object(s3: Any, key: str) -> str:
    response = await s3.get_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=key)
    return (await response["Body"].read()).decode("utf-8", errors="replace")


async def read_text_prefix(s3: Any, key: str, byte_count: int = 500_000) -> str:
    response = await s3.get_object(
        Bucket=settings.OBJECT_STORAGE_BUCKET,
        Key=key,
        Range=f"bytes=0-{byte_count - 1}",
    )
    return (await response["Body"].read()).decode("utf-8", errors="replace")


async def load_manifests(s3: Any) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for obj in await list_objects(s3, PF_LISTINGS_MANIFEST_PREFIX):
        if not obj["Key"].endswith(".json") or obj.get("Size", 0) <= 0:
            continue
        manifest = json.loads(await read_text_object(s3, obj["Key"]))
        manifest["s3_key"] = obj["Key"]
        manifest["last_modified"] = obj.get("LastModified")
        manifests.append(manifest)
    return sorted(
        manifests,
        key=lambda item: item.get("last_modified") or item.get("created_at") or "",
        reverse=True,
    )


def properties_file(manifest: dict[str, Any]) -> dict[str, Any] | None:
    for file in manifest.get("files", []):
        if file.get("path") == "pf_listing_properties.jsonl" and file.get("size_bytes", 0) > 0:
            return file
    return None


async def sample_manifest_mode(s3: Any, file: dict[str, Any]) -> str | None:
    sample = first_json_object(await read_text_prefix(s3, file["s3_key"]))
    return listing_mode(sample) if sample else None


async def collect_listing_records(max_per_mode: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    session = aioboto3.Session()
    object_storage_client_kwargs = {
        "aws_access_key_id": settings.OBJECT_STORAGE_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.OBJECT_STORAGE_SECRET_ACCESS_KEY,
        "region_name": settings.OBJECT_STORAGE_REGION or "auto",
    }
    if settings.OBJECT_STORAGE_ENDPOINT_URL:
        object_storage_client_kwargs["endpoint_url"] = str(settings.OBJECT_STORAGE_ENDPOINT_URL)

    records: list[dict[str, Any]] = []
    counts = {"sale": 0, "rent": 0}
    seen_listing_ids: set[str] = set()

    async with session.client("s3", **object_storage_client_kwargs) as s3:
        manifests = await load_manifests(s3)
        for manifest in manifests:
            file = properties_file(manifest)
            if not file:
                continue
            sample_mode = await sample_manifest_mode(s3, file)
            if max_per_mode > 0 and sample_mode in counts and counts[sample_mode] >= max_per_mode:
                continue

            text_value = await read_text_object(s3, file["s3_key"])
            imported_from_file = 0
            for row in iter_json_objects(text_value):
                record = listing_record(row, manifest["s3_key"])
                if not record:
                    continue
                mode = record["listing_mode"]
                if max_per_mode > 0 and counts[mode] >= max_per_mode:
                    continue
                listing_id = record["listing_id"]
                if listing_id in seen_listing_ids:
                    continue
                seen_listing_ids.add(listing_id)
                records.append(record)
                counts[mode] += 1
                imported_from_file += 1

            print(
                f"sampled {imported_from_file} rows from {file['s3_key']} "
                f"(sale={counts['sale']} rent={counts['rent']})"
            )
            if max_per_mode > 0 and all(counts[mode] >= max_per_mode for mode in counts):
                break

    return records, counts


async def create_demo_tables(db: AsyncSession, reset: bool) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS demo_pf_listings (
                listing_id TEXT PRIMARY KEY,
                listing_mode TEXT NOT NULL,
                category_id INTEGER,
                property_type_id INTEGER,
                property_type TEXT,
                title TEXT NOT NULL,
                description TEXT,
                reference TEXT,
                details_path TEXT,
                share_url TEXT,
                price_value BIGINT,
                price_currency TEXT,
                price_period TEXT,
                size_value DOUBLE PRECISION,
                size_unit TEXT,
                bedrooms TEXT,
                bathrooms TEXT,
                city_name TEXT,
                area_name TEXT,
                subcommunity_name TEXT,
                tower_name TEXT,
                location_name TEXT,
                location_id TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                is_available BOOLEAN,
                is_verified BOOLEAN,
                is_featured BOOLEAN,
                is_premium BOOLEAN,
                listed_date TIMESTAMPTZ,
                scraped_at TIMESTAMPTZ,
                agent JSONB NOT NULL DEFAULT '{}'::jsonb,
                broker JSONB NOT NULL DEFAULT '{}'::jsonb,
                client JSONB NOT NULL DEFAULT '{}'::jsonb,
                images JSONB NOT NULL DEFAULT '[]'::jsonb,
                floorplans JSONB NOT NULL DEFAULT '[]'::jsonb,
                amenities JSONB NOT NULL DEFAULT '[]'::jsonb,
                image_count INTEGER NOT NULL DEFAULT 0,
                floorplan_count INTEGER NOT NULL DEFAULT 0,
                furnished TEXT,
                completion_status TEXT,
                rera TEXT,
                number_of_cheques INTEGER,
                payment_method JSONB NOT NULL DEFAULT '[]'::jsonb,
                video_url TEXT,
                view_360_url TEXT,
                source_manifest_key TEXT,
                source_run_id TEXT,
                imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE demo_pf_listings
                ALTER COLUMN price_value TYPE BIGINT
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_demo_pf_listings_mode_area
                ON demo_pf_listings(listing_mode, area_name)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_demo_pf_listings_mode_type
                ON demo_pf_listings(listing_mode, property_type)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_demo_pf_listings_mode_price
                ON demo_pf_listings(listing_mode, price_value)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_demo_pf_listings_listed_date
                ON demo_pf_listings(listed_date DESC)
            """
        )
    )
    if reset:
        await db.execute(text("TRUNCATE demo_pf_listings"))
    await db.commit()


async def upsert_listings(db: AsyncSession, records: list[dict[str, Any]]) -> None:
    sql = text(
        """
        INSERT INTO demo_pf_listings (
            listing_id, listing_mode, category_id, property_type_id, property_type,
            title, description, reference, details_path, share_url, price_value,
            price_currency, price_period, size_value, size_unit, bedrooms, bathrooms,
            city_name, area_name, subcommunity_name, tower_name, location_name,
            location_id, latitude, longitude, is_available, is_verified, is_featured,
            is_premium, listed_date, scraped_at, agent, broker, client, images,
            floorplans, amenities, image_count, floorplan_count, furnished,
            completion_status, rera, number_of_cheques, payment_method, video_url,
            view_360_url, source_manifest_key, source_run_id
        ) VALUES (
            :listing_id, :listing_mode, :category_id, :property_type_id, :property_type,
            :title, :description, :reference, :details_path, :share_url, :price_value,
            :price_currency, :price_period, :size_value, :size_unit, :bedrooms, :bathrooms,
            :city_name, :area_name, :subcommunity_name, :tower_name, :location_name,
            :location_id, :latitude, :longitude, :is_available, :is_verified, :is_featured,
            :is_premium, :listed_date, :scraped_at, CAST(:agent AS jsonb),
            CAST(:broker AS jsonb), CAST(:client AS jsonb), CAST(:images AS jsonb),
            CAST(:floorplans AS jsonb), CAST(:amenities AS jsonb), :image_count,
            :floorplan_count, :furnished, :completion_status, :rera, :number_of_cheques,
            CAST(:payment_method AS jsonb), :video_url, :view_360_url, :source_manifest_key,
            :source_run_id
        )
        ON CONFLICT (listing_id) DO UPDATE SET
            listing_mode = EXCLUDED.listing_mode,
            category_id = EXCLUDED.category_id,
            property_type_id = EXCLUDED.property_type_id,
            property_type = EXCLUDED.property_type,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            reference = EXCLUDED.reference,
            details_path = EXCLUDED.details_path,
            share_url = EXCLUDED.share_url,
            price_value = EXCLUDED.price_value,
            price_currency = EXCLUDED.price_currency,
            price_period = EXCLUDED.price_period,
            size_value = EXCLUDED.size_value,
            size_unit = EXCLUDED.size_unit,
            bedrooms = EXCLUDED.bedrooms,
            bathrooms = EXCLUDED.bathrooms,
            city_name = EXCLUDED.city_name,
            area_name = EXCLUDED.area_name,
            subcommunity_name = EXCLUDED.subcommunity_name,
            tower_name = EXCLUDED.tower_name,
            location_name = EXCLUDED.location_name,
            location_id = EXCLUDED.location_id,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            is_available = EXCLUDED.is_available,
            is_verified = EXCLUDED.is_verified,
            is_featured = EXCLUDED.is_featured,
            is_premium = EXCLUDED.is_premium,
            listed_date = EXCLUDED.listed_date,
            scraped_at = EXCLUDED.scraped_at,
            agent = EXCLUDED.agent,
            broker = EXCLUDED.broker,
            client = EXCLUDED.client,
            images = EXCLUDED.images,
            floorplans = EXCLUDED.floorplans,
            amenities = EXCLUDED.amenities,
            image_count = EXCLUDED.image_count,
            floorplan_count = EXCLUDED.floorplan_count,
            furnished = EXCLUDED.furnished,
            completion_status = EXCLUDED.completion_status,
            rera = EXCLUDED.rera,
            number_of_cheques = EXCLUDED.number_of_cheques,
            payment_method = EXCLUDED.payment_method,
            video_url = EXCLUDED.video_url,
            view_360_url = EXCLUDED.view_360_url,
            source_manifest_key = EXCLUDED.source_manifest_key,
            source_run_id = EXCLUDED.source_run_id,
            imported_at = now()
        """
    )

    prepared = []
    for record in records:
        row = record.copy()
        for json_field in [
            "agent",
            "broker",
            "client",
            "images",
            "floorplans",
            "amenities",
            "payment_method",
        ]:
            row[json_field] = json.dumps(row[json_field], ensure_ascii=False)
        prepared.append(row)

    for index in range(0, len(prepared), 1000):
        await db.execute(sql, prepared[index : index + 1000])
    await db.commit()


async def import_pf_listings_demo(reset: bool, max_per_mode: int) -> None:
    records, counts = await collect_listing_records(max_per_mode=max_per_mode)
    session_factory = async_sessionmaker(
        get_postgres_engine(), class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as db:
        await create_demo_tables(db, reset=reset)
        await upsert_listings(db, records)
    await close_postgres()
    print(
        f"imported {len(records)} PropertyFinder listing rows "
        f"(sale={counts['sale']} rent={counts['rent']})"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-reset", action="store_true", help="Do not truncate demo tables first")
    parser.add_argument(
        "--max-per-mode",
        type=int,
        default=7500,
        help="Maximum imported rows per sale/rent mode. Use 0 to import every discovered row.",
    )
    args = parser.parse_args()
    asyncio.run(import_pf_listings_demo(reset=not args.no_reset, max_per_mode=args.max_per_mode))


if __name__ == "__main__":
    main()
