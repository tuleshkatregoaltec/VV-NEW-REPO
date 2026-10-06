"""Normalize unit-bearing rows from the DXB sales backfill."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from holocron.sources.dxbi.rental_events import canonical_area_name

_AGENT_PREFIX = re.compile(r"^(?:Buyer's|Seller's)\s+agent\s+", re.IGNORECASE)
_LOCATION_SUFFIX = re.compile(
    r"\s+(?P<status>Offplan|Ready)\s+(?P<property_type>.+?),\s*Floor\b.*$",
    re.IGNORECASE,
)
_BEDROOMS = re.compile(r"(?P<count>\d+)\s*Beds?\b", re.IGNORECASE)
_SIZE = re.compile(r"(?P<size>[\d,]+(?:\.\d+)?)\s*sqft", re.IGNORECASE)
_PRICE = re.compile(r"AED\s*(?P<price>[\d,]+)", re.IGNORECASE)
_PRICE_PER_SQFT = re.compile(
    r"AED\s*(?P<price>[\d,]+(?:\.\d+)?)\s*/sqft",
    re.IGNORECASE,
)
_CAPITAL_GAIN = re.compile(r"\((?P<sign>[+-])(?P<value>\d+(?:\.\d+)?)%\)")
_LTV = re.compile(r"(?<![\w-])(?P<value>\d+(?:\.\d+)?)%\s*LTV", re.IGNORECASE)
_BALCONY = re.compile(r"Balcony\s+(?P<size>[\d,]+(?:\.\d+)?)\s*sqft", re.IGNORECASE)
_BUA = re.compile(r"[•·]\s*(?P<size>[\d,]+(?:\.\d+)?)\s*sqft\s*BUA", re.IGNORECASE)
_SOLD_BY = re.compile(
    r"\d{4}\s+(?P<seller>Developer|Individual)"
    r"(?:\s+\((?P<count>\d+)\s+Times?\))?",
    re.IGNORECASE,
)
_SALE_DATE = re.compile(
    r"(?P<day>\d{1,2}),\s*(?P<month>[A-Za-z]{3})\s*(?P<year>\d{4})"
)
_UNIT_NUMBER = re.compile(r"\bNo\.\s*(?P<unit>[A-Za-z0-9][A-Za-z0-9/-]*)", re.IGNORECASE)


def normalize_sales_row(payload: dict[str, Any], *, source_file: str = "") -> dict[str, Any] | None:
    unit_number = str(payload.get("unit_number") or "").strip()
    if not unit_number or unit_number.lower() == "u-hidden":
        return None

    raw_location = str(payload.get("location_text") or "").strip()
    agent_side = (
        "buyer"
        if raw_location.lower().startswith("buyer's agent")
        else "seller"
        if raw_location.lower().startswith("seller's agent")
        else ""
    )
    location = _AGENT_PREFIX.sub("", raw_location)
    suffix = _LOCATION_SUFFIX.search(location)
    property_type = ""
    market_status = ""
    if suffix:
        property_type = suffix.group("property_type").strip()
        market_status = suffix.group("status").strip().title()
        location = location[: suffix.start()].strip(" ,")

    parts = [part.strip() for part in location.split(",") if part.strip()]
    building_name = parts[0] if parts else ""
    area_name = canonical_area_name(parts[-1]) if len(parts) >= 2 else ""
    project_name = ", ".join(parts[1:-1]) if len(parts) >= 3 else ""
    specs = str(payload.get("specs_text") or "")
    bedrooms = _bedroom_label(specs)
    size_match = _SIZE.search(specs)
    amount_text = str(payload.get("amount_text") or "")
    date_text = str(payload.get("date_text") or "")
    price_match = _PRICE.search(amount_text)
    price_per_sqft_match = _PRICE_PER_SQFT.search(amount_text)
    capital_gain_match = _CAPITAL_GAIN.search(amount_text)
    ltv_match = _LTV.search(amount_text)
    balcony_match = _BALCONY.search(specs)
    bua_match = _BUA.search(specs)
    sold_by_match = _SOLD_BY.search(date_text)
    transaction_date = _parse_date(date_text)
    if not building_name or not transaction_date or not size_match or not price_match:
        return None

    size_sqft = float(size_match.group("size").replace(",", ""))
    sale_amount = int(price_match.group("price").replace(",", ""))
    capital_gain_pct = None
    if capital_gain_match:
        direction = -1 if capital_gain_match.group("sign") == "-" else 1
        capital_gain_pct = direction * float(capital_gain_match.group("value"))
    detail_url = str(payload.get("detail_url") or "").strip()
    sale_key = _digest(
        detail_url
        or "|".join(
            (
                transaction_date.isoformat(),
                unit_number,
                building_name,
                str(sale_amount),
                f"{size_sqft:.1f}",
            )
        )
    )
    return {
        "sale_key": sale_key,
        "transaction_date": transaction_date,
        "unit_number": unit_number,
        "building_name": building_name,
        "building_key": location_key(building_name),
        "project_name": project_name,
        "area_name": area_name,
        "area_key": location_key(area_name),
        "address_normalization_version": 5,
        "property_type": property_type,
        "market_status": market_status,
        "bedrooms": bedrooms,
        "size_sqft": size_sqft,
        "size_key": round(size_sqft),
        "built_up_area_sqft": (
            float(bua_match.group("size").replace(",", "")) if bua_match else None
        ),
        "balcony_sqft": (
            float(balcony_match.group("size").replace(",", "")) if balcony_match else None
        ),
        "sale_amount_aed": sale_amount,
        "price_per_sqft_aed": (
            float(price_per_sqft_match.group("price").replace(",", ""))
            if price_per_sqft_match
            else None
        ),
        "capital_gain_pct": capital_gain_pct,
        "ltv_pct": float(ltv_match.group("value")) if ltv_match else None,
        "seller_type": sold_by_match.group("seller").title() if sold_by_match else "",
        "seller_transaction_count": (
            int(sold_by_match.group("count"))
            if sold_by_match and sold_by_match.group("count")
            else None
        ),
        "agent_side": agent_side,
        "detail_url": detail_url,
        "source_file": source_file,
    }


def compact_payload(line: str) -> dict[str, Any]:
    """Return the normalized input shape from old compact or current raw rows."""
    prefix = line.split(',"columns":', 1)[0]
    import json

    compact = json.loads(f"{prefix}}}")
    if "unit_number" in compact:
        return compact

    record = json.loads(line)
    columns = {
        str(column.get("id") or ""): column
        for column in record.get("columns") or []
        if isinstance(column, dict)
    }
    location_text = str(columns.get("PATH_NAME", {}).get("text") or "")
    unit_match = _UNIT_NUMBER.search(location_text)
    detail_url = ""
    for column in columns.values():
        for link in column.get("links") or []:
            candidate = str(link.get("href") or "")
            if "/sold/" in candidate:
                detail_url = candidate
                break
        if detail_url:
            break
    return {
        "unit_number": unit_match.group("unit") if unit_match else "",
        "location_text": location_text,
        "amount_text": str(columns.get("TOTAL_PRICE", {}).get("text") or ""),
        "specs_text": str(columns.get("BEDROOM", {}).get("text") or ""),
        "date_text": str(columns.get("SOLD_BY", {}).get("text") or ""),
        "detail_url": detail_url,
    }


def location_key(value: str) -> str:
    normalized = value.lower()
    replacements = {
        "jumeriah": "jumeirah",
        "residences": "residence",
        "apartments": "apartment",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _bedroom_label(value: str) -> str:
    if re.search(r"\bStudio\b", value, re.IGNORECASE):
        return "Studio"
    match = _BEDROOMS.search(value)
    return f"{match.group('count')} Bed" if match else ""


def _parse_date(value: str) -> date | None:
    match = _SALE_DATE.search(value)
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group('day')} {match.group('month')} {match.group('year')}", "%d %b %Y"
        ).date()
    except ValueError:
        return None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def source_name(path: Path) -> str:
    return path.name
