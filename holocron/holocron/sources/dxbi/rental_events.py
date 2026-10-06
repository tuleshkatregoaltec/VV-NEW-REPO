"""Normalize the DXB rental backfill JSONL format into CRM lease events."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from holocron.sources.dxbi.rental_coverage import canonical_json, raw_row_fingerprint

_PROPERTY_TYPES = (
    "Hotel Apartment",
    "Commercial",
    "Apartment",
    "Villa",
    "Townhouse",
    "Office",
    "Shop",
    "Warehouse",
    "Land",
)
_DATE_RANGE = re.compile(
    r"(?P<start>\d{1,2} [A-Za-z]{3}, \d{4})\s*-\s*"
    r"(?P<end>\d{1,2} [A-Za-z]{3}, \d{4})"
)
_SIZE = re.compile(r"(?P<size>[\d,]+(?:\.\d+)?)\s*sqft", re.IGNORECASE)
_BEDROOMS = re.compile(r"(?P<bedrooms>Studio|\d+\s*Bed)", re.IGNORECASE)
_TERM_MONTHS = re.compile(r"(?P<months>\d+(?:\.\d+)?)\s*Months?\b", re.IGNORECASE)
_FIRST_NUMBER = re.compile(r"(?P<value>[\d,]+(?:\.\d+)?)")
_PURCHASE_PRICE = re.compile(r"AED\s*(?P<value>[\d,.]+)\s*(?P<suffix>[KMB]?)", re.IGNORECASE)
_VISIBLE_UNIT_NUMBER = re.compile(r"\b(?:Unit\s+)?No\.\s*(?P<value>[^,]+)", re.IGNORECASE)
_SOURCE_ID_KEYS = re.compile(r"(?:contract|transaction|record|source)[_-]?id", re.IGNORECASE)
_SOURCE_ID_LINK = re.compile(
    r"(?:/|[?&])(?:rent(?:al)?|contract|transaction)(?:/|-|=)(?P<value>[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_AREA_ACRONYM = re.compile(r"\s*\((?:JVC|JLT|JVT|DSO|IMPZ|JBR|TECOM|DIP)\)\s*$", re.IGNORECASE)
_AREA_ALIASES = {
    "jvc": "Jumeirah Village Circle",
    "jumeirah village circle": "Jumeirah Village Circle",
    "jlt": "Jumeirah Lake Towers",
    "jumeirah lake towers": "Jumeirah Lake Towers",
    "jvt": "Jumeirah Village Triangle",
    "jumeirah village triangle": "Jumeirah Village Triangle",
    "dso": "Dubai Silicon Oasis",
    "dubai silicon oasis": "Dubai Silicon Oasis",
    "impz": "Dubai Production City",
    "international media production zone": "Dubai Production City",
    "dubai production city": "Dubai Production City",
    "jbr": "Jumeirah Beach Residence",
    "jumeirah beach residence": "Jumeirah Beach Residence",
    "tecom": "Barsha Heights",
    "barsha heights": "Barsha Heights",
    "dip": "Dubai Investment Park",
    "dubai investment park": "Dubai Investment Park",
    "dubai international financial center": "DIFC",
    "difc": "DIFC",
    "mirdif": "Mirdif",
    "dubai hills": "Dubai Hills Estate",
    "dubai hills estate": "Dubai Hills Estate",
    "al barshaa south 1": "Al Barsha South 1",
    "al barshaa south 3": "Al Barsha South 3",
    "al goze industrial 1": "Al Quoz Industrial 1",
    "al goze industrial 3": "Al Quoz Industrial 3",
    "al goze industrial 4": "Al Quoz Industrial 4",
    "al saffa 1": "Al Safa 1",
    "al saffa 2": "Al Safa 2",
    "al safouh 1": "Al Sufouh 1",
    "al safouh 2": "Al Sufouh 2",
    "al thanayah 4": "Al Thanyah 4",
    "dubai creek harbour (the lagoons": "Dubai Creek Harbour",
    "dubai south (dubai world central": "Dubai South",
    "dubai maritime city": "Maritime City",
    "festival city": "Dubai Festival City",
    "the greens": "Greens",
    "hessayan 1": "Hessyan 1",
    "um suqaim 1": "Umm Suqeim 1",
    "um suqaim 2": "Umm Suqeim 2",
    "um suqaim 3": "Umm Suqeim 3",
    "za'abeel 1": "Zabeel 1",
    "zaabeel 1": "Zabeel 1",
    "zaabeel 2": "Zabeel 2",
}
_AREA_ORDINALS = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
}


@dataclass(frozen=True)
class RentalNormalizationResult:
    events: list[dict[str, Any]]
    quarantined: list[dict[str, Any]]
    raw_rows: int
    normalized_rows: int
    unique_source_rows: int
    profile_overlap: int


def normalize_rental_row(
    payload: dict[str, Any],
    *,
    source_file: str = "",
    source_account: str = "",
    occurrence_index: int = 1,
) -> dict[str, Any] | None:
    columns = {
        str(column.get("id") or ""): str(column.get("text") or "").strip()
        for column in payload.get("columns") or []
    }
    location_text = columns.get("PATH_NAME", "")
    specs_text = columns.get("PROP_SIZES", "")
    price_text = columns.get("TOTAL_PRICES", "")
    duration_text = columns.get("START_DATE", "")
    if not location_text or not duration_text:
        return None

    date_match = _DATE_RANGE.search(duration_text)
    if not date_match:
        return None
    lease_start = datetime.strptime(date_match.group("start"), "%d %b, %Y").date()
    lease_end = datetime.strptime(date_match.group("end"), "%d %b, %Y").date()
    if lease_end < lease_start:
        return None

    location_name, building_name, project_name, area_name, property_type = _parse_location(
        location_text
    )
    bedrooms_match = _BEDROOMS.search(specs_text)
    size_match = _SIZE.search(specs_text)
    bedrooms = bedrooms_match.group("bedrooms").title() if bedrooms_match else ""
    size_sqft = float(size_match.group("size").replace(",", "")) if size_match else 0.0
    contract_amount_aed = _first_amount(price_text)
    contract_term_days = (lease_end - lease_start).days + 1
    term_match = _TERM_MONTHS.search(duration_text)
    contract_term_months = float(term_match.group("months")) if term_match else 0.0
    annual_rent_aed = _annualize_contract_amount(
        contract_amount_aed,
        contract_term_days,
        contract_term_months=contract_term_months,
    )
    purchase_price_aed = _purchase_price(columns.get("PURCHASE_PRICE", ""))
    contract_state = "Renewed" if re.search(r"\bRenewed\b", price_text, re.IGNORECASE) else "New"

    raw_shard = payload.get("shard")
    shard: dict[str, Any] = raw_shard if isinstance(raw_shard, dict) else {}
    shard_date = (
        _safe_date(str(shard.get("date") or payload.get("shard_start_date") or "")) or lease_start
    )
    scraped_at = _safe_datetime(str(payload.get("scraped_at") or ""))
    unit_number = extract_unit_number(payload)
    source_contract_id = extract_source_contract_id(payload)
    fingerprint = str(payload.get("raw_row_fingerprint") or raw_row_fingerprint(payload))
    raw_profile = payload.get("filter_profile")
    profile: dict[str, Any] = raw_profile if isinstance(raw_profile, dict) else {}
    raw_source_location = payload.get("source_location")
    source_location: dict[str, Any] = (
        raw_source_location if isinstance(raw_source_location, dict) else {}
    )
    profile_id = str(profile.get("id") or payload.get("filter_profile_id") or "default")
    source_location_id = str(source_location.get("id") or payload.get("source_location_id") or "1")
    source_location_text = str(
        source_location.get("text") or payload.get("source_location_text") or "Dubai"
    )
    source_location_slug = str(
        source_location.get("slug") or payload.get("source_location_slug") or "dubai"
    )
    report_type = str(payload.get("report_type") or payload.get("transaction_type") or "rentals")
    configuration_hash = str(payload.get("configuration_hash") or "legacy")
    source_account = str(payload.get("source_account") or "") or source_account
    source_run_id = str(payload.get("source_run_id") or source_run_id_from_path(Path(source_file)))

    cohort_parts = (
        _key_text(unit_number),
        _key_text(building_name or location_name),
        _key_text(project_name),
        _key_text(area_name),
        _key_text(property_type),
        _key_text(bedrooms),
        f"{size_sqft:.1f}",
    )
    unit_cohort_key = _digest(cohort_parts)
    candidate_parts = cohort_parts + (
        str(int(round(purchase_price_aed / 1_000) * 1_000)) if purchase_price_aed else "unknown",
    )
    unit_candidate_key = _digest(candidate_parts)
    immutable_contract_parts = (
        "unit-contract",
        _key_text(unit_number),
        _key_text(location_name),
        _key_text(property_type),
        _key_text(bedrooms),
        f"{size_sqft:.3f}",
        lease_start.isoformat(),
        lease_end.isoformat(),
        str(contract_amount_aed),
        contract_state.lower(),
    )
    contract_base_key = _digest(
        ("source-contract", _key_text(source_contract_id))
        if source_contract_id
        else immutable_contract_parts
    )
    contract_key = _digest((contract_base_key, str(occurrence_index)))
    raw_attributes_json = canonical_json(
        {
            "row": payload.get("row_attributes") or {},
            "hidden": payload.get("hidden_attributes") or {},
            "cells": {
                str(column.get("id") or ""): column.get("attributes") or {}
                for column in payload.get("columns") or []
                if column.get("attributes")
            },
        }
    )

    return {
        "contract_key": contract_key,
        "event_key": contract_key,
        "source_contract_id": source_contract_id,
        "unit_number": unit_number,
        "occurrence_index": occurrence_index,
        "unit_candidate_key": unit_candidate_key,
        "unit_cohort_key": unit_cohort_key,
        "location_name": location_name,
        "building_name": building_name,
        "project_name": project_name,
        "area_name": area_name,
        "property_type": property_type,
        "bedrooms": bedrooms,
        "size_sqft": size_sqft,
        "contract_amount_aed": contract_amount_aed,
        "contract_term_days": contract_term_days,
        "contract_term_months": contract_term_months,
        "annual_rent_aed": annual_rent_aed,
        "rent_normalization_version": 2,
        "address_normalization_version": 5,
        "purchase_price_aed": purchase_price_aed,
        "lease_start": lease_start,
        "lease_end": lease_end,
        "contract_state": contract_state,
        "source_account": source_account,
        "source_run_id": source_run_id,
        "report_type": report_type,
        "filter_profile_id": profile_id,
        "source_location_id": source_location_id,
        "source_location_text": source_location_text,
        "source_location_slug": source_location_slug,
        "configuration_hash": configuration_hash,
        "raw_row_fingerprint": fingerprint,
        "raw_attributes_json": raw_attributes_json,
        "source_shard_date": shard_date,
        "source_file": source_file,
        "scraped_at": scraped_at,
        "_contract_base_key": contract_base_key,
    }


def legacy_rental_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep the active v1 identities stable until the validated v2 cutover."""
    cohort_parts = (
        _key_text(event["building_name"] or event["location_name"]),
        _key_text(event["project_name"]),
        _key_text(event["area_name"]),
        _key_text(event["property_type"]),
        _key_text(event["bedrooms"]),
        f"{event['size_sqft']:.1f}",
    )
    purchase_price = event["purchase_price_aed"]
    candidate_parts = cohort_parts + (
        str(int(round(purchase_price / 1_000) * 1_000)) if purchase_price else "unknown",
    )
    return {
        **event,
        "unit_cohort_key": _digest(cohort_parts),
        "unit_candidate_key": _digest(candidate_parts),
        "event_key": _digest(
            candidate_parts
            + (
                event["lease_start"].isoformat(),
                event["lease_end"].isoformat(),
                str(event["contract_amount_aed"]),
                event["contract_state"].lower(),
            )
        ),
    }


def normalize_rental_rows(
    payloads: list[tuple[dict[str, Any], str, str]],
) -> RentalNormalizationResult:
    """Normalize a day's profile/location union without collapsing real duplicate rows.

    Each tuple contains ``(payload, source_file, fallback_account)``. Rows repeated by
    overlapping profiles or locations share an occurrence slot, while repeated rows
    within one source collection receive stable occurrence indexes.
    """
    normalized: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for input_index, (payload, source_file, fallback_account) in enumerate(payloads):
        try:
            event = normalize_rental_row(
                payload,
                source_file=source_file,
                source_account=fallback_account,
            )
        except (TypeError, ValueError) as exc:
            event = None
            reason = f"{type(exc).__name__}: {exc}"
        else:
            reason = "missing location/date or malformed lease period" if event is None else ""
        if event is None:
            quarantined.append(
                {
                    "reason": reason,
                    "source_file": source_file,
                    "payload": payload,
                }
            )
            continue
        event["_input_index"] = input_index
        normalized.append(event)

    by_contract: dict[str, dict[tuple[str, ...], list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    raw_multiplicity: dict[str, dict[tuple[str, ...], int]] = defaultdict(lambda: defaultdict(int))
    for event in normalized:
        scope = (
            event["source_run_id"],
            event["source_account"],
            event["filter_profile_id"],
            event["source_location_id"],
            event["source_shard_date"].isoformat(),
            event["configuration_hash"],
        )
        by_contract[event["_contract_base_key"]][scope].append(event)
        raw_multiplicity[event["raw_row_fingerprint"]][scope] += 1

    events: list[dict[str, Any]] = []
    for contract_base_key in sorted(by_contract):
        scoped = by_contract[contract_base_key]
        ordered_scopes: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for scope, rows in scoped.items():
            ordered_scopes[scope] = sorted(
                rows,
                key=lambda row: (
                    row["raw_row_fingerprint"],
                    row["source_file"],
                    row["_input_index"],
                ),
            )
        occurrence_count = max(len(rows) for rows in ordered_scopes.values())
        for index in range(occurrence_count):
            candidates = [rows[index] for rows in ordered_scopes.values() if index < len(rows)]
            representative = min(
                candidates,
                key=lambda row: (
                    row["filter_profile_id"] != "broad",
                    row["source_location_id"] != "1",
                    row["filter_profile_id"],
                    row["source_location_id"],
                    row["raw_row_fingerprint"],
                    row["source_file"],
                ),
            ).copy()
            occurrence_index = index + 1
            contract_key = _digest((contract_base_key, str(occurrence_index)))
            representative["occurrence_index"] = occurrence_index
            representative["contract_key"] = contract_key
            representative["event_key"] = contract_key
            representative.pop("_contract_base_key", None)
            representative.pop("_input_index", None)
            events.append(representative)

    events = merge_rental_snapshots(events)
    unique_source_rows = sum(
        max(scope_counts.values()) for scope_counts in raw_multiplicity.values()
    )
    return RentalNormalizationResult(
        events=events,
        quarantined=quarantined,
        raw_rows=len(payloads),
        normalized_rows=len(normalized),
        unique_source_rows=unique_source_rows,
        profile_overlap=max(0, len(normalized) - len(events)),
    )


def merge_rental_snapshots(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconcile snapshots when an older collection concealed the unit number.

    Identified units remain distinct. Unidentified occurrences are retained only
    to preserve the largest observed multiplicity within an exact lease cohort;
    they are never assigned to a guessed unit or added on top of a fuller snapshot.
    """

    def cohort_key(event: dict[str, Any]) -> tuple:
        return (
            event["source_contract_id"],
            _key_text(event["location_name"]),
            _key_text(event["property_type"]),
            _key_text(event["bedrooms"]),
            f"{event['size_sqft']:.3f}",
            event["lease_start"],
            event["lease_end"],
            event["contract_amount_aed"],
            event["contract_state"].lower(),
        )

    def version(event: dict[str, Any]) -> tuple:
        scraped_at = event["scraped_at"]
        if scraped_at.tzinfo is None:
            scraped_at = scraped_at.replace(tzinfo=timezone.utc)
        return bool(event["unit_number"]), scraped_at

    # Count each snapshot before selecting representatives across snapshots.
    # Otherwise a repeated known unit can move to another run and make a real
    # unidentified occurrence from its original run disappear.
    scoped_keys: dict[tuple, dict[tuple, set[str]]] = defaultdict(lambda: defaultdict(set))
    observed_sizes: dict[tuple, int] = defaultdict(int)
    by_key: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event["contract_key"]
        scope = (
            event["source_run_id"],
            event["source_account"],
            event["filter_profile_id"],
            event["source_location_id"],
            event["source_shard_date"],
            event["configuration_hash"],
        )
        cohort = cohort_key(event)
        scoped_keys[cohort][scope].add(key)
        observed_sizes[cohort] = max(
            observed_sizes[cohort], int(event.get("source_cohort_size", 0))
        )
        previous = by_key.get(key)
        if previous is None or version(event) >= version(previous):
            by_key[key] = event
    cohorts: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for event in by_key.values():
        cohorts[cohort_key(event)].append(event)
    merged: list[dict[str, Any]] = []
    for cohort, rows in cohorts.items():
        cohort_size = max(
            max(map(len, scoped_keys[cohort].values())),
            observed_sizes[cohort],
        )
        # Persist the observed multiplicity so incremental merges are idempotent
        # even after a more recent snapshot supplies the representative row.
        rows = [{**row, "source_cohort_size": cohort_size} for row in rows]
        known = [row for row in rows if row["unit_number"]]
        unknown = [row for row in rows if not row["unit_number"]]
        if not known or not unknown:
            merged.extend(rows)
            continue
        remainder = max(0, cohort_size - len(known))
        merged.extend(known)
        merged.extend(
            sorted(unknown, key=lambda row: (row["occurrence_index"], row["contract_key"]))[
                :remainder
            ]
        )
    return merged


def extract_unit_number(payload: dict[str, Any]) -> str:
    direct = _clean_unit_number(str(payload.get("unit_number") or ""))
    if direct:
        return direct
    for column in payload.get("columns") or []:
        column_id = str(column.get("id") or "").upper()
        if column_id in {"UNIT", "UNIT_NO", "UNIT_NUMBER", "PROPERTY_NO"}:
            value = _clean_unit_number(str(column.get("text") or ""))
            if value:
                return value
    location_text = next(
        (
            str(column.get("text") or "")
            for column in payload.get("columns") or []
            if str(column.get("id") or "") == "PATH_NAME"
        ),
        "",
    )
    matches = [
        _clean_unit_number(match.group("value"))
        for match in _VISIBLE_UNIT_NUMBER.finditer(location_text)
    ]
    return next((value for value in reversed(matches) if value), "")


def _clean_unit_number(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" ,.-")
    if not cleaned or cleaned.lower() in {"u-hidden", "hidden", "n/a", "none"}:
        return ""
    return cleaned


def extract_source_contract_id(payload: dict[str, Any]) -> str:
    for attributes in (
        payload.get("row_attributes") or {},
        payload.get("hidden_attributes") or {},
    ):
        for key, value in sorted(attributes.items()):
            if _SOURCE_ID_KEYS.search(str(key)) and str(value).strip():
                return str(value).strip()
    direct_link = _SOURCE_ID_LINK.search(str(payload.get("detail_url") or ""))
    if direct_link:
        return direct_link.group("value")
    for column in payload.get("columns") or []:
        for attributes in (column.get("attributes") or {},):
            for key, value in sorted(attributes.items()):
                if _SOURCE_ID_KEYS.search(str(key)) and str(value).strip():
                    return str(value).strip()
        for link in column.get("links") or []:
            match = _SOURCE_ID_LINK.search(str(link.get("href") or ""))
            if match:
                return match.group("value")
    return ""


def _parse_location(value: str) -> tuple[str, str, str, str, str]:
    cleaned = re.sub(r",?\s*(?:Floor\s+)?No\..*$", "", value, flags=re.IGNORECASE).strip(" ,")
    property_type = ""
    for candidate in _PROPERTY_TYPES:
        match = re.search(rf"\b{re.escape(candidate)}\b\s*$", cleaned, re.IGNORECASE)
        if match:
            property_type = candidate
            cleaned = cleaned[: match.start()].strip(" ,")
            break

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    is_landed_home = property_type in {"Villa", "Townhouse"}
    if is_landed_home and len(parts) >= 3:
        # DXB paths for landed homes describe a phase/subcommunity, not a
        # physical building: "Sun, Arabian Ranches 3, Wadi Al Safa 5".
        building_name = ""
        project_name = parts[0]
        penultimate = parts[-2]
        final_area = canonical_area_name(parts[-1])
        penultimate_is_path_marker = bool(re.fullmatch(r"\d+[A-Za-z]?", penultimate))
        final_is_known_market_area = final_area in _AREA_ALIASES.values()
        area_name = (
            parts[-1] if penultimate_is_path_marker or final_is_known_market_area else penultimate
        )
    elif is_landed_home and len(parts) == 2:
        building_name = ""
        project_name, area_name = parts
    elif len(parts) >= 3:
        building_name = parts[0]
        project_name = parts[-2]
        area_name = parts[-1]
    elif len(parts) == 2:
        building_name, area_name = parts
        project_name = ""
    elif parts:
        building_name = ""
        project_name = ""
        area_name = parts[0]
    else:
        building_name = project_name = area_name = ""
    return cleaned, building_name, project_name, canonical_area_name(area_name), property_type


def _first_amount(value: str) -> int:
    match = _FIRST_NUMBER.search(value)
    return int(round(float(match.group("value").replace(",", "")))) if match else 0


def _annualize_contract_amount(
    contract_amount_aed: int,
    contract_term_days: int,
    *,
    contract_term_months: float = 0,
) -> int:
    if not contract_amount_aed or contract_term_days <= 0:
        return 0
    if contract_term_months > 0:
        return int(round(contract_amount_aed * 12 / contract_term_months))
    return int(round(contract_amount_aed * 365.25 / contract_term_days))


def canonical_area_name(value: str) -> str:
    cleaned = re.sub(r"\s+Building\s*$", "", value, flags=re.IGNORECASE).strip()
    cleaned = _AREA_ACRONYM.sub("", cleaned).strip()
    cleaned = cleaned.rstrip(")").strip()
    for ordinal, number in _AREA_ORDINALS.items():
        cleaned = re.sub(rf"\b{ordinal}\b", number, cleaned, flags=re.IGNORECASE)
    alias_key = re.sub(r"\s+", " ", cleaned.lower())
    if alias_key.startswith("international city"):
        return "International City"
    return _AREA_ALIASES.get(alias_key, cleaned)


def _purchase_price(value: str) -> int:
    match = _PURCHASE_PRICE.search(value)
    if not match:
        return 0
    amount = float(match.group("value").replace(",", ""))
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    return int(round(amount * multiplier[match.group("suffix").upper()]))


def _safe_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _safe_datetime(value: str) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _key_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _digest(parts: tuple[str, ...]) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]


def source_account_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("account-"):
            return part
    return ""


def source_run_id_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("run="):
            return part.removeprefix("run=")
    return path.name.removesuffix(".gz").removesuffix(".jsonl") or "legacy"
