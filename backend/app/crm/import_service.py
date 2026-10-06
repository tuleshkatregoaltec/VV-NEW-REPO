from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Any, Iterable

import httpx
import openpyxl
from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, delete, func, or_, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.clickhouse.client import query
from app.config import settings
from app.crm.import_models import (
    CrmContactClaimResponse,
    CrmContactImport,
    CrmContactImportResponse,
    CrmContactImportSummary,
    CrmContactList,
    CrmContactListDetail,
    CrmContactListSummary,
    CrmLeadImportedContact,
    CrmOwnerBulkUpdate,
    CrmOwnerNote,
    CrmOwnerProfile,
    CrmOwnerProperty,
    CrmOwnerRegistryResponse,
    CrmOwnerRegistrySummary,
    CrmOwnerWorkspace,
    CrmOwnerWorkspaceSummary,
    CrmPropertyContactClaim,
    CrmSheetMapping,
)
from app.crm.models import CrmLeadWorkspace

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 50 * 1024 * 1024
_MAX_ROWS = 500_000
_QUERY_CHUNK = 4_000
_SALES_EVIDENCE_UNIT_CHUNK = 20_000
_PLACEHOLDER_HEADER = re.compile(r"^column\s*\d+$", re.IGNORECASE)
_NON_KEY = re.compile(r"[^a-z0-9]+")
_LOCATION_TOKEN = re.compile(r"[a-z0-9]+")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TRANSFER_WORDS = ("sale", "sell", "delayed sell")
_OWNER_SUMMARY_CACHE_TTL_SECONDS = 300
_owner_summary_cache: dict[tuple[str, int | None], tuple[float, CrmOwnerRegistrySummary]] = {}
_UNIT_PLACEHOLDERS = {"", "-", "n/a", "na", "none", "null", "unknown"}
_NUMERIC_PROPERTY_IDENTIFIER = re.compile(r"^\d+(?:\.\d+)?$")
_VILLA_PROPERTY_IDENTIFIER = re.compile(
    r"(?:^|[-\s])(?:v|villa)[-\s]*[a-z0-9.]+$", re.IGNORECASE
)
_TRANSACTION_SIGNATURE_CHUNK = 1_500
_LOCATION_ALIAS_GROUPS = (
    ("jumeirah gate tower 1", "the address jbr 1"),
    ("jumeirah gate tower 2", "the address jbr 2"),
    ("maple", "maple 1"),
    ("maple iii", "maple 3"),
    ("park heights ii t1", "park heights 2 tower 1"),
    ("park heights ii t2", "park heights 2 tower 2"),
    ("executive residences", "executive residences 1"),
    ("club villas at dubai hills", "club villas"),
    ("mag eye phase 1", "mag eye townhouses"),
    ("mag eye 890", "mag 890"),
    ("mag eye 900", "mag 900"),
    ("mag eye 910", "mag 910"),
    ("mag eye 920", "mag 920"),
    ("ellington house", "ellington house 1"),
    ("j one - 1", "j one tower a"),
    ("canal heights", "canal heights 1"),
    ("churchill tower 1-commercial", "churchill executive"),
    ("churchill tower 2-residential", "churchill residence"),
    ("atria ra", "the atria residences"),
    ("citadel tower", "the citadel"),
    ("prive by damac (a)", "prive (a)"),
    ("prive by damac (b)", "prive (b)"),
)
_ROMAN_NUMERALS = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
}


def _invalidate_owner_summary_cache(organization_id: str) -> None:
    for key in [key for key in _owner_summary_cache if key[0] == organization_id]:
        _owner_summary_cache.pop(key, None)

_CANONICAL_FIELDS = {
    "area_name",
    "master_project",
    "project_name",
    "building_name",
    "unit_number",
    "property_type",
    "size_sqft",
    "transaction_date",
    "transaction_price_aed",
    "party_role",
    "procedure_type",
    "contact_name",
    "phone_primary",
    "phone_alternate",
    "email_primary",
}

_ALIASES = {
    "area_name": {"areanameen", "area", "community"},
    "master_project": {"masterproject", "masterdevelopment"},
    "project_name": {"project", "projectname", "development"},
    "building_name": {"buildingnameen", "building", "tower", "buildingname"},
    "unit_number": {
        "unitnumber",
        "unit",
        "villanumber",
        "unitnumberproxy",
        "plotpreregisterationno",
        "plotpreregistrationno",
        "plotregistrationno",
    },
    "property_type": {"propertytypeen", "propertytype", "type"},
    "size_sqft": {"size", "areasqft", "propertysize"},
    "transaction_date": {"regis", "date", "registrationdate", "transactiondate"},
    "transaction_price_aed": {
        "procedurevalue",
        "price",
        "transactionvalue",
        "saleprice",
    },
    "party_role": {"procedurepartytypenameen", "partytype", "partyrole"},
    "procedure_type": {"procedurenameen", "procedurename"},
    "contact_name": {"nameen", "name", "ownername", "contactname"},
    "phone_primary": {"phone", "mobile", "phonenumber", "mobilenumber"},
    "phone_alternate": {"secondarymobile", "alternatemobile", "mobile2"},
    "email_primary": {"email", "emailaddress", "owneremail"},
}


@dataclass
class HeaderCell:
    key: str
    label: str
    index: int


@dataclass
class SheetProfile:
    name: str
    header_row: int
    headers: list[HeaderCell]
    meaningful_rows: int
    field_map: dict[str, str]
    sheet_family: str
    mapping_source: str = "heuristic"
    confidence: float = 0.82
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedContact:
    source_sheet: str
    source_row_number: int
    contact_name: str
    phone_primary: str | None
    phone_alternate: str | None
    email_primary: str | None
    area_name: str
    project_name: str
    building_name: str
    unit_number: str
    property_type: str
    transaction_date: date | None
    transaction_price_aed: int | None
    party_role: str
    procedure_type: str
    row_fingerprint: str
    ownership_status: str = "unmatched"
    confidence_score: int = 20
    match_reason: str = "No exact property evidence was found."
    lead_id: str | None = None
    unit_candidate_key: str | None = None
    latest_sale_date: date | None = None
    latest_sale_price_aed: int | None = None
    later_sale_date: date | None = None
    lease_end: date | None = None
    annual_rent_aed: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def has_valid_contact(self) -> bool:
        return bool(self.phone_primary or self.phone_alternate or self.email_primary)

    @property
    def property_key(self) -> str:
        location = self.building_name or self.project_name
        if not location or not self.unit_number:
            return ""
        return f"{_location_key(location)}|{self.unit_number.lower()}"


_OWNERSHIP_PRIORITY = {
    "former_owner": 6,
    "verified_current_owner": 5,
    "probable_current_owner": 4,
    "unit_linked_unverified": 3,
    "conflicting_claim": 2,
    "registry_not_observed": 1,
    "insufficient_property_data": 1,
    "unmatched": 1,
}

_OWNER_REGISTRY_BASE_SQL = """
WITH base AS (
    SELECT
        c.id,
        c.organization_id,
        c.import_id,
        c.list_id,
        c.source_sheet,
        c.source_row_number,
        c.owner_key,
        c.property_key,
        c.contact_name,
        c.phone_primary,
        c.phone_alternate,
        c.email_primary,
        c.area_name,
        c.project_name,
        c.building_name,
        c.unit_number,
        c.property_type,
        c.transaction_date,
        c.transaction_price_aed,
        c.ownership_status,
        c.confidence_score,
        c.match_reason,
        c.lead_id,
        c.unit_candidate_key,
        c.latest_sale_date,
        c.latest_sale_price_aed,
        c.later_sale_date,
        c.lease_end,
        c.annual_rent_aed,
        c.owner_key AS owner_key_sql,
        c.property_key AS property_key_sql,
        CASE c.ownership_status
            WHEN 'former_owner' THEN 6
            WHEN 'verified_current_owner' THEN 5
            WHEN 'probable_current_owner' THEN 4
            WHEN 'unit_linked_unverified' THEN 3
            WHEN 'conflicting_claim' THEN 2
            ELSE 1
        END AS status_rank
    FROM crm_property_contact_claims c
    WHERE c.organization_id = :organization_id
      AND (
        CAST(:owner_list_id AS INTEGER) IS NULL
        OR c.list_id = CAST(:owner_list_id AS INTEGER)
      )
),
ranked AS (
    SELECT DISTINCT ON (owner_key_sql, property_key_sql)
        *
    FROM base
    ORDER BY
        owner_key_sql,
        property_key_sql,
        status_rank DESC,
        confidence_score DESC,
        transaction_date DESC NULLS LAST
),
properties AS (
    SELECT * FROM ranked
)
"""

_STATUS_SUMMARY_FIELDS = {
    "verified_current_owner": "verified_current_owners",
    "probable_current_owner": "probable_current_owners",
    "unit_linked_unverified": "unit_linked_unverified",
    "former_owner": "former_owners",
    "conflicting_claim": "conflicting_claims",
    "insufficient_property_data": "insufficient_property_data",
    "registry_not_observed": "registry_not_observed",
    "unmatched": "unmatched",
}


def _identity_text(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _owner_key(
    *,
    contact_name: str,
    phone_primary: str | None,
    phone_alternate: str | None,
    email_primary: str | None,
    property_key: str,
) -> str:
    name = _identity_text(contact_name)
    contact = phone_primary or phone_alternate or (email_primary or "").casefold()
    # A name without a contact identifier is not safe evidence that two different
    # properties share one owner. Keep those identities property-scoped.
    seed = f"{name}|{contact or property_key}"
    return hashlib.md5(seed.encode(), usedforsecurity=False).hexdigest()


def _candidate_owner_key(candidate: ParsedContact) -> str:
    return _owner_key(
        contact_name=candidate.contact_name,
        phone_primary=candidate.phone_primary,
        phone_alternate=candidate.phone_alternate,
        email_primary=candidate.email_primary,
        property_key=candidate.property_key,
    )


def _candidate_preference(candidate: ParsedContact) -> tuple[int, int, int, int]:
    return (
        _OWNERSHIP_PRIORITY.get(candidate.ownership_status, 0),
        candidate.confidence_score,
        1 if candidate.has_valid_contact else 0,
        candidate.transaction_date.toordinal() if candidate.transaction_date else 0,
    )


def _dedupe_candidates(candidates: list[ParsedContact]) -> tuple[list[ParsedContact], int]:
    grouped: dict[tuple[str, str], list[ParsedContact]] = {}
    for candidate in candidates:
        property_key = candidate.property_key or f"source:{candidate.row_fingerprint}"
        grouped.setdefault((_candidate_owner_key(candidate), property_key), []).append(candidate)

    unique: list[ParsedContact] = []
    collapsed = 0
    for group in grouped.values():
        best = max(group, key=_candidate_preference)
        ordered_rows = sorted({f"{item.source_sheet}:{item.source_row_number}" for item in group})
        if len(group) > 1:
            collapsed += len(group) - 1
            best.evidence = {
                **best.evidence,
                "duplicate_count": len(group),
                "source_rows": ordered_rows,
                "alternate_claims": [
                    {
                        "source_sheet": item.source_sheet,
                        "source_row_number": item.source_row_number,
                        "transaction_date": (
                            item.transaction_date.isoformat() if item.transaction_date else None
                        ),
                        "transaction_price_aed": item.transaction_price_aed,
                        "ownership_status": item.ownership_status,
                        "confidence_score": item.confidence_score,
                    }
                    for item in group
                    if item is not best
                ],
            }
        best.phone_primary = best.phone_primary or next(
            (item.phone_primary for item in group if item.phone_primary),
            None,
        )
        best.phone_alternate = best.phone_alternate or next(
            (item.phone_alternate for item in group if item.phone_alternate),
            None,
        )
        best.email_primary = best.email_primary or next(
            (item.email_primary for item in group if item.email_primary),
            None,
        )
        unique.append(best)
    unique.sort(key=lambda item: (item.source_sheet, item.source_row_number))
    return unique, collapsed


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _chunks(values: list[str], size: int = _QUERY_CHUNK) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _header_token(value: str) -> str:
    base = value.rsplit("__", 1)[0]
    return _NON_KEY.sub("", base.lower())


@lru_cache(maxsize=100_000)
def _location_key(value: str) -> str:
    normalized = _canonical_location_text(value)
    return _NON_KEY.sub("", normalized)


@lru_cache(maxsize=100_000)
def _canonical_location_text(value: str) -> str:
    normalized = value.lower()
    for source, target in {
        "jumeriah": "jumeirah",
        "residences": "residence",
        "apartments": "apartment",
    }.items():
        normalized = normalized.replace(source, target)
    return normalized


@lru_cache(maxsize=100_000)
def _location_tokens(value: str) -> tuple[str, ...]:
    """Return a stable building identity token set without trusting word order."""
    tokens: list[str] = []
    for token in _LOCATION_TOKEN.findall(_canonical_location_text(value)):
        normalized = _ROMAN_NUMERALS.get(token, token)
        tokens.append(str(int(normalized)) if normalized.isdigit() else normalized)
    return tuple(tokens)


@lru_cache(maxsize=100_000)
def _location_alias_identity(value: str) -> str:
    key = _location_key(value)
    if not key:
        return ""
    for group in _LOCATION_ALIAS_GROUPS:
        canonical = _location_key(group[0])
        for alias in group:
            alias_key = _location_key(alias)
            if key == alias_key or (len(alias_key) >= 8 and key.endswith(alias_key)):
                return canonical
    return key


@lru_cache(maxsize=200_000)
def _building_match_strength(owner_location: str, sale_location: str) -> tuple[int, str]:
    """Return a conservative match score for two building labels.

    DXB Interact frequently puts the project after the building while owner
    exports put it before the building. We accept reordered labels and a single
    unambiguous appended/omitted location suffix, but never a generic fuzzy
    string match. Unit equality and a unique area are enforced by the caller.
    """
    owner_key = _location_key(owner_location)
    sale_key = _location_key(sale_location)
    if owner_key and owner_key == sale_key:
        return 3, "exact_building_key"

    owner_tokens = frozenset(_location_tokens(owner_location))
    sale_tokens = frozenset(_location_tokens(sale_location))
    if len(owner_tokens) < 3 or len(sale_tokens) < 3:
        return 0, ""

    owner_numbers = _location_number_markers(owner_location)
    sale_numbers = _location_number_markers(sale_location)
    if owner_numbers != sale_numbers:
        return 0, ""
    if owner_tokens == sale_tokens:
        return 2, "canonical_building_identity"
    if owner_tokens <= sale_tokens or sale_tokens <= owner_tokens:
        return 1, "canonical_building_variant"
    return 0, ""


@lru_cache(maxsize=100_000)
def _location_number_markers(value: str) -> frozenset[str]:
    markers: set[str] = set()
    for token in _location_tokens(value):
        markers.update(str(int(marker)) for marker in re.findall(r"\d+", token))
    return frozenset(markers)


@lru_cache(maxsize=300_000)
def _location_similarity(owner_location: str, sale_location: str) -> int:
    """Score two location labels for transaction-collision resolution."""
    if not owner_location or not sale_location:
        return 0
    if _location_alias_identity(owner_location) == _location_alias_identity(sale_location):
        return 100
    strength, _ = _building_match_strength(owner_location, sale_location)
    if strength:
        return {1: 82, 2: 92, 3: 100}[strength]

    owner_tokens = frozenset(_location_tokens(owner_location))
    sale_tokens = frozenset(_location_tokens(sale_location))
    if not owner_tokens or not sale_tokens:
        return 0
    owner_numbers = _location_number_markers(owner_location)
    sale_numbers = _location_number_markers(sale_location)
    if owner_numbers and sale_numbers and owner_numbers != sale_numbers:
        return 0

    overlap = len(owner_tokens & sale_tokens)
    if not overlap:
        return 0
    return round(75 * overlap / len(owner_tokens | sale_tokens))


def _transaction_location_score(candidate: ParsedContact, row: dict[str, Any]) -> int:
    owner_building = _usable_project_name(candidate.building_name)
    owner_project = _usable_project_name(candidate.project_name)
    owner_area = _usable_project_name(candidate.area_name)
    sale_building = str(row.get("building_name") or "")
    sale_project = str(row.get("project_name") or "")
    sale_area = str(row.get("area_name") or "")
    combined_sale = " ".join(value for value in (sale_building, sale_project) if value)

    building_score = max(
        (_location_similarity(owner_building, value) for value in (sale_building, combined_sale)),
        default=0,
    )
    project_score = max(
        (_location_similarity(owner_project, value) for value in (sale_project, sale_building, combined_sale)),
        default=0,
    )
    area_score = _location_similarity(owner_area, sale_area)
    if owner_building:
        return round(0.70 * building_score + 0.25 * project_score + 0.05 * area_score)
    if owner_project:
        return round(0.90 * project_score + 0.10 * area_score)
    return area_score


def _unique_headers(values: tuple[Any, ...] | list[Any]) -> list[HeaderCell]:
    counts: dict[str, int] = {}
    headers: list[HeaderCell] = []
    for index, raw in enumerate(values):
        label = _text(raw)
        if not label or _PLACEHOLDER_HEADER.match(label):
            continue
        count = counts.get(label.lower(), 0) + 1
        counts[label.lower()] = count
        key = label if count == 1 else f"{label}__{count}"
        headers.append(HeaderCell(key=key, label=label, index=index))
    return headers


def _recognized_headers(values: tuple[Any, ...] | list[Any]) -> int:
    tokens = {_header_token(_text(value)) for value in values if _text(value)}
    aliases = set().union(*_ALIASES.values())
    return len(tokens & aliases)


def _find_header(rows: list[tuple[Any, ...]]) -> tuple[int, list[HeaderCell]]:
    best_index = 0
    best_score = -1
    best_headers: list[HeaderCell] = []
    for index, row in enumerate(rows):
        headers = _unique_headers(row)
        score = _recognized_headers(row) * 100 + len(headers)
        if score > best_score:
            best_index = index
            best_score = score
            best_headers = headers
    return best_index + 1, best_headers


def _header_for(
    headers: list[HeaderCell],
    aliases: set[str],
    *,
    last: bool = False,
) -> str | None:
    matches = [header.key for header in headers if _header_token(header.key) in aliases]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


def _heuristic_mapping(
    headers: list[HeaderCell],
    *,
    filename: str,
    sheet_name: str,
) -> tuple[dict[str, str], str, list[str]]:
    mapping: dict[str, str] = {}
    warnings: list[str] = []
    lowered_filename = filename.lower()
    for field_name, aliases in _ALIASES.items():
        header = _header_for(headers, aliases)
        if header:
            mapping[field_name] = header

    if "elan" in lowered_filename:
        villa = _header_for(headers, {"villanumber"}, last=True)
        if villa:
            mapping["unit_number"] = villa

    header_tokens = {_header_token(header.key): header.key for header in headers}
    if (
        "procedure" in header_tokens
        and "procedurepartytypenameen" not in header_tokens
        and "partytype" not in header_tokens
    ):
        mapping["party_role"] = header_tokens["procedure"]
        mapping.pop("procedure_type", None)

    family = "transaction_party" if mapping.get("transaction_date") else "contact_list"
    if "contact_name" not in mapping:
        warnings.append("No owner/contact name column was detected.")
    if "unit_number" not in mapping:
        warnings.append("No direct unit-number column was detected.")
    if not {"phone_primary", "phone_alternate", "email_primary"} & mapping.keys():
        warnings.append("No contact channel was detected.")
    if family == "contact_list" and not mapping.get("building_name"):
        inferred = _inferred_project(filename, sheet_name)
        if inferred:
            warnings.append(f"Property name will be inferred as {inferred}.")
    return mapping, family, warnings


def _inferred_project(filename: str, sheet_name: str) -> str:
    source = f"{filename} {sheet_name}".lower()
    for name in ("Aura", "Harmony", "Alaya", "Elysian", "Elan"):
        if name.lower() in source:
            return name
    return ""


def _inspect_xlsx(data: bytes, filename: str) -> list[SheetProfile]:
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    profiles: list[SheetProfile] = []
    try:
        for sheet in workbook.worksheets:
            initial_rows = list(
                sheet.iter_rows(
                    min_row=1,
                    max_row=min(15, max(1, sheet.max_row)),
                    max_col=min(100, max(1, sheet.max_column)),
                    values_only=True,
                )
            )
            header_row, headers = _find_header(initial_rows)
            mapping, family, warnings = _heuristic_mapping(
                headers,
                filename=filename,
                sheet_name=sheet.title,
            )
            profiles.append(
                SheetProfile(
                    name=sheet.title.strip() or "Sheet",
                    header_row=header_row,
                    headers=headers,
                    meaningful_rows=max(0, sheet.max_row - header_row),
                    field_map=mapping,
                    sheet_family=family,
                    warnings=warnings,
                )
            )
    finally:
        workbook.close()
    return profiles


def _csv_rows(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def _inspect_csv(data: bytes, filename: str) -> list[SheetProfile]:
    rows = _csv_rows(data)
    initial = [tuple(row[:100]) for row in rows[:15]]
    header_row, headers = _find_header(initial)
    mapping, family, warnings = _heuristic_mapping(
        headers,
        filename=filename,
        sheet_name=Path(filename).stem,
    )
    return [
        SheetProfile(
            name=Path(filename).stem,
            header_row=header_row,
            headers=headers,
            meaningful_rows=max(0, len(rows) - header_row),
            field_map=mapping,
            sheet_family=family,
            warnings=warnings,
        )
    ]


async def _llm_mapping(profile: SheetProfile) -> SheetProfile:
    prompt = {
        "task": "Map spreadsheet headers to canonical CRM owner-import fields.",
        "privacy": "Headers only. No owner names, phone numbers, emails, or row values are included.",
        "canonical_fields": sorted(_CANONICAL_FIELDS),
        "headers": [header.key for header in profile.headers],
        "heuristic_mapping": profile.field_map,
        "requirements": [
            "Return JSON only.",
            "Only use canonical fields and exact supplied header names.",
            "Do not invent a unit number when no unit column exists.",
        ],
        "response_shape": {
            "field_map": {"canonical_field": "exact header"},
            "sheet_family": "transaction_party or contact_list",
            "confidence": "number from 0 to 1",
            "warnings": ["string"],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEFAULT_CHAT_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You map spreadsheet schemas. Return a single valid JSON object "
                                "and never infer or request personal data."
                            ),
                        },
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                    "max_tokens": 900,
                    "provider": {"zdr": True},
                },
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            proposal = json.loads(content)
    except Exception:
        logger.warning(
            "CRM import schema mapping fell back to heuristics",
            extra={"sheet": profile.name},
            exc_info=True,
        )
        profile.mapping_source = "heuristic_fallback"
        profile.warnings.append("Automated schema confirmation was unavailable.")
        return profile

    available = {header.key for header in profile.headers}
    llm_map = proposal.get("field_map") if isinstance(proposal, dict) else {}
    if isinstance(llm_map, dict):
        for canonical, header in llm_map.items():
            if canonical in _CANONICAL_FIELDS and header in available:
                profile.field_map.setdefault(canonical, header)
    family = proposal.get("sheet_family")
    if family in {"transaction_party", "contact_list"}:
        profile.sheet_family = family
    confidence = proposal.get("confidence")
    if isinstance(confidence, int | float):
        profile.confidence = max(0.0, min(1.0, float(confidence)))
    warnings = proposal.get("warnings")
    if isinstance(warnings, list):
        profile.warnings.extend(str(item)[:300] for item in warnings if item)
    profile.mapping_source = "llm"
    return profile


def _normalize_unit(value: Any) -> str:
    unit = _text(value).upper().replace("–", "-")
    unit = re.sub(r"\s+", "", unit)
    if unit.lower() in _UNIT_PLACEHOLDERS:
        return ""
    if unit.endswith(".0") and unit[:-2].isdigit():
        unit = unit[:-2]
    if unit.startswith("TAG-") and "-" in unit:
        unit = unit.rsplit("-", 1)[-1]
    return unit


def _usable_project_name(value: str) -> str:
    """Return a project label only when it is meaningful matching context."""
    project = value.strip()
    if not project or project.lower() in _UNIT_PLACEHOLDERS:
        return ""
    return "" if _NUMERIC_PROPERTY_IDENTIFIER.fullmatch(project) else project


def _recover_embedded_property_identity(candidate: ParsedContact) -> None:
    """Recover a unit embedded in owner-export address fields when unambiguous.

    Some owner files put a complete villa identifier in the building column
    (``DE Maple 2-V-486``) while DXB Interact stores ``Maple 2`` as the
    building and the complete identifier as the unit. Other exports put a
    plain unit number in that column alongside a project name.  Recover only
    these explicit formats; arbitrary address text remains unmatched.
    """
    candidate.unit_number = _normalize_unit(candidate.unit_number)
    source_location = candidate.building_name or candidate.project_name
    edge_tower = re.match(r"^([AB])\d+$", candidate.unit_number, re.IGNORECASE)
    if _location_key(source_location) == "theedge" and edge_tower:
        source_building = candidate.building_name
        candidate.building_name = f"The Edge Tower {edge_tower.group(1).upper()}"
        candidate.evidence["address_recovery"] = {
            "source_building_name": source_building,
            "resolved_building_name": candidate.building_name,
            "resolved_unit_number": candidate.unit_number,
            "method": "project_unit_prefix_tower",
        }
    if candidate.unit_number:
        return

    source_building = candidate.building_name.strip()
    project = _usable_project_name(candidate.project_name)
    if not source_building or source_building.lower() in _UNIT_PLACEHOLDERS or not project:
        return

    source_identifier = _normalize_unit(source_building)
    is_villa_identifier = bool(_VILLA_PROPERTY_IDENTIFIER.search(source_building))
    is_numeric_identifier = bool(_NUMERIC_PROPERTY_IDENTIFIER.fullmatch(source_building))
    if not (is_villa_identifier or is_numeric_identifier):
        return

    candidate.building_name = project
    candidate.unit_number = source_identifier
    candidate.evidence["address_recovery"] = {
        "source_building_name": source_building,
        "resolved_building_name": project,
        "resolved_unit_number": source_identifier,
        "method": (
            "embedded_villa_identifier" if is_villa_identifier else "embedded_numeric_identifier"
        ),
    }


def _normalize_phone(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("971") and len(digits) >= 11:
        return f"+{digits}"
    if digits.startswith("05") and len(digits) == 10:
        return f"+971{digits[1:]}"
    if digits.startswith("5") and len(digits) == 9:
        return f"+971{digits}"
    if len(digits) < 7:
        return None
    return f"+{digits}" if raw.startswith("+") else digits


def _normalize_email(value: Any) -> str | None:
    email = _text(value).lower()
    return email if email and _EMAIL.match(email) else None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d-%b-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: Any) -> int | None:
    if isinstance(value, int | float) and value > 0:
        return int(round(value))
    raw = re.sub(r"[^\d.]", "", _text(value))
    if not raw:
        return None
    try:
        amount = int(round(float(raw)))
    except ValueError:
        return None
    return amount if amount > 0 else None


def _normalized_role(value: Any) -> str:
    role = _text(value).lower()
    if "buyer" in role:
        return "Buyer"
    if "seller" in role:
        return "Seller"
    return _text(value).title()


def _is_transfer_candidate(role: str, procedure: str, family: str) -> bool:
    if family == "contact_list":
        return True
    if role not in {"Buyer", "Seller"}:
        return False
    if not procedure:
        return True
    lowered = procedure.lower()
    return any(word in lowered for word in _TRANSFER_WORDS)


def _field_value(
    row: tuple[Any, ...] | list[Any],
    profile: SheetProfile,
    canonical: str,
) -> Any:
    header_key = profile.field_map.get(canonical)
    if not header_key:
        return None
    header = next((item for item in profile.headers if item.key == header_key), None)
    if not header or header.index >= len(row):
        return None
    return row[header.index]


def _candidate_from_row(
    row: tuple[Any, ...] | list[Any],
    *,
    profile: SheetProfile,
    filename: str,
    row_number: int,
) -> ParsedContact | None:
    name = _text(_field_value(row, profile, "contact_name"))
    unit = _normalize_unit(_field_value(row, profile, "unit_number"))
    if not name:
        return None
    role = _normalized_role(_field_value(row, profile, "party_role"))
    procedure = _text(_field_value(row, profile, "procedure_type"))
    if not _is_transfer_candidate(role, procedure, profile.sheet_family):
        return None

    inferred_project = _inferred_project(filename, profile.name)
    area = _text(_field_value(row, profile, "area_name"))
    master_project = _text(_field_value(row, profile, "master_project"))
    project = _text(_field_value(row, profile, "project_name")) or inferred_project
    building = _text(_field_value(row, profile, "building_name")) or project
    if not area:
        area = "Tilal Al Ghaf" if inferred_project else master_project
    if not project:
        project = master_project

    phone = _normalize_phone(_field_value(row, profile, "phone_primary"))
    alternate = _normalize_phone(_field_value(row, profile, "phone_alternate"))
    email = _normalize_email(_field_value(row, profile, "email_primary"))
    transaction_date = _parse_date(_field_value(row, profile, "transaction_date"))
    transaction_price = _parse_amount(_field_value(row, profile, "transaction_price_aed"))
    fingerprint_source = "|".join(
        (
            profile.name,
            str(row_number),
            name.lower(),
            building.lower(),
            unit.lower(),
            transaction_date.isoformat() if transaction_date else "",
        )
    )
    candidate = ParsedContact(
        source_sheet=profile.name,
        source_row_number=row_number,
        contact_name=name[:300],
        phone_primary=phone,
        phone_alternate=alternate if alternate != phone else None,
        email_primary=email,
        area_name=area[:200],
        project_name=project[:200],
        building_name=building[:250],
        unit_number=unit[:100],
        property_type=_text(_field_value(row, profile, "property_type"))[:100],
        transaction_date=transaction_date,
        transaction_price_aed=transaction_price,
        party_role=role[:80],
        procedure_type=procedure[:160],
        row_fingerprint=hashlib.sha256(fingerprint_source.encode()).hexdigest(),
    )
    _recover_embedded_property_identity(candidate)
    return candidate


def _parse_xlsx(
    data: bytes,
    filename: str,
    profiles: list[SheetProfile],
) -> tuple[list[ParsedContact], int]:
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    candidates: list[ParsedContact] = []
    total_rows = 0
    profile_by_name = {profile.name: profile for profile in profiles}
    try:
        for sheet in workbook.worksheets:
            profile = profile_by_name.get(sheet.title.strip() or "Sheet")
            if not profile:
                continue
            max_index = max((header.index for header in profile.headers), default=0)
            for row_number, row in enumerate(
                sheet.iter_rows(
                    min_row=profile.header_row + 1,
                    max_col=max_index + 1,
                    values_only=True,
                ),
                start=profile.header_row + 1,
            ):
                if not any(value not in (None, "") for value in row):
                    continue
                total_rows += 1
                if total_rows > _MAX_ROWS:
                    raise ValueError(f"Import exceeds the {_MAX_ROWS:,}-row limit")
                candidate = _candidate_from_row(
                    row,
                    profile=profile,
                    filename=filename,
                    row_number=row_number,
                )
                if candidate:
                    candidates.append(candidate)
    finally:
        workbook.close()
    return candidates, total_rows


def _parse_csv(
    data: bytes,
    filename: str,
    profiles: list[SheetProfile],
) -> tuple[list[ParsedContact], int]:
    rows = _csv_rows(data)
    profile = profiles[0]
    candidates: list[ParsedContact] = []
    total_rows = 0
    for row_number, row in enumerate(rows[profile.header_row :], start=profile.header_row + 1):
        if not any(value.strip() for value in row):
            continue
        total_rows += 1
        if total_rows > _MAX_ROWS:
            raise ValueError(f"Import exceeds the {_MAX_ROWS:,}-row limit")
        candidate = _candidate_from_row(
            row,
            profile=profile,
            filename=filename,
            row_number=row_number,
        )
        if candidate:
            candidates.append(candidate)
    return candidates, total_rows


async def _recover_property_identity_from_transaction(
    candidates: list[ParsedContact],
) -> dict[str, int]:
    """Resolve a canonical DXBI property from an exact sale date and price.

    Transaction-party imports usually contain authoritative DLD date/price
    evidence even when their project fields use a different naming scheme.
    A globally unique signature is sufficient to recover the property. When a
    signature occurs on multiple properties, location context must select one
    candidate with a clear score margin.
    """
    eligible = [
        candidate
        for candidate in candidates
        if candidate.transaction_date and candidate.transaction_price_aed
    ]
    unique_resolutions = 0
    contextual_resolutions = 0
    ambiguous = 0
    for start in range(0, len(eligible), _TRANSACTION_SIGNATURE_CHUNK):
        batch = eligible[start : start + _TRANSACTION_SIGNATURE_CHUNK]
        wanted = {
            (candidate.transaction_date, int(candidate.transaction_price_aed or 0))
            for candidate in batch
        }
        rows = await query(
            """
            SELECT
                transaction_date,
                sale_amount_aed,
                replaceRegexpAll(lowerUTF8(unit_number), '\\s+', '') AS unit_key,
                unit_number,
                building_name,
                building_key,
                project_name,
                area_name,
                area_key,
                sale_key,
                detail_url
            FROM dxbi_sales_unit_events FINAL
            WHERE transaction_date IN {dates:Array(Date)}
              AND sale_amount_aed IN {prices:Array(UInt64)}
            """,
            {
                "dates": sorted({signature[0] for signature in wanted}),
                "prices": sorted({signature[1] for signature in wanted}),
            },
        )
        by_signature: dict[
            tuple[date, int],
            dict[tuple[str, str, str], dict[str, Any]],
        ] = {}
        for row in rows:
            signature = (
                row["transaction_date"],
                int(row.get("sale_amount_aed") or 0),
            )
            if signature not in wanted:
                continue
            unit_key = str(row.get("unit_key") or "")
            building_key = str(row.get("building_key") or "") or _location_key(
                str(row.get("building_name") or row.get("project_name") or "")
            )
            if not unit_key or not building_key:
                continue
            property_identity = (
                str(row.get("area_key") or ""),
                building_key,
                unit_key,
            )
            by_signature.setdefault(signature, {}).setdefault(property_identity, row)

        for candidate in batch:
            signature = (
                candidate.transaction_date,
                int(candidate.transaction_price_aed or 0),
            )
            properties = list(by_signature.get(signature, {}).values())
            if not properties:
                continue

            method = "unique_transaction_signature"
            score = 100
            selected: dict[str, Any] | None = None
            if len(properties) == 1:
                selected = properties[0]
                location_score = _transaction_location_score(candidate, selected)
                has_source_location = bool(
                    _usable_project_name(candidate.building_name)
                    or _usable_project_name(candidate.project_name)
                    or _usable_project_name(candidate.area_name)
                )
                if has_source_location and location_score < 55:
                    selected = None
                    ambiguous += 1
                    continue
                score = location_score or 100
                unique_resolutions += 1
            else:
                scored = sorted(
                    (
                        (_transaction_location_score(candidate, row), row)
                        for row in properties
                    ),
                    key=lambda item: item[0],
                    reverse=True,
                )
                score, selected = scored[0]
                runner_up = scored[1][0]
                if score < 55 or score - runner_up < 12:
                    selected = None
                    ambiguous += 1
                    continue
                method = "transaction_signature_with_location"
                contextual_resolutions += 1

            if not selected:
                continue
            source_identity = {
                "area_name": candidate.area_name,
                "project_name": candidate.project_name,
                "building_name": candidate.building_name,
                "unit_number": candidate.unit_number,
            }
            candidate.area_name = str(selected.get("area_name") or candidate.area_name)
            candidate.project_name = str(
                selected.get("project_name") or candidate.project_name
            )
            candidate.building_name = str(
                selected.get("building_name") or selected.get("project_name") or ""
            )
            candidate.unit_number = _normalize_unit(selected.get("unit_number"))
            candidate.evidence["property_identity_resolution"] = {
                "method": method,
                "score": score,
                "transaction_candidate_count": len(properties),
                "source": source_identity,
                "resolved": {
                    "area_name": candidate.area_name,
                    "project_name": candidate.project_name,
                    "building_name": candidate.building_name,
                    "unit_number": candidate.unit_number,
                    "sale_key": str(selected.get("sale_key") or ""),
                },
            }

    return {
        "eligible": len(eligible),
        "unique": unique_resolutions,
        "contextual": contextual_resolutions,
        "ambiguous": ambiguous,
    }


async def _recover_property_identity_from_near_transaction(
    candidates: list[ParsedContact],
    *,
    window_days: int = 14,
) -> dict[str, int]:
    """Recover property identity when registry/display dates differ slightly.

    The DLD registration date in owner exports can differ from DXBI's displayed
    transaction date. Price remains exact, and a project/building hierarchy
    must identify one property within the bounded window.
    """
    eligible = [
        candidate
        for candidate in candidates
        if candidate.transaction_date
        and candidate.transaction_price_aed
        and "property_identity_resolution" not in candidate.evidence
    ]
    resolved = 0
    ambiguous = 0
    for start in range(0, len(eligible), 500):
        batch = eligible[start : start + 500]
        dates = {
            candidate.transaction_date + timedelta(days=offset)
            for candidate in batch
            for offset in range(-window_days, window_days + 1)
            if candidate.transaction_date
        }
        prices = sorted({int(candidate.transaction_price_aed or 0) for candidate in batch})
        rows = await query(
            """
            SELECT
                transaction_date,
                sale_amount_aed,
                replaceRegexpAll(lowerUTF8(unit_number), '\\s+', '') AS unit_key,
                unit_number,
                building_name,
                building_key,
                project_name,
                area_name,
                area_key,
                sale_key,
                detail_url
            FROM dxbi_sales_unit_events FINAL
            WHERE transaction_date IN {dates:Array(Date)}
              AND sale_amount_aed IN {prices:Array(UInt64)}
            """,
            {"dates": sorted(dates), "prices": prices},
        )
        rows_by_price: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            rows_by_price.setdefault(int(row.get("sale_amount_aed") or 0), []).append(row)

        for candidate in batch:
            source_date = candidate.transaction_date
            if not source_date:
                continue
            candidate_rows = [
                row
                for row in rows_by_price.get(int(candidate.transaction_price_aed or 0), [])
                if abs((row["transaction_date"] - source_date).days) <= window_days
            ]
            properties: dict[tuple[str, str, str], dict[str, Any]] = {}
            for row in candidate_rows:
                unit_key = str(row.get("unit_key") or "")
                building_key = str(row.get("building_key") or "") or _location_key(
                    str(row.get("building_name") or row.get("project_name") or "")
                )
                if not unit_key or not building_key:
                    continue
                identity = (
                    str(row.get("area_key") or ""),
                    building_key,
                    unit_key,
                )
                current = properties.get(identity)
                if current is None or abs((row["transaction_date"] - source_date).days) < abs(
                    (current["transaction_date"] - source_date).days
                ):
                    properties[identity] = row
            if not properties:
                continue

            ranked = sorted(
                (
                    (
                        _transaction_location_score(candidate, row),
                        abs((row["transaction_date"] - source_date).days),
                        row,
                    )
                    for row in properties.values()
                ),
                key=lambda item: (-item[0], item[1]),
            )
            score, date_delta, selected = ranked[0]
            if score < 55:
                continue
            if len(ranked) > 1:
                runner_score, runner_delta, _ = ranked[1]
                clear_location = score - runner_score >= 12
                clear_date = score >= 80 and date_delta + 2 <= runner_delta
                if not (clear_location or clear_date):
                    ambiguous += 1
                    continue

            source_identity = {
                "area_name": candidate.area_name,
                "project_name": candidate.project_name,
                "building_name": candidate.building_name,
                "unit_number": candidate.unit_number,
            }
            candidate.area_name = str(selected.get("area_name") or candidate.area_name)
            candidate.project_name = str(
                selected.get("project_name") or candidate.project_name
            )
            candidate.building_name = str(
                selected.get("building_name") or selected.get("project_name") or ""
            )
            candidate.unit_number = _normalize_unit(selected.get("unit_number"))
            candidate.evidence["property_identity_resolution"] = {
                "method": "near_transaction_signature_with_location",
                "score": score,
                "date_delta_days": date_delta,
                "transaction_candidate_count": len(ranked),
                "source": source_identity,
                "resolved": {
                    "area_name": candidate.area_name,
                    "project_name": candidate.project_name,
                    "building_name": candidate.building_name,
                    "unit_number": candidate.unit_number,
                    "sale_key": str(selected.get("sale_key") or ""),
                },
            }
            resolved += 1

    return {"eligible": len(eligible), "resolved": resolved, "ambiguous": ambiguous}


async def _sales_evidence(
    candidates: list[ParsedContact],
) -> dict[str, list[dict[str, Any]]]:
    """Find DXBI sales history through a canonical project/building hierarchy."""
    unit_keys = sorted(
        {candidate.unit_number.lower() for candidate in candidates if candidate.property_key}
    )
    evidence: dict[str, list[dict[str, Any]]] = {}
    sales_by_unit: dict[str, list[dict[str, Any]]] = {}
    for chunk in _chunks(unit_keys, size=_SALES_EVIDENCE_UNIT_CHUNK):
        rows = await query(
            """
            SELECT
                replaceRegexpAll(lowerUTF8(unit_number), '\\s+', '') AS unit_key,
                unit_number,
                building_name,
                building_key,
                project_name,
                area_name,
                area_key,
                transaction_date,
                sale_amount_aed,
                sale_key,
                detail_url
            FROM dxbi_sales_unit_events FINAL
            WHERE replaceRegexpAll(lowerUTF8(unit_number), '\\s+', '')
                IN {unit_keys:Array(String)}
            ORDER BY unit_key, transaction_date
            """,
            {"unit_keys": chunk},
        )
        for row in rows:
            sales_by_unit.setdefault(str(row["unit_key"]), []).append(row)

    properties_by_unit: dict[
        str,
        list[tuple[tuple[str, str, str], list[dict[str, Any]]]],
    ] = {}
    for unit_key, unit_rows in sales_by_unit.items():
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in unit_rows:
            building_key = str(row.get("building_key") or "") or _location_key(
                str(row.get("building_name") or row.get("project_name") or "")
            )
            identity = (
                str(row.get("area_key") or ""),
                building_key,
                str(row.get("unit_key") or ""),
            )
            grouped.setdefault(identity, []).append(row)
        properties_by_unit[unit_key] = list(grouped.items())

    resolution_cache: dict[
        tuple[str, str, str, str],
        tuple[int, str, list[dict[str, Any]], int] | None,
    ] = {}
    for candidate in candidates:
        source_property_key = candidate.property_key
        if not source_property_key:
            continue
        rows_for_unit = sales_by_unit.get(candidate.unit_number.lower(), [])
        if not rows_for_unit:
            candidate.evidence["sales_lookup"] = {
                "status": "unit_not_observed",
                "normalized_unit_number": candidate.unit_number.lower(),
            }
            continue

        cache_key = (
            _location_key(candidate.area_name),
            _location_key(candidate.project_name),
            _location_key(candidate.building_name),
            candidate.unit_number.lower(),
        )
        if cache_key in resolution_cache:
            cached = resolution_cache[cache_key]
            if cached is None:
                continue
            best_score, method, selected_rows, registry_candidate_count = cached
        else:
            ranked = sorted(
                (
                    (
                        _transaction_location_score(candidate, property_rows[0]),
                        identity,
                        property_rows,
                    )
                    for identity, property_rows in properties_by_unit[
                        candidate.unit_number.lower()
                    ]
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            best_score, _, selected_rows = ranked[0]
            runner_up = ranked[1][0] if len(ranked) > 1 else 0
            distinctive_unit = (
                len(candidate.unit_number) >= 5
                and any(character.isalpha() for character in candidate.unit_number)
            )
            unique_distinctive_unit = distinctive_unit and len(ranked) == 1
            if not unique_distinctive_unit and (
                best_score < 55 or (len(ranked) > 1 and best_score - runner_up < 12)
            ):
                candidate.evidence["sales_lookup"] = {
                    "status": "ambiguous_location",
                    "registry_property_candidates": len(ranked),
                    "best_location_score": best_score,
                    "runner_up_location_score": runner_up,
                }
                resolution_cache[cache_key] = None
                continue

            method = (
                "unique_registry_unit_identifier"
                if unique_distinctive_unit
                else "unit_with_location_hierarchy"
            )
            registry_candidate_count = len(ranked)
            resolution_cache[cache_key] = (
                best_score,
                method,
                selected_rows,
                registry_candidate_count,
            )

        canonical = selected_rows[0]
        candidate.evidence.pop("sales_lookup", None)
        source_identity = {
            "area_name": candidate.area_name,
            "project_name": candidate.project_name,
            "building_name": candidate.building_name,
            "unit_number": candidate.unit_number,
        }
        candidate.area_name = str(canonical.get("area_name") or candidate.area_name)
        candidate.project_name = str(canonical.get("project_name") or candidate.project_name)
        candidate.building_name = str(
            canonical.get("building_name") or canonical.get("project_name") or ""
        )
        candidate.unit_number = _normalize_unit(canonical.get("unit_number"))
        if candidate.property_key != source_property_key:
            candidate.evidence["unit_hierarchy_resolution"] = {
                "method": method,
                "score": best_score,
                "registry_property_candidates": registry_candidate_count,
                "source": source_identity,
                "resolved": {
                    "area_name": candidate.area_name,
                    "project_name": candidate.project_name,
                    "building_name": candidate.building_name,
                    "unit_number": candidate.unit_number,
                },
            }

        selected: list[dict[str, Any]] = []
        seen_sale_keys: set[str] = set()
        for row in selected_rows:
            sale_key = str(row.get("sale_key") or "")
            if sale_key in seen_sale_keys:
                continue
            seen_sale_keys.add(sale_key)
            selected.append({**row, "_match_method": method})
        evidence[candidate.property_key] = selected
    return evidence


async def _rental_evidence(
    candidates: list[ParsedContact],
) -> dict[str, dict[str, Any]]:
    units = sorted({candidate.unit_number for candidate in candidates if candidate.unit_number})
    return await _rental_evidence_for_units(units)


async def _rental_evidence_for_units(units: list[str]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    units = sorted({_normalize_unit(unit) for unit in units if _normalize_unit(unit)})
    if not units:
        return evidence
    columns = await query(
        "SELECT count() AS has_unit FROM system.columns WHERE database=currentDatabase() "
        "AND table='dxbi_rental_unit_candidates' AND name='unit_number'"
    )
    source_unit = "c.unit_number" if columns[0]["has_unit"] else "''"
    anchor = date.today()
    for chunk in _chunks(units):
        rows = await query(
            rf"""
            WITH
                if({source_unit} != '', {source_unit}, m.unit_number) AS observed_unit,
                replaceRegexpAll(upperUTF8(replaceAll(observed_unit, '–', '-')), '\\s+', '') AS compact_unit,
                if(match(compact_unit, '^\\d+\\.0$'), substring(compact_unit, 1, length(compact_unit)-2), compact_unit) AS numeric_unit,
                if(startsWith(numeric_unit, 'TAG-'), arrayElement(splitByChar('-', numeric_unit), -1), numeric_unit) AS normalized_unit
            SELECT
                c.event_key AS event_key,
                c.unit_candidate_key AS unit_candidate_key,
                c.building_name AS building_name,
                c.project_name AS project_name,
                c.area_name AS area_name,
                c.property_type AS property_type,
                c.lease_end AS lease_end,
                c.annual_rent_aed AS annual_rent_aed,
                observed_unit AS unit_number,
                normalized_unit AS unit_key,
                if({source_unit} != '', 'source_unit', 'sale_inference') AS rental_match_method
            FROM dxbi_rental_unit_candidates AS c FINAL
            LEFT JOIN dxbi_rental_sale_matches AS m FINAL USING (unit_candidate_key)
            WHERE
                ({source_unit} != '' OR m.match_status = 'unique')
                AND normalized_unit IN {{units:Array(String)}}
                AND c.lease_end >= {{window_start:Date}}
                AND c.lease_end <= {{window_end:Date}}
            ORDER BY ({source_unit} != '') DESC, c.lease_end DESC, c.unit_candidate_key, c.event_key
            SETTINGS max_threads=2, max_memory_usage=2000000000
            """,
            {
                "units": chunk,
                "window_start": (anchor - timedelta(days=365)).isoformat(),
                "window_end": (anchor + timedelta(days=90)).isoformat(),
            },
        )
        for row in rows:
            location = str(row.get("building_name") or row.get("project_name") or "")
            key = f"{_location_key(location)}|{_normalize_unit(row['unit_number']).lower()}"
            evidence.setdefault(key, row)
    return evidence


async def refresh_property_contact_rentals(
    db: AsyncSession,
    *,
    organization_id: str,
    import_id: int | None = None,
    commit: bool = True,
) -> dict[str, int]:
    """Refresh rental links for every imported claim without changing owner identities.

    Missing current evidence clears an old rental link. Contact/source data,
    ownership assessments, sales evidence and agent workspaces remain intact.
    """
    statement = select(CrmPropertyContactClaim).where(
        CrmPropertyContactClaim.organization_id == organization_id
    )
    if import_id is not None:
        statement = statement.where(CrmPropertyContactClaim.import_id == import_id)
    claims = (await db.exec(statement.with_for_update())).all()
    units = sorted({claim.unit_number for claim in claims if claim.unit_number})
    rentals = await _rental_evidence_for_units(units)
    counts = {
        "claims": len(claims),
        "before_hits": 0,
        "after_hits": 0,
        "added_hits": 0,
        "removed_hits": 0,
        "changed_claims": 0,
    }
    now = _utcnow()
    for claim in claims:
        before = (claim.lead_id, claim.unit_candidate_key, claim.lease_end, claim.annual_rent_aed)
        rental = rentals.get(claim.property_key)
        after = (
            (
                str(rental["event_key"]),
                str(rental["unit_candidate_key"]),
                rental.get("lease_end"),
                int(rental.get("annual_rent_aed") or 0) or None,
            )
            if rental
            else (None, None, None, None)
        )
        counts["before_hits"] += bool(before[0])
        counts["after_hits"] += bool(after[0])
        counts["added_hits"] += bool(after[0]) and not before[0]
        counts["removed_hits"] += bool(before[0]) and not after[0]
        if before != after:
            (claim.lead_id, claim.unit_candidate_key, claim.lease_end, claim.annual_rent_aed) = (
                after
            )
            claim.updated_at = now
            db.add(claim)
            counts["changed_claims"] += 1
    await db.flush()
    import_ids = {claim.import_id for claim in claims}
    if import_id is not None:
        import_ids.add(import_id)
    await _refresh_contact_import_match_summaries(
        db,
        organization_id=organization_id,
        import_ids=import_ids,
    )
    if commit:
        await db.commit()
    _invalidate_owner_summary_cache(organization_id)
    return counts


def _price_matches(imported: int | None, observed: int) -> bool:
    if not imported or not observed:
        return True
    return abs(imported - observed) / observed <= 0.02


def _apply_evidence(
    candidate: ParsedContact,
    *,
    sales: dict[str, list[dict[str, Any]]],
    rentals: dict[str, dict[str, Any]],
) -> None:
    key = candidate.property_key
    sale_events = sales.get(key, [])
    rental = rentals.get(key)
    if rental:
        candidate.lead_id = str(rental["event_key"])
        candidate.unit_candidate_key = str(rental["unit_candidate_key"])
        candidate.lease_end = rental.get("lease_end")
        candidate.annual_rent_aed = int(rental.get("annual_rent_aed") or 0) or None

    latest = sale_events[-1] if sale_events else None
    if latest:
        candidate.latest_sale_date = latest["transaction_date"]
        candidate.latest_sale_price_aed = int(latest.get("sale_amount_aed") or 0) or None
        methods = sorted({str(event.get("_match_method") or "exact_building_key") for event in sale_events})
        candidate.evidence["sales_match"] = {
            "methods": methods,
            "matched_buildings": sorted(
                {str(event.get("building_name") or "") for event in sale_events if event.get("building_name")}
            ),
            "matched_sales": len(sale_events),
        }

    if candidate.party_role == "Seller":
        candidate.ownership_status = "former_owner"
        candidate.confidence_score = 100
        candidate.match_reason = (
            "The uploaded record identifies this contact as the seller, not the current buyer."
        )
        if candidate.transaction_date:
            candidate.later_sale_date = candidate.transaction_date
        return

    if not key:
        candidate.ownership_status = "insufficient_property_data"
        candidate.confidence_score = 0
        candidate.match_reason = (
            "The source row has transaction evidence but no recoverable unit/property "
            "identifier; registry matching requires source enrichment."
        )
        return

    if not latest:
        if rental:
            candidate.ownership_status = "unit_linked_unverified"
            candidate.confidence_score = 60
            candidate.match_reason = (
                "The contact links to an exact lease-opportunity unit, but acquisition "
                "evidence was not found in the sales registry."
            )
        else:
            lookup_status = str((candidate.evidence.get("sales_lookup") or {}).get("status") or "")
            if lookup_status == "unit_not_observed":
                candidate.ownership_status = "registry_not_observed"
                candidate.confidence_score = 10
                candidate.match_reason = (
                    "The source contains a usable unit identifier, but that unit is not "
                    "present in current DXBI sales-registry coverage."
                )
            else:
                candidate.match_reason = (
                    "Registry candidates exist for the unit, but the property location "
                    "could not be resolved unambiguously."
                )
        return

    identity_label = (
        "canonical building identity and unit"
        if any(str(event.get("_match_method")) != "exact_building_key" for event in sale_events)
        else "exact building and unit"
    )

    if not candidate.transaction_date:
        candidate.ownership_status = "unit_linked_unverified"
        candidate.confidence_score = 62 if rental else 55
        candidate.match_reason = (
            "The unit is exact, but the uploaded contact list does not provide an "
            "acquisition date or price."
        )
        return

    matched_event = next(
        (
            event
            for event in sale_events
            if abs((event["transaction_date"] - candidate.transaction_date).days) <= 2
        ),
        None,
    )
    if latest["transaction_date"] > candidate.transaction_date + timedelta(days=2):
        candidate.ownership_status = "former_owner"
        candidate.confidence_score = 99
        candidate.later_sale_date = latest["transaction_date"]
        candidate.match_reason = (
            f"A later sale was recorded on {latest['transaction_date']:%d %b %Y}; "
            "this contact is not presented as the current owner."
        )
        return

    if matched_event and not _price_matches(
        candidate.transaction_price_aed,
        int(matched_event.get("sale_amount_aed") or 0),
    ):
        candidate.ownership_status = "conflicting_claim"
        candidate.confidence_score = 45
        candidate.match_reason = (
            "The building, unit, and date match, but the uploaded price differs by more "
            "than 2% from the sales registry."
        )
        return

    if matched_event and candidate.transaction_price_aed:
        candidate.ownership_status = "verified_current_owner"
        candidate.confidence_score = 98
        candidate.match_reason = (
            f"{identity_label.title()}; acquisition date and price match the latest sale, "
            "with no later transfer observed."
        )
        return

    if matched_event:
        candidate.ownership_status = "probable_current_owner"
        candidate.confidence_score = 86
        candidate.match_reason = (
            f"{identity_label.title()}; acquisition date matches the latest sale and no "
            "later transfer is observed. Price evidence was unavailable."
        )
        return

    if candidate.transaction_date > latest["transaction_date"]:
        candidate.ownership_status = "probable_current_owner"
        candidate.confidence_score = 72
        candidate.match_reason = (
            "The exact unit matches, but the uploaded acquisition is newer than available "
            "sales-registry coverage and requires review."
        )
        return

    candidate.ownership_status = "conflicting_claim"
    candidate.confidence_score = 40
    candidate.match_reason = (
        "The unit is exact, but the uploaded acquisition date does not match the observed "
        "sales history."
    )


async def rematch_property_contact_claims(
    db: AsyncSession,
    *,
    organization_id: str,
    import_id: int | None = None,
    only_unmatched: bool = True,
    audit_resolution_methods: set[str] | None = None,
) -> dict[str, int]:
    """Re-evaluate saved owner claims against the current DXBI sales registry.

    Imports are immutable source records, but their evidence changes when either
    DXBI coverage improves or the building-identity resolver improves. This
    updates only calculated matching fields, never the uploaded contact data.
    """
    statement = select(CrmPropertyContactClaim).where(
        CrmPropertyContactClaim.organization_id == organization_id
    )
    if import_id is not None:
        statement = statement.where(CrmPropertyContactClaim.import_id == import_id)
    if audit_resolution_methods:
        statement = statement.where(
            CrmPropertyContactClaim.evidence["property_identity_resolution"][
                "method"
            ].as_string().in_(sorted(audit_resolution_methods))
        )
    elif only_unmatched:
        statement = statement.where(CrmPropertyContactClaim.ownership_status == "unmatched")
    claims = (await db.exec(statement)).all()
    candidates: list[ParsedContact] = []
    for claim in claims:
        claim_evidence = dict(claim.evidence or {})
        source_identity: dict[str, Any] = {}
        if audit_resolution_methods:
            prior_resolution = claim_evidence.get("property_identity_resolution")
            if isinstance(prior_resolution, dict) and prior_resolution.get(
                "method"
            ) in audit_resolution_methods:
                raw_source = prior_resolution.get("source")
                if isinstance(raw_source, dict):
                    source_identity = raw_source
            for calculated_key in (
                "property_identity_resolution",
                "unit_hierarchy_resolution",
                "sales_lookup",
                "sales_match",
            ):
                claim_evidence.pop(calculated_key, None)

        def identity_field(field_name: str, current: str) -> str:
            value = source_identity.get(field_name)
            return str(value) if value is not None else current

        candidate = ParsedContact(
            source_sheet=claim.source_sheet,
            source_row_number=claim.source_row_number,
            contact_name=claim.contact_name,
            phone_primary=claim.phone_primary,
            phone_alternate=claim.phone_alternate,
            email_primary=claim.email_primary,
            area_name=identity_field("area_name", claim.area_name),
            project_name=identity_field("project_name", claim.project_name),
            building_name=identity_field("building_name", claim.building_name),
            unit_number=identity_field("unit_number", claim.unit_number),
            property_type=claim.property_type,
            transaction_date=claim.transaction_date,
            transaction_price_aed=claim.transaction_price_aed,
            party_role=claim.party_role,
            procedure_type=claim.procedure_type,
            row_fingerprint=claim.row_fingerprint,
            evidence={
                key: value for key, value in claim_evidence.items() if key != "sales_match"
            },
        )
        _recover_embedded_property_identity(candidate)
        candidates.append(candidate)
    resolution_counts = await _recover_property_identity_from_transaction(candidates)
    near_resolution_counts = await _recover_property_identity_from_near_transaction(candidates)
    sales = await _sales_evidence(candidates)
    rentals = await _rental_evidence(candidates)
    now = _utcnow()
    status_counts: dict[str, int] = {}
    for claim, candidate in zip(claims, candidates, strict=True):
        _apply_evidence(candidate, sales=sales, rentals=rentals)
        claim.area_name = candidate.area_name
        claim.project_name = candidate.project_name
        claim.building_name = candidate.building_name
        claim.unit_number = candidate.unit_number
        claim.property_key = candidate.property_key
        claim.owner_key = _candidate_owner_key(candidate)
        claim.ownership_status = candidate.ownership_status
        claim.confidence_score = candidate.confidence_score
        claim.match_reason = candidate.match_reason
        claim.lead_id = candidate.lead_id
        claim.unit_candidate_key = candidate.unit_candidate_key
        claim.latest_sale_date = candidate.latest_sale_date
        claim.latest_sale_price_aed = candidate.latest_sale_price_aed
        claim.later_sale_date = candidate.later_sale_date
        claim.lease_end = candidate.lease_end
        claim.annual_rent_aed = candidate.annual_rent_aed
        claim.evidence = candidate.evidence
        claim.updated_at = now
        db.add(claim)
        status_counts[candidate.ownership_status] = (
            status_counts.get(candidate.ownership_status, 0) + 1
        )
    await db.flush()
    affected_import_ids = {claim.import_id for claim in claims}
    if import_id is not None:
        affected_import_ids.add(import_id)
    await _refresh_contact_import_match_summaries(
        db,
        organization_id=organization_id,
        import_ids=affected_import_ids,
    )
    await db.commit()
    _invalidate_owner_summary_cache(organization_id)
    return {
        "claims": len(claims),
        **{f"transaction_{key}": value for key, value in resolution_counts.items()},
        **{
            f"near_transaction_{key}": value
            for key, value in near_resolution_counts.items()
        },
        **status_counts,
    }


async def _refresh_contact_import_match_summaries(
    db: AsyncSession,
    *,
    organization_id: str,
    import_ids: set[int],
) -> dict[int, dict[str, int]]:
    """Synchronize persisted import cards with current claim evidence."""
    refreshed: dict[int, dict[str, int]] = {}
    if not import_ids:
        return refreshed

    import_result = await db.exec(
        select(CrmContactImport).where(
            CrmContactImport.organization_id == organization_id,
            CrmContactImport.id.in_(sorted(import_ids)),
        )
    )
    for record in import_result.all():
        record_id = record.id
        if record_id is None:
            continue
        status_result = await db.exec(
            select(CrmPropertyContactClaim.ownership_status, func.count())
            .where(
                CrmPropertyContactClaim.organization_id == organization_id,
                CrmPropertyContactClaim.import_id == record_id,
            )
            .group_by(CrmPropertyContactClaim.ownership_status)
        )
        status_counts = {str(status): int(count) for status, count in status_result.all()}
        has_contact = or_(
            CrmPropertyContactClaim.phone_primary.is_not(None),
            CrmPropertyContactClaim.phone_alternate.is_not(None),
            CrmPropertyContactClaim.email_primary.is_not(None),
        )
        metrics_result = await db.exec(
            select(
                func.count(),
                func.count().filter(has_contact),
                func.count().filter(CrmPropertyContactClaim.lead_id.is_not(None)),
                func.count().filter(
                    and_(
                        CrmPropertyContactClaim.lead_id.is_not(None),
                        has_contact,
                        CrmPropertyContactClaim.ownership_status.in_(
                            ("verified_current_owner", "probable_current_owner")
                        ),
                    )
                ),
            ).where(
                CrmPropertyContactClaim.organization_id == organization_id,
                CrmPropertyContactClaim.import_id == record_id,
            )
        )
        candidate_rows, valid_contacts, rental_opportunities, contact_ready = (
            int(value or 0) for value in metrics_result.one()
        )
        summary = dict(record.summary or {})
        summary.update(
            {
                "candidate_rows": candidate_rows,
                "valid_contacts": valid_contacts,
                "rental_opportunities": rental_opportunities,
                "contact_ready": contact_ready,
            }
        )
        for summary_field in _STATUS_SUMMARY_FIELDS.values():
            summary[summary_field] = 0
        for status, count in status_counts.items():
            summary_field = _STATUS_SUMMARY_FIELDS.get(status)
            if summary_field:
                summary[summary_field] = count
        validated = CrmContactImportSummary.model_validate(summary).model_dump()
        record.summary = validated
        db.add(record)
        refreshed[record_id] = {
            "candidate_rows": candidate_rows,
            **status_counts,
        }
    return refreshed


async def refresh_contact_import_match_summaries(
    db: AsyncSession,
    *,
    organization_id: str,
    import_id: int | None = None,
) -> dict[int, dict[str, int]]:
    """Refresh import-card summaries without re-running registry matching."""
    if import_id is not None:
        import_ids = {import_id}
    else:
        result = await db.exec(
            select(CrmContactImport.id).where(
                CrmContactImport.organization_id == organization_id
            )
        )
        import_ids = {record_id for record_id in result.all() if record_id is not None}
    refreshed = await _refresh_contact_import_match_summaries(
        db,
        organization_id=organization_id,
        import_ids=import_ids,
    )
    await db.commit()
    _invalidate_owner_summary_cache(organization_id)
    return refreshed


def _summary(
    candidates: list[ParsedContact],
    total_rows: int,
    duplicate_rows_collapsed: int = 0,
) -> CrmContactImportSummary:
    return CrmContactImportSummary(
        total_rows=total_rows,
        candidate_rows=len(candidates),
        duplicate_rows_collapsed=duplicate_rows_collapsed,
        valid_contacts=sum(candidate.has_valid_contact for candidate in candidates),
        verified_current_owners=sum(
            candidate.ownership_status == "verified_current_owner" for candidate in candidates
        ),
        probable_current_owners=sum(
            candidate.ownership_status == "probable_current_owner" for candidate in candidates
        ),
        unit_linked_unverified=sum(
            candidate.ownership_status == "unit_linked_unverified" for candidate in candidates
        ),
        former_owners=sum(candidate.ownership_status == "former_owner" for candidate in candidates),
        conflicting_claims=sum(
            candidate.ownership_status == "conflicting_claim" for candidate in candidates
        ),
        insufficient_property_data=sum(
            candidate.ownership_status == "insufficient_property_data"
            for candidate in candidates
        ),
        registry_not_observed=sum(
            candidate.ownership_status == "registry_not_observed" for candidate in candidates
        ),
        unmatched=sum(candidate.ownership_status == "unmatched" for candidate in candidates),
        rental_opportunities=sum(bool(candidate.lead_id) for candidate in candidates),
        contact_ready=sum(
            bool(candidate.lead_id)
            and candidate.has_valid_contact
            and candidate.ownership_status in {"verified_current_owner", "probable_current_owner"}
            for candidate in candidates
        ),
    )


async def _enrich_workspaces(
    db: AsyncSession,
    *,
    candidates: list[ParsedContact],
    user_id: str,
    organization_id: str,
    list_name: str,
) -> None:
    ready = [
        candidate
        for candidate in candidates
        if candidate.unit_candidate_key
        and candidate.lead_id
        and candidate.has_valid_contact
        and candidate.ownership_status in {"verified_current_owner", "probable_current_owner"}
    ]
    if not ready:
        return
    candidate_keys = sorted(
        {candidate.unit_candidate_key for candidate in ready if candidate.unit_candidate_key}
    )
    result = await db.exec(
        select(CrmLeadWorkspace).where(
            CrmLeadWorkspace.user_id == user_id,
            CrmLeadWorkspace.organization_id == organization_id,
            CrmLeadWorkspace.unit_candidate_key.in_(candidate_keys),  # type: ignore[union-attr]
        )
    )
    existing = {workspace.unit_candidate_key: workspace for workspace in result.all()}
    now = _utcnow()
    for candidate in ready:
        candidate_key = candidate.unit_candidate_key
        if not candidate_key:
            continue
        workspace = existing.get(candidate_key)
        if workspace is None:
            workspace = CrmLeadWorkspace(
                user_id=user_id,
                organization_id=organization_id,
                lead_id=candidate.lead_id or "",
                unit_candidate_key=candidate_key,
                pipeline_status="contact_ready",
                highlight_color="green",
                owner_name=candidate.contact_name,
                owner_email=candidate.email_primary,
                owner_phone=candidate.phone_primary or candidate.phone_alternate,
                tags=["Imported owner", list_name[:80]],
                created_at=now,
                updated_at=now,
            )
            db.add(workspace)
            existing[candidate_key] = workspace
            continue
        workspace.pipeline_status = (
            "contact_ready" if workspace.pipeline_status == "new" else workspace.pipeline_status
        )
        workspace.owner_name = workspace.owner_name or candidate.contact_name
        workspace.owner_email = workspace.owner_email or candidate.email_primary
        workspace.owner_phone = (
            workspace.owner_phone or candidate.phone_primary or candidate.phone_alternate
        )
        tags = list(workspace.tags or [])
        for tag in ("Imported owner", list_name[:80]):
            if tag not in tags and len(tags) < 12:
                tags.append(tag)
        workspace.tags = tags
        workspace.updated_at = now
        db.add(workspace)


def _mapping_response(profile: SheetProfile) -> dict[str, Any]:
    return CrmSheetMapping(
        sheet_name=profile.name,
        header_row=profile.header_row,
        meaningful_rows=profile.meaningful_rows,
        sheet_family=profile.sheet_family,
        mapping_source=profile.mapping_source,  # type: ignore[arg-type]
        confidence=profile.confidence,
        field_map=profile.field_map,
        warnings=profile.warnings,
    ).model_dump(mode="json")


async def process_contact_import(
    db: AsyncSession,
    *,
    upload: UploadFile,
    name: str,
    user_id: str,
    organization_id: str,
) -> CrmContactImportResponse:
    filename = Path(upload.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(status_code=400, detail="Upload an XLSX or CSV file")
    data = await upload.read(_MAX_FILE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The uploaded file exceeds 50 MB")
    sha256 = hashlib.sha256(data).hexdigest()
    existing_result = await db.exec(
        select(CrmContactImport).where(
            CrmContactImport.organization_id == organization_id,
            CrmContactImport.sha256 == sha256,
        )
    )
    existing = existing_result.first()
    if existing:
        return await _import_response(db, existing)

    now = _utcnow()
    record = CrmContactImport(
        organization_id=organization_id,
        created_by_user_id=user_id,
        name=name.strip()[:200] or Path(filename).stem[:200],
        original_filename=filename,
        sha256=sha256,
        size_bytes=len(data),
        status="processing",
        mapping={},
        summary={},
        created_at=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    if record.id is None:
        raise HTTPException(status_code=500, detail="Import record could not be created")

    try:
        inspector = _inspect_xlsx if suffix == ".xlsx" else _inspect_csv
        profiles = await asyncio.to_thread(inspector, data, filename)
        profiles = [await _llm_mapping(profile) for profile in profiles]
        parser = _parse_xlsx if suffix == ".xlsx" else _parse_csv
        candidates, total_rows = await asyncio.to_thread(parser, data, filename, profiles)
        await _recover_property_identity_from_transaction(candidates)
        await _recover_property_identity_from_near_transaction(candidates)
        sales = await _sales_evidence(candidates)
        rentals = await _rental_evidence(candidates)
        for candidate in candidates:
            _apply_evidence(candidate, sales=sales, rentals=rentals)
        candidates, duplicate_rows_collapsed = _dedupe_candidates(candidates)

        contact_list = CrmContactList(
            organization_id=organization_id,
            created_by_user_id=user_id,
            source_import_id=record.id,
            name=record.name,
            description=f"Imported from {filename}",
            created_at=now,
            updated_at=now,
        )
        db.add(contact_list)
        await db.flush()
        if contact_list.id is None:
            raise RuntimeError("Contact list could not be created")

        for start in range(0, len(candidates), 1_000):
            db.add_all(
                [
                    CrmPropertyContactClaim(
                        organization_id=organization_id,
                        import_id=record.id,
                        list_id=contact_list.id,
                        source_sheet=candidate.source_sheet,
                        source_row_number=candidate.source_row_number,
                        row_fingerprint=candidate.row_fingerprint,
                        owner_key=_candidate_owner_key(candidate),
                        property_key=candidate.property_key
                        or f"source:{candidate.row_fingerprint}",
                        contact_name=candidate.contact_name,
                        phone_primary=candidate.phone_primary,
                        phone_alternate=candidate.phone_alternate,
                        email_primary=candidate.email_primary,
                        area_name=candidate.area_name,
                        project_name=candidate.project_name,
                        building_name=candidate.building_name,
                        unit_number=candidate.unit_number,
                        property_type=candidate.property_type,
                        transaction_date=candidate.transaction_date,
                        transaction_price_aed=candidate.transaction_price_aed,
                        party_role=candidate.party_role,
                        procedure_type=candidate.procedure_type,
                        ownership_status=candidate.ownership_status,
                        confidence_score=candidate.confidence_score,
                        match_reason=candidate.match_reason,
                        lead_id=candidate.lead_id,
                        unit_candidate_key=candidate.unit_candidate_key,
                        latest_sale_date=candidate.latest_sale_date,
                        latest_sale_price_aed=candidate.latest_sale_price_aed,
                        later_sale_date=candidate.later_sale_date,
                        lease_end=candidate.lease_end,
                        annual_rent_aed=candidate.annual_rent_aed,
                        evidence=candidate.evidence,
                        created_at=now,
                        updated_at=now,
                    )
                    for candidate in candidates[start : start + 1_000]
                ]
            )
            await db.flush()

        await _enrich_workspaces(
            db,
            candidates=candidates,
            user_id=user_id,
            organization_id=organization_id,
            list_name=record.name,
        )
        summary = _summary(candidates, total_rows, duplicate_rows_collapsed)
        record.status = "completed"
        record.mapping = {"sheets": [_mapping_response(profile) for profile in profiles]}
        record.summary = summary.model_dump()
        record.completed_at = _utcnow()
        db.add(record)
        await db.commit()
        _invalidate_owner_summary_cache(organization_id)
        return await _import_response(db, record)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("CRM contact import failed", extra={"import_id": record.id})
        await db.rollback()
        record.status = "failed"
        record.error_message = str(exc)[:2_000]
        record.completed_at = _utcnow()
        db.add(record)
        await db.commit()
        raise HTTPException(status_code=422, detail=f"Import failed: {exc}") from exc


async def _import_response(
    db: AsyncSession,
    record: CrmContactImport,
) -> CrmContactImportResponse:
    list_result = await db.exec(
        select(CrmContactList).where(CrmContactList.source_import_id == record.id)
    )
    contact_list = list_result.first()
    raw_sheets = record.mapping.get("sheets", []) if record.mapping else []
    return CrmContactImportResponse(
        id=record.id or 0,
        list_id=contact_list.id if contact_list else None,
        name=record.name,
        original_filename=record.original_filename,
        status=record.status,  # type: ignore[arg-type]
        summary=CrmContactImportSummary.model_validate(record.summary or {}),
        mappings=[CrmSheetMapping.model_validate(item) for item in raw_sheets],
        error_message=record.error_message,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


async def list_contact_imports(
    db: AsyncSession,
    *,
    organization_id: str,
) -> list[CrmContactImportResponse]:
    result = await db.exec(
        select(CrmContactImport)
        .where(CrmContactImport.organization_id == organization_id)
        .order_by(CrmContactImport.created_at.desc())
    )
    return [await _import_response(db, record) for record in result.all()]


async def rename_contact_import(
    db: AsyncSession,
    *,
    import_id: int,
    name: str,
    organization_id: str,
) -> CrmContactImportResponse:
    result = await db.exec(
        select(CrmContactImport).where(
            CrmContactImport.id == import_id,
            CrmContactImport.organization_id == organization_id,
        )
    )
    record = result.first()
    if not record:
        raise HTTPException(status_code=404, detail="Owner-data import not found")
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Import name cannot be empty")
    record.name = cleaned[:200]
    db.add(record)
    list_result = await db.exec(
        select(CrmContactList).where(
            CrmContactList.source_import_id == import_id,
            CrmContactList.organization_id == organization_id,
        )
    )
    contact_list = list_result.first()
    if contact_list:
        contact_list.name = record.name
        contact_list.updated_at = _utcnow()
        db.add(contact_list)
    await db.commit()
    await db.refresh(record)
    return await _import_response(db, record)


async def delete_contact_import(
    db: AsyncSession,
    *,
    import_id: int,
    organization_id: str,
) -> None:
    result = await db.exec(
        select(CrmContactImport).where(
            CrmContactImport.id == import_id,
            CrmContactImport.organization_id == organization_id,
        )
    )
    record = result.first()
    if not record:
        raise HTTPException(status_code=404, detail="Owner-data import not found")

    # Remove only records published by this import. Agent-maintained lead
    # workspaces, notes, and manually saved properties are intentionally kept.
    await db.exec(
        delete(CrmPropertyContactClaim).where(
            CrmPropertyContactClaim.import_id == import_id,
            CrmPropertyContactClaim.organization_id == organization_id,
        )
    )
    await db.exec(
        delete(CrmContactList).where(
            CrmContactList.source_import_id == import_id,
            CrmContactList.organization_id == organization_id,
        )
    )
    await db.delete(record)
    await db.commit()
    _invalidate_owner_summary_cache(organization_id)


def _claim_property_key(claim: CrmPropertyContactClaim) -> str:
    if claim.property_key:
        return claim.property_key
    location = claim.building_name or claim.project_name
    if not location or not claim.unit_number:
        return f"claim:{claim.id or claim.row_fingerprint}"
    return f"{_location_key(location)}|{claim.unit_number.casefold()}"


def _claim_owner_key(claim: CrmPropertyContactClaim) -> str:
    if claim.owner_key:
        return claim.owner_key
    return _owner_key(
        contact_name=claim.contact_name,
        phone_primary=claim.phone_primary,
        phone_alternate=claim.phone_alternate,
        email_primary=claim.email_primary,
        property_key=_claim_property_key(claim),
    )


def _claim_preference(claim: CrmPropertyContactClaim) -> tuple[int, int, int, int]:
    return (
        _OWNERSHIP_PRIORITY.get(claim.ownership_status, 0),
        claim.confidence_score,
        1 if claim.phone_primary or claim.phone_alternate or claim.email_primary else 0,
        claim.transaction_date.toordinal() if claim.transaction_date else 0,
    )


def _dedupe_claims(
    claims: list[CrmPropertyContactClaim],
) -> list[list[CrmPropertyContactClaim]]:
    grouped: dict[tuple[str, str], list[CrmPropertyContactClaim]] = {}
    for claim in claims:
        grouped.setdefault(
            (_claim_owner_key(claim), _claim_property_key(claim)),
            [],
        ).append(claim)
    groups = list(grouped.values())
    groups.sort(
        key=lambda group: _claim_preference(max(group, key=_claim_preference)), reverse=True
    )
    return groups


def _claim_source_rows(group: list[CrmPropertyContactClaim]) -> list[str]:
    values = {f"{claim.source_sheet}:{claim.source_row_number}" for claim in group}
    for claim in group:
        source_rows = claim.evidence.get("source_rows", []) if claim.evidence else []
        if isinstance(source_rows, list):
            values.update(str(item) for item in source_rows if item)
    return sorted(values)


def _claim_duplicate_count(group: list[CrmPropertyContactClaim]) -> int:
    persisted = [
        int(claim.evidence.get("duplicate_count", 1))
        for claim in group
        if claim.evidence and isinstance(claim.evidence.get("duplicate_count", 1), int)
    ]
    return max(len(group), max(persisted, default=1))


def _claim_response(
    claim: CrmPropertyContactClaim,
    group: list[CrmPropertyContactClaim] | None = None,
) -> CrmContactClaimResponse:
    if claim.id is None:
        raise HTTPException(status_code=500, detail="Imported contact is missing an id")
    grouped = group or [claim]
    return CrmContactClaimResponse(
        id=claim.id,
        source_sheet=claim.source_sheet,
        source_row_number=claim.source_row_number,
        contact_name=claim.contact_name,
        phone_primary=claim.phone_primary,
        phone_alternate=claim.phone_alternate,
        email_primary=claim.email_primary,
        area_name=claim.area_name,
        project_name=claim.project_name,
        building_name=claim.building_name,
        unit_number=claim.unit_number,
        property_type=claim.property_type,
        transaction_date=claim.transaction_date,
        transaction_price_aed=claim.transaction_price_aed,
        ownership_status=claim.ownership_status,  # type: ignore[arg-type]
        confidence_score=claim.confidence_score,
        match_reason=claim.match_reason,
        lead_id=claim.lead_id,
        unit_candidate_key=claim.unit_candidate_key,
        latest_sale_date=claim.latest_sale_date,
        latest_sale_price_aed=claim.latest_sale_price_aed,
        later_sale_date=claim.later_sale_date,
        lease_end=claim.lease_end,
        annual_rent_aed=claim.annual_rent_aed,
        owner_key=_claim_owner_key(claim),
        duplicate_count=_claim_duplicate_count(grouped),
        source_rows=_claim_source_rows(grouped),
    )


def _list_summary(
    contact_list: CrmContactList,
    claims: list[CrmPropertyContactClaim],
) -> CrmContactListSummary:
    if contact_list.id is None:
        raise HTTPException(status_code=500, detail="CRM contact list is missing an id")
    unique_claims = [max(group, key=_claim_preference) for group in _dedupe_claims(claims)]
    return CrmContactListSummary(
        id=contact_list.id,
        source_import_id=contact_list.source_import_id,
        name=contact_list.name,
        description=contact_list.description,
        total_contacts=len(unique_claims),
        contact_ready=sum(
            bool(claim.lead_id)
            and bool(claim.phone_primary or claim.phone_alternate or claim.email_primary)
            and claim.ownership_status in {"verified_current_owner", "probable_current_owner"}
            for claim in unique_claims
        ),
        needs_review=sum(
            claim.ownership_status
            in {
                "unit_linked_unverified",
                "conflicting_claim",
                "insufficient_property_data",
                "registry_not_observed",
            }
            for claim in unique_claims
        ),
        former_owners=sum(claim.ownership_status == "former_owner" for claim in unique_claims),
        created_at=contact_list.created_at,
        updated_at=contact_list.updated_at,
    )


async def list_contact_lists(
    db: AsyncSession,
    *,
    organization_id: str,
) -> list[CrmContactListSummary]:
    list_result = await db.exec(
        select(CrmContactList)
        .where(CrmContactList.organization_id == organization_id)
        .order_by(CrmContactList.updated_at.desc())
    )
    contact_lists = list(list_result.all())
    if not contact_lists:
        return []
    ids = [item.id for item in contact_lists if item.id is not None]
    claim_result = await db.exec(
        select(CrmPropertyContactClaim).where(
            CrmPropertyContactClaim.organization_id == organization_id,
            CrmPropertyContactClaim.list_id.in_(ids),  # type: ignore[union-attr]
        )
    )
    grouped: dict[int, list[CrmPropertyContactClaim]] = {}
    for claim in claim_result.all():
        grouped.setdefault(claim.list_id, []).append(claim)
    return [_list_summary(item, grouped.get(item.id or 0, [])) for item in contact_lists]


async def get_contact_list(
    db: AsyncSession,
    *,
    list_id: int,
    organization_id: str,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> CrmContactListDetail:
    list_result = await db.exec(
        select(CrmContactList).where(
            CrmContactList.id == list_id,
            CrmContactList.organization_id == organization_id,
        )
    )
    contact_list = list_result.first()
    if not contact_list:
        raise HTTPException(status_code=404, detail="CRM contact list not found")
    statement = select(CrmPropertyContactClaim).where(
        CrmPropertyContactClaim.organization_id == organization_id,
        CrmPropertyContactClaim.list_id == list_id,
    )
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                CrmPropertyContactClaim.contact_name.ilike(term),
                CrmPropertyContactClaim.building_name.ilike(term),
                CrmPropertyContactClaim.project_name.ilike(term),
                CrmPropertyContactClaim.unit_number.ilike(term),
            )
        )
    all_result = await db.exec(statement)
    matching_groups = _dedupe_claims(list(all_result.all()))
    if status:
        matching_groups = [
            group
            for group in matching_groups
            if max(group, key=_claim_preference).ownership_status == status
        ]
    visible = matching_groups[offset : offset + limit]
    all_list_result = await db.exec(
        select(CrmPropertyContactClaim).where(
            CrmPropertyContactClaim.organization_id == organization_id,
            CrmPropertyContactClaim.list_id == list_id,
        )
    )
    all_list_claims = list(all_list_result.all())
    return CrmContactListDetail(
        list=_list_summary(contact_list, all_list_claims),
        contacts=[_claim_response(max(group, key=_claim_preference), group) for group in visible],
        total=len(matching_groups),
        limit=limit,
        offset=offset,
    )


async def list_lead_imported_contacts(
    db: AsyncSession,
    *,
    lead_id: str,
    organization_id: str,
) -> list[CrmLeadImportedContact]:
    result = await db.exec(
        select(CrmPropertyContactClaim, CrmContactList)
        .join(CrmContactList, CrmContactList.id == CrmPropertyContactClaim.list_id)
        .where(
            CrmPropertyContactClaim.organization_id == organization_id,
            CrmPropertyContactClaim.lead_id == lead_id,
        )
        .order_by(CrmPropertyContactClaim.confidence_score.desc())
    )
    rows = list(result.all())
    grouped: dict[tuple[str, str], list[tuple[CrmPropertyContactClaim, CrmContactList]]] = {}
    for claim, contact_list in rows:
        grouped.setdefault(
            (_claim_owner_key(claim), _claim_property_key(claim)),
            [],
        ).append((claim, contact_list))

    # A lead drawer only needs portfolio counts for the owners attached to that
    # lead. Loading and de-duplicating every imported claim made this endpoint
    # progressively slower as an organization's owner registry grew.
    owner_keys = {_claim_owner_key(claim) for claim, _ in rows}
    property_counts: dict[str, int] = {}
    if owner_keys:
        property_count_result = await db.exec(
            select(
                CrmPropertyContactClaim.owner_key,
                func.count(func.distinct(CrmPropertyContactClaim.property_key)),
            )
            .where(
                CrmPropertyContactClaim.organization_id == organization_id,
                CrmPropertyContactClaim.owner_key.in_(owner_keys),
            )
            .group_by(CrmPropertyContactClaim.owner_key)
        )
        property_counts = {
            str(owner_key): int(property_count)
            for owner_key, property_count in property_count_result.all()
        }

    contacts: list[CrmLeadImportedContact] = []
    for group_rows in grouped.values():
        claim_group = [claim for claim, _ in group_rows]
        claim = max(claim_group, key=_claim_preference)
        contact_list = next(
            contact_list for candidate, contact_list in group_rows if candidate.id == claim.id
        )
        if claim.id is None or contact_list.id is None:
            continue
        owner_key = _claim_owner_key(claim)
        contacts.append(
            CrmLeadImportedContact(
                claim_id=claim.id,
                list_id=contact_list.id,
                list_name=contact_list.name,
                contact_name=claim.contact_name,
                phone_primary=claim.phone_primary,
                phone_alternate=claim.phone_alternate,
                email_primary=claim.email_primary,
                ownership_status=claim.ownership_status,  # type: ignore[arg-type]
                confidence_score=claim.confidence_score,
                match_reason=claim.match_reason,
                source_sheet=claim.source_sheet,
                imported_at=claim.created_at,
                owner_key=owner_key,
                duplicate_count=_claim_duplicate_count(claim_group),
                property_count=property_counts.get(owner_key, 1),
                source_lists=sorted({item.name for _, item in group_rows}),
            )
        )
    contacts.sort(key=lambda item: (item.confidence_score, item.property_count), reverse=True)
    return contacts


def _group_claim_rows(
    rows: list[tuple[CrmPropertyContactClaim, CrmContactList]],
) -> dict[str, list[list[tuple[CrmPropertyContactClaim, CrmContactList]]]]:
    properties: dict[
        tuple[str, str],
        list[tuple[CrmPropertyContactClaim, CrmContactList]],
    ] = {}
    for claim, contact_list in rows:
        properties.setdefault(
            (_claim_owner_key(claim), _claim_property_key(claim)),
            [],
        ).append((claim, contact_list))
    owners: dict[str, list[list[tuple[CrmPropertyContactClaim, CrmContactList]]]] = {}
    for (owner_key, _), property_rows in properties.items():
        owners.setdefault(owner_key, []).append(property_rows)
    return owners


def _is_rental_ready_claim(claim: CrmPropertyContactClaim) -> bool:
    return bool(claim.lead_id) and claim.ownership_status in {
        "verified_current_owner",
        "probable_current_owner",
    }


def _property_from_rows(
    rows: list[tuple[CrmPropertyContactClaim, CrmContactList]],
) -> CrmOwnerProperty:
    claims = [claim for claim, _ in rows]
    best = max(claims, key=_claim_preference)
    return CrmOwnerProperty(
        property_key=_claim_property_key(best),
        area_name=best.area_name,
        project_name=best.project_name,
        building_name=best.building_name,
        unit_number=best.unit_number,
        property_type=best.property_type,
        ownership_status=best.ownership_status,  # type: ignore[arg-type]
        confidence_score=best.confidence_score,
        match_reason=best.match_reason,
        lead_id=best.lead_id,
        unit_candidate_key=best.unit_candidate_key,
        imported_transaction_date=best.transaction_date,
        imported_transaction_price_aed=best.transaction_price_aed,
        imported_property_type=best.property_type,
        latest_sale_date=best.latest_sale_date,
        latest_sale_price_aed=best.latest_sale_price_aed,
        registry_sale_date=best.latest_sale_date,
        registry_sale_price_aed=best.latest_sale_price_aed,
        later_sale_date=best.later_sale_date,
        lease_end=best.lease_end,
        annual_rent_aed=best.annual_rent_aed,
        duplicate_count=_claim_duplicate_count(claims),
        source_lists=sorted({contact_list.name for _, contact_list in rows}),
        source_rows=_claim_source_rows(claims),
    )


def _owner_profile(
    owner_key: str,
    property_groups: list[list[tuple[CrmPropertyContactClaim, CrmContactList]]],
) -> CrmOwnerProfile:
    claims = [claim for group in property_groups for claim, _ in group]
    best = max(claims, key=_claim_preference)
    properties = [_property_from_rows(group) for group in property_groups]
    properties.sort(
        key=lambda item: (
            1 if item.lead_id else 0,
            item.confidence_score,
            -(item.lease_end.toordinal() if item.lease_end else 0),
        ),
        reverse=True,
    )
    phones = list(
        dict.fromkeys(
            value
            for claim in claims
            for value in (claim.phone_primary, claim.phone_alternate)
            if value
        )
    )
    emails = list(dict.fromkeys(claim.email_primary for claim in claims if claim.email_primary))
    rental_properties = [item for item in properties if item.lead_id]
    contact_ready = [
        item
        for item in properties
        if item.lead_id
        and item.ownership_status in {"verified_current_owner", "probable_current_owner"}
    ]
    lease_dates = [item.lease_end for item in rental_properties if item.lease_end]
    return CrmOwnerProfile(
        owner_key=owner_key,
        contact_name=best.contact_name,
        phone_primary=phones[0] if phones else None,
        phone_alternate=phones[1] if len(phones) > 1 else None,
        email_primary=emails[0] if emails else None,
        highest_ownership_status=best.ownership_status,  # type: ignore[arg-type]
        highest_confidence_score=best.confidence_score,
        property_count=len(properties),
        rental_linked_count=len(rental_properties),
        contact_ready_count=len(contact_ready),
        annual_rent_aed=sum(item.annual_rent_aed or 0 for item in rental_properties),
        next_lease_end=min(lease_dates) if lease_dates else None,
        properties=properties,
    )


def _profile_matches_scope(profile: CrmOwnerProfile, scope: str) -> bool:
    ready_properties = [
        item
        for item in profile.properties
        if item.lead_id
        and item.ownership_status in {"verified_current_owner", "probable_current_owner"}
    ]
    if scope == "rental_ready":
        return bool(ready_properties)
    if scope == "registry":
        return len(ready_properties) < len(profile.properties)
    return True


def _profile_for_scope(profile: CrmOwnerProfile, scope: str) -> CrmOwnerProfile:
    if scope == "all":
        return profile
    properties = [
        item
        for item in profile.properties
        if (
            item.lead_id
            and item.ownership_status in {"verified_current_owner", "probable_current_owner"}
        )
        == (scope == "rental_ready")
    ]
    if not properties:
        return profile
    best = max(
        properties,
        key=lambda item: (
            _OWNERSHIP_PRIORITY.get(item.ownership_status, 0),
            item.confidence_score,
        ),
    )
    rental_properties = [item for item in properties if item.lead_id]
    lease_dates = [item.lease_end for item in rental_properties if item.lease_end]
    return profile.model_copy(
        update={
            "highest_ownership_status": best.ownership_status,
            "highest_confidence_score": best.confidence_score,
            "property_count": len(properties),
            "rental_linked_count": len(rental_properties),
            "contact_ready_count": sum(
                bool(item.lead_id)
                and item.ownership_status in {"verified_current_owner", "probable_current_owner"}
                for item in properties
            ),
            "annual_rent_aed": sum(item.annual_rent_aed or 0 for item in rental_properties),
            "next_lease_end": min(lease_dates) if lease_dates else None,
            "properties": properties,
        }
    )


async def _all_owner_profiles(
    db: AsyncSession,
    *,
    organization_id: str,
) -> list[CrmOwnerProfile]:
    result = await db.exec(
        select(CrmPropertyContactClaim, CrmContactList)
        .join(CrmContactList, CrmContactList.id == CrmPropertyContactClaim.list_id)
        .where(CrmPropertyContactClaim.organization_id == organization_id)
    )
    owners = _group_claim_rows(list(result.all()))
    return [
        _owner_profile(owner_key, property_groups) for owner_key, property_groups in owners.items()
    ]


def _owner_registry_summary(
    profiles: list[CrmOwnerProfile],
) -> CrmOwnerRegistrySummary:
    return CrmOwnerRegistrySummary(
        rental_owner_profiles=sum(
            any(
                item.lead_id
                and item.ownership_status in {"verified_current_owner", "probable_current_owner"}
                for item in profile.properties
            )
            for profile in profiles
        ),
        registry_owner_profiles=sum(
            any(
                not (
                    item.lead_id
                    and item.ownership_status
                    in {"verified_current_owner", "probable_current_owner"}
                )
                and item.ownership_status != "former_owner"
                for item in profile.properties
            )
            for profile in profiles
        ),
        prior_owner_profiles=sum(
            any(item.ownership_status == "former_owner" for item in profile.properties)
            for profile in profiles
        ),
        needs_review_profiles=sum(
            any(
                item.ownership_status
                in {
                    "unit_linked_unverified",
                    "conflicting_claim",
                    "insufficient_property_data",
                    "registry_not_observed",
                    "unmatched",
                }
                for item in profile.properties
            )
            for profile in profiles
        ),
        multi_property_owners=sum(profile.property_count > 1 for profile in profiles),
    )


def _owner_scope_clause(scope: str, alias: str = "p") -> str:
    ready = (
        f"{alias}.lead_id IS NOT NULL AND "
        f"{alias}.ownership_status IN "
        "('verified_current_owner', 'probable_current_owner')"
    )
    if scope == "rental_ready":
        return ready
    if scope == "prior_owners":
        return f"{alias}.ownership_status = 'former_owner'"
    if scope == "registry":
        return f"NOT ({ready}) AND {alias}.ownership_status <> 'former_owner'"
    return "TRUE"


def _owner_filter_sql(
    *,
    scope: str,
    status: str | None,
    search: str | None,
    lease_window: str | None = None,
    min_rent_aed: int | None = None,
    max_rent_aed: int | None = None,
    min_value_aed: int | None = None,
    max_value_aed: int | None = None,
    alias: str = "p",
) -> tuple[str, dict[str, Any]]:
    clauses = [_owner_scope_clause(scope, alias)]
    parameters: dict[str, Any] = {}
    if status:
        clauses.append(f"{alias}.ownership_status = :owner_status")
        parameters["owner_status"] = status
    if search:
        clauses.append(
            "lower(concat_ws(' ', "
            f"{alias}.contact_name, {alias}.phone_primary, "
            f"{alias}.phone_alternate, {alias}.email_primary, "
            f"{alias}.building_name, {alias}.project_name, "
            f"{alias}.area_name, {alias}.unit_number"
            ")) LIKE :owner_search"
        )
        parameters["owner_search"] = f"%{search.casefold().strip()}%"
    if lease_window == "expired":
        clauses.append(f"{alias}.lease_end < CURRENT_DATE")
    elif lease_window in {"expiring_30", "expiring_60", "expiring_90"}:
        lower_days, upper_days = {
            "expiring_30": (0, 30),
            "expiring_60": (30, 60),
            "expiring_90": (60, 90),
        }[lease_window]
        clauses.append(
            f"{alias}.lease_end > CURRENT_DATE + make_interval(days => :lease_lower_days)"
        )
        clauses.append(
            f"{alias}.lease_end <= CURRENT_DATE + make_interval(days => :lease_upper_days)"
        )
        parameters["lease_lower_days"] = lower_days
        parameters["lease_upper_days"] = upper_days
    if min_rent_aed is not None:
        clauses.append(f"{alias}.annual_rent_aed >= :owner_min_rent")
        parameters["owner_min_rent"] = min_rent_aed
    if max_rent_aed is not None:
        clauses.append(f"{alias}.annual_rent_aed <= :owner_max_rent")
        parameters["owner_max_rent"] = max_rent_aed
    if min_value_aed is not None:
        clauses.append(f"{alias}.latest_sale_price_aed >= :owner_min_value")
        parameters["owner_min_value"] = min_value_aed
    if max_value_aed is not None:
        clauses.append(f"{alias}.latest_sale_price_aed <= :owner_max_value")
        parameters["owner_max_value"] = max_value_aed
    return " AND ".join(f"({clause})" for clause in clauses), parameters


async def _owner_registry_summary_sql(
    db: AsyncSession,
    *,
    organization_id: str,
    list_id: int | None,
) -> CrmOwnerRegistrySummary:
    cache_key = (organization_id, list_id)
    cached = _owner_summary_cache.get(cache_key)
    if cached and monotonic() - cached[0] < _OWNER_SUMMARY_CACHE_TTL_SECONDS:
        return cached[1]
    statement = text(
        _OWNER_REGISTRY_BASE_SQL
        + """
        , profile_rollup AS (
            SELECT
                owner_key_sql,
                count(*) AS property_count,
                count(*) FILTER (
                    WHERE lead_id IS NOT NULL
                    AND ownership_status IN (
                        'verified_current_owner',
                        'probable_current_owner'
                    )
                ) AS rental_ready_count,
                count(*) FILTER (
                    WHERE NOT (
                        lead_id IS NOT NULL
                        AND ownership_status IN (
                            'verified_current_owner',
                            'probable_current_owner'
                        )
                    )
                    AND ownership_status <> 'former_owner'
                ) AS registry_count,
                count(*) FILTER (
                    WHERE ownership_status = 'former_owner'
                ) AS prior_count,
                count(*) FILTER (
                    WHERE ownership_status IN (
                        'unit_linked_unverified',
                        'conflicting_claim',
                        'insufficient_property_data',
                        'registry_not_observed',
                        'unmatched'
                    )
                ) AS review_count
            FROM properties
            GROUP BY owner_key_sql
        )
        SELECT
            count(*) FILTER (WHERE rental_ready_count > 0)
                AS rental_owner_profiles,
            count(*) FILTER (WHERE registry_count > 0)
                AS registry_owner_profiles,
            count(*) FILTER (WHERE prior_count > 0)
                AS prior_owner_profiles,
            count(*) FILTER (WHERE review_count > 0)
                AS needs_review_profiles,
            count(*) FILTER (WHERE property_count > 1)
                AS multi_property_owners
        FROM profile_rollup
        """
    )
    row = (
        await db.exec(
            statement,
            params={"organization_id": organization_id, "owner_list_id": list_id},
        )
    ).mappings().one()
    summary = CrmOwnerRegistrySummary(
        rental_owner_profiles=int(row["rental_owner_profiles"] or 0),
        registry_owner_profiles=int(row["registry_owner_profiles"] or 0),
        prior_owner_profiles=int(row["prior_owner_profiles"] or 0),
        needs_review_profiles=int(row["needs_review_profiles"] or 0),
        multi_property_owners=int(row["multi_property_owners"] or 0),
    )
    _owner_summary_cache[cache_key] = (monotonic(), summary)
    return summary


async def _owner_page_keys_sql(
    db: AsyncSession,
    *,
    organization_id: str,
    list_id: int | None,
    scope: str,
    status: str | None,
    search: str | None,
    lease_window: str | None,
    portfolio_only: bool,
    min_rent_aed: int | None,
    max_rent_aed: int | None,
    min_value_aed: int | None,
    max_value_aed: int | None,
    limit: int,
    offset: int,
) -> tuple[list[str], int]:
    where_sql, parameters = _owner_filter_sql(
        scope=scope,
        status=status,
        search=search,
        lease_window=lease_window,
        min_rent_aed=min_rent_aed,
        max_rent_aed=max_rent_aed,
        min_value_aed=min_value_aed,
        max_value_aed=max_value_aed,
    )
    statement = text(
        _OWNER_REGISTRY_BASE_SQL
        + f"""
        , scoped_properties AS (
            SELECT p.* FROM properties p WHERE {where_sql}
        ),
        profile_rollup AS (
            SELECT
                owner_key_sql,
                count(*) AS property_count,
                count(*) FILTER (WHERE lead_id IS NOT NULL)
                    AS rental_linked_count,
                count(*) FILTER (
                    WHERE lead_id IS NOT NULL
                    AND ownership_status IN (
                        'verified_current_owner',
                        'probable_current_owner'
                    )
                ) AS contact_ready_count,
                max(confidence_score) AS highest_confidence_score,
                min(lease_end) FILTER (WHERE lease_end IS NOT NULL)
                    AS next_lease_end
            FROM scoped_properties
            GROUP BY owner_key_sql
        )
        SELECT
            owner_key_sql,
            count(*) OVER () AS total_profiles
        FROM profile_rollup
        WHERE (NOT :portfolio_only OR property_count > 1)
        ORDER BY
            contact_ready_count DESC,
            property_count DESC,
            highest_confidence_score DESC,
            next_lease_end ASC NULLS LAST,
            owner_key_sql
        LIMIT :owner_limit OFFSET :owner_offset
        """
    )
    parameters.update(
        {
            "organization_id": organization_id,
            "owner_list_id": list_id,
            "portfolio_only": portfolio_only,
            "owner_limit": limit,
            "owner_offset": offset,
        }
    )
    rows = (await db.exec(statement, params=parameters)).mappings().all()
    return (
        [str(row["owner_key_sql"]) for row in rows],
        int(rows[0]["total_profiles"]) if rows else 0,
    )


async def _owner_properties_sql(
    db: AsyncSession,
    *,
    organization_id: str,
    list_id: int | None,
    owner_keys: list[str],
    scope: str,
    status: str | None = None,
    search: str | None = None,
    lease_window: str | None = None,
    min_rent_aed: int | None = None,
    max_rent_aed: int | None = None,
    min_value_aed: int | None = None,
    max_value_aed: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not owner_keys:
        return {}
    where_sql, parameters = _owner_filter_sql(
        scope=scope,
        status=status,
        search=search,
        lease_window=lease_window,
        min_rent_aed=min_rent_aed,
        max_rent_aed=max_rent_aed,
        min_value_aed=min_value_aed,
        max_value_aed=max_value_aed,
    )
    statement = text(
        _OWNER_REGISTRY_BASE_SQL
        + f"""
        , limited_properties AS (
            SELECT DISTINCT ON (owner_key_sql, property_key_sql)
                *
            FROM base
            WHERE owner_key_sql = ANY(:owner_keys)
            ORDER BY
                owner_key_sql,
                property_key_sql,
                status_rank DESC,
                confidence_score DESC,
                transaction_date DESC NULLS LAST
        ),
        limited_source_aggregation AS (
            SELECT
                c.owner_key AS owner_key_sql,
                c.property_key AS property_key_sql,
                count(*) AS duplicate_count,
                array_agg(DISTINCT l.name ORDER BY l.name)
                    AS source_lists,
                array_agg(
                    DISTINCT c.source_sheet || ':' || c.source_row_number::text
                    ORDER BY c.source_sheet || ':' || c.source_row_number::text
                ) AS source_rows
            FROM crm_property_contact_claims c
            INNER JOIN crm_contact_lists l ON l.id = c.list_id
            WHERE c.organization_id = :organization_id
              AND (
                CAST(:owner_list_id AS INTEGER) IS NULL
                OR c.list_id = CAST(:owner_list_id AS INTEGER)
              )
              AND c.owner_key = ANY(:owner_keys)
            GROUP BY c.owner_key, c.property_key
        ),
        scoped_properties AS (
            SELECT p.* FROM limited_properties p WHERE {where_sql}
        )
        SELECT
            p.*,
            a.duplicate_count,
            a.source_lists,
            a.source_rows
        FROM scoped_properties p
        INNER JOIN limited_source_aggregation a
            ON a.owner_key_sql = p.owner_key_sql
            AND a.property_key_sql = p.property_key_sql
        WHERE p.owner_key_sql = ANY(:owner_keys)
        ORDER BY
            p.owner_key_sql,
            p.status_rank DESC,
            p.confidence_score DESC,
            p.lease_end ASC NULLS LAST
        """
    )
    parameters.update(
        {
            "organization_id": organization_id,
            "owner_list_id": list_id,
            "owner_keys": owner_keys,
        }
    )
    rows = (await db.exec(statement, params=parameters)).mappings().all()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["owner_key_sql"]), []).append(dict(row))
    return grouped


def _sql_owner_property(row: dict[str, Any]) -> CrmOwnerProperty:
    return CrmOwnerProperty(
        property_key=str(row["property_key_sql"]),
        area_name=str(row["area_name"] or ""),
        project_name=str(row["project_name"] or ""),
        building_name=str(row["building_name"] or ""),
        unit_number=str(row["unit_number"] or ""),
        property_type=str(row["property_type"] or ""),
        ownership_status=str(row["ownership_status"]),  # type: ignore[arg-type]
        confidence_score=int(row["confidence_score"] or 0),
        match_reason=str(row["match_reason"] or ""),
        lead_id=str(row["lead_id"]) if row["lead_id"] else None,
        unit_candidate_key=(str(row["unit_candidate_key"]) if row["unit_candidate_key"] else None),
        imported_transaction_date=row["transaction_date"],
        imported_transaction_price_aed=(
            int(row["transaction_price_aed"]) if row["transaction_price_aed"] else None
        ),
        imported_property_type=str(row["property_type"] or ""),
        latest_sale_date=row["latest_sale_date"],
        latest_sale_price_aed=(
            int(row["latest_sale_price_aed"]) if row["latest_sale_price_aed"] else None
        ),
        registry_sale_date=row["latest_sale_date"],
        registry_sale_price_aed=(
            int(row["latest_sale_price_aed"]) if row["latest_sale_price_aed"] else None
        ),
        later_sale_date=row["later_sale_date"],
        lease_end=row["lease_end"],
        annual_rent_aed=(int(row["annual_rent_aed"]) if row["annual_rent_aed"] else None),
        duplicate_count=int(row["duplicate_count"] or 1),
        source_lists=list(row["source_lists"] or []),
        source_rows=list(row["source_rows"] or []),
    )


def _sql_owner_profile(
    owner_key: str,
    rows: list[dict[str, Any]],
) -> CrmOwnerProfile:
    best = max(
        rows,
        key=lambda row: (
            int(row["status_rank"] or 0),
            int(row["confidence_score"] or 0),
        ),
    )
    properties = [_sql_owner_property(row) for row in rows]
    phones = list(
        dict.fromkeys(
            str(value)
            for row in rows
            for value in (row["phone_primary"], row["phone_alternate"])
            if value
        )
    )
    emails = list(dict.fromkeys(str(row["email_primary"]) for row in rows if row["email_primary"]))
    rental_properties = [item for item in properties if item.lead_id]
    contact_ready = [
        item
        for item in properties
        if item.lead_id
        and item.ownership_status in {"verified_current_owner", "probable_current_owner"}
    ]
    lease_dates = [item.lease_end for item in rental_properties if item.lease_end]
    return CrmOwnerProfile(
        owner_key=owner_key,
        contact_name=str(best["contact_name"]),
        phone_primary=phones[0] if phones else None,
        phone_alternate=phones[1] if len(phones) > 1 else None,
        email_primary=emails[0] if emails else None,
        highest_ownership_status=str(best["ownership_status"]),  # type: ignore[arg-type]
        highest_confidence_score=int(best["confidence_score"] or 0),
        property_count=len(properties),
        rental_linked_count=len(rental_properties),
        contact_ready_count=len(contact_ready),
        annual_rent_aed=sum(item.annual_rent_aed or 0 for item in rental_properties),
        next_lease_end=min(lease_dates) if lease_dates else None,
        properties=properties,
    )


async def get_owner_registry(
    db: AsyncSession,
    *,
    organization_id: str,
    list_id: int | None,
    scope: str,
    status: str | None,
    search: str | None,
    lease_window: str | None,
    portfolio_only: bool,
    min_rent_aed: int | None,
    max_rent_aed: int | None,
    min_value_aed: int | None,
    max_value_aed: int | None,
    limit: int,
    offset: int,
) -> CrmOwnerRegistryResponse:
    summary = await _owner_registry_summary_sql(
        db,
        organization_id=organization_id,
        list_id=list_id,
    )
    owner_keys, total = await _owner_page_keys_sql(
        db,
        organization_id=organization_id,
        list_id=list_id,
        scope=scope,
        status=status,
        search=search,
        lease_window=lease_window,
        portfolio_only=portfolio_only,
        min_rent_aed=min_rent_aed,
        max_rent_aed=max_rent_aed,
        min_value_aed=min_value_aed,
        max_value_aed=max_value_aed,
        limit=limit,
        offset=offset,
    )
    property_rows = await _owner_properties_sql(
        db,
        organization_id=organization_id,
        list_id=list_id,
        owner_keys=owner_keys,
        scope=scope,
        status=status,
        search=search,
        lease_window=lease_window,
        min_rent_aed=min_rent_aed,
        max_rent_aed=max_rent_aed,
        min_value_aed=min_value_aed,
        max_value_aed=max_value_aed,
    )
    profiles = [
        _sql_owner_profile(owner_key, property_rows[owner_key])
        for owner_key in owner_keys
        if owner_key in property_rows
    ]
    return CrmOwnerRegistryResponse(
        scope=scope,  # type: ignore[arg-type]
        owners=profiles,
        total=total,
        limit=limit,
        offset=offset,
        summary=summary,
    )


def _owner_property_registry_score(
    owner_property: CrmOwnerProperty,
    row: dict[str, Any],
) -> int:
    owner_building = _usable_project_name(owner_property.building_name)
    owner_project = _usable_project_name(owner_property.project_name)
    owner_area = _usable_project_name(owner_property.area_name)
    sale_building = str(row.get("building_name") or "")
    sale_project = str(row.get("project_name") or "")
    sale_area = str(row.get("area_name") or "")
    combined_sale = " ".join(value for value in (sale_building, sale_project) if value)
    building_score = max(
        (
            _location_similarity(owner_building, value)
            for value in (sale_building, combined_sale)
        ),
        default=0,
    )
    project_score = max(
        (
            _location_similarity(owner_project, value)
            for value in (sale_project, sale_building, combined_sale)
        ),
        default=0,
    )
    area_score = _location_similarity(owner_area, sale_area)
    if owner_building:
        return round(0.70 * building_score + 0.25 * project_score + 0.05 * area_score)
    if owner_project:
        return round(0.90 * project_score + 0.10 * area_score)
    return area_score


def _positive_float(value: Any) -> float | None:
    parsed = float(value or 0)
    return parsed if parsed > 0 else None


async def _enrich_owner_profile_registry(profile: CrmOwnerProfile) -> CrmOwnerProfile:
    """Attach authoritative DLD registry attributes to a clicked owner profile.

    Claims already retain the selected property's latest sale signature. Restricting
    the registry query to those signatures avoids scanning every Dubai property that
    happens to use a generic unit number such as 101 or 204.
    """
    eligible = [
        owner_property
        for owner_property in profile.properties
        if owner_property.unit_number
        and owner_property.latest_sale_date
        and owner_property.latest_sale_price_aed
    ]
    if not eligible:
        return profile
    signatures = {
        (
            owner_property.latest_sale_date,
            int(owner_property.latest_sale_price_aed or 0),
        )
        for owner_property in eligible
    }
    rows = await query(
        """
        SELECT
            transaction_date,
            sale_amount_aed,
            replaceRegexpAll(lowerUTF8(unit_number), '\\s+', '') AS unit_key,
            unit_number,
            building_name,
            building_key,
            project_name,
            area_name,
            area_key,
            property_type,
            market_status,
            bedrooms,
            size_sqft,
            built_up_area_sqft,
            price_per_sqft_aed,
            sale_key
        FROM dxbi_sales_unit_events FINAL
        WHERE transaction_date IN {dates:Array(Date)}
          AND sale_amount_aed IN {prices:Array(UInt64)}
        """,
        {
            "dates": sorted({signature[0] for signature in signatures}),
            "prices": sorted({signature[1] for signature in signatures}),
        },
    )
    rows_by_signature: dict[tuple[date, int], list[dict[str, Any]]] = {}
    for row in rows:
        signature = (
            row["transaction_date"],
            int(row.get("sale_amount_aed") or 0),
        )
        if signature in signatures:
            rows_by_signature.setdefault(signature, []).append(row)

    for owner_property in eligible:
        signature = (
            owner_property.latest_sale_date,
            int(owner_property.latest_sale_price_aed or 0),
        )
        unit_key = _normalize_unit(owner_property.unit_number).lower()
        property_candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows_by_signature.get(signature, []):
            if str(row.get("unit_key") or "") != unit_key:
                continue
            building_key = str(row.get("building_key") or "") or _location_key(
                str(row.get("building_name") or row.get("project_name") or "")
            )
            identity = (
                str(row.get("area_key") or ""),
                building_key,
                str(row.get("unit_key") or ""),
            )
            property_candidates.setdefault(identity, row)
        if not property_candidates:
            continue
        ranked = sorted(
            (
                (_owner_property_registry_score(owner_property, row), row)
                for row in property_candidates.values()
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        score, selected = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0
        if score < 55 or (len(ranked) > 1 and score - runner_up < 12):
            continue

        owner_property.registry_sale_date = selected["transaction_date"]
        owner_property.registry_sale_price_aed = int(
            selected.get("sale_amount_aed") or 0
        ) or None
        owner_property.registry_property_type = (
            str(selected.get("property_type") or "").strip() or None
        )
        owner_property.registry_bedrooms = (
            str(selected.get("bedrooms") or "").strip() or None
        )
        owner_property.registry_size_sqft = _positive_float(selected.get("size_sqft"))
        owner_property.registry_built_up_area_sqft = _positive_float(
            selected.get("built_up_area_sqft")
        )
        owner_property.registry_price_per_sqft_aed = _positive_float(
            selected.get("price_per_sqft_aed")
        )
        owner_property.registry_market_status = (
            str(selected.get("market_status") or "").strip() or None
        )
    return profile


async def get_owner_profile(
    db: AsyncSession,
    *,
    organization_id: str,
    owner_key: str,
) -> CrmOwnerProfile:
    property_rows = await _owner_properties_sql(
        db,
        organization_id=organization_id,
        list_id=None,
        owner_keys=[owner_key],
        scope="all",
    )
    rows = property_rows.get(owner_key)
    if not rows:
        raise HTTPException(status_code=404, detail="Owner profile not found")
    profile = _sql_owner_profile(owner_key, rows)
    try:
        return await _enrich_owner_profile_registry(profile)
    except Exception:
        logger.exception(
            "Owner profile registry enrichment failed",
            extra={"owner_key": owner_key},
        )
        return profile


def _owner_workspace_summaries(
    workspaces: list[CrmOwnerWorkspace],
    notes: list[CrmOwnerNote],
) -> list[CrmOwnerWorkspaceSummary]:
    notes_by_workspace: dict[int, list[CrmOwnerNote]] = {}
    for note in notes:
        notes_by_workspace.setdefault(note.workspace_id, []).append(note)
    summaries: list[CrmOwnerWorkspaceSummary] = []
    for workspace in workspaces:
        workspace_notes = notes_by_workspace.get(workspace.id or 0, [])
        workspace_notes.sort(key=lambda item: item.created_at, reverse=True)
        summaries.append(
            CrmOwnerWorkspaceSummary(
                owner_key=workspace.owner_key,
                pipeline_status=workspace.pipeline_status,  # type: ignore[arg-type]
                highlight_color=workspace.highlight_color,  # type: ignore[arg-type]
                next_follow_up=workspace.next_follow_up,
                tags=list(workspace.tags or []),
                note_count=len(workspace_notes),
                last_note=workspace_notes[0].body if workspace_notes else None,
                updated_at=workspace.updated_at,
            )
        )
    summaries.sort(key=lambda item: item.updated_at, reverse=True)
    return summaries


async def list_owner_workspaces(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str,
) -> list[CrmOwnerWorkspaceSummary]:
    workspace_result = await db.exec(
        select(CrmOwnerWorkspace).where(
            CrmOwnerWorkspace.user_id == user_id,
            CrmOwnerWorkspace.organization_id == organization_id,
        )
    )
    workspaces = list(workspace_result.all())
    if not workspaces:
        return []
    workspace_ids = [item.id for item in workspaces if item.id is not None]
    note_result = await db.exec(
        select(CrmOwnerNote).where(
            CrmOwnerNote.user_id == user_id,
            CrmOwnerNote.organization_id == organization_id,
            CrmOwnerNote.workspace_id.in_(workspace_ids),  # type: ignore[union-attr]
        )
    )
    return _owner_workspace_summaries(workspaces, list(note_result.all()))


async def bulk_update_owner_workspaces(
    db: AsyncSession,
    *,
    payload: CrmOwnerBulkUpdate,
    user_id: str,
    organization_id: str,
) -> list[CrmOwnerWorkspaceSummary]:
    owner_keys = sorted({value.strip() for value in payload.owner_keys if value.strip()})
    if not owner_keys:
        raise HTTPException(status_code=422, detail="Select at least one owner")
    if not any((payload.pipeline_status, payload.highlight_color, payload.note)):
        raise HTTPException(status_code=422, detail="Choose a CRM update to apply")

    claim_result = await db.exec(
        select(CrmPropertyContactClaim.owner_key).where(
            CrmPropertyContactClaim.organization_id == organization_id,
            CrmPropertyContactClaim.owner_key.in_(owner_keys),  # type: ignore[union-attr]
        )
    )
    valid_keys = set(claim_result.all())
    owner_keys = [key for key in owner_keys if key in valid_keys]
    if not owner_keys:
        raise HTTPException(status_code=404, detail="Selected owners were not found")

    workspace_result = await db.exec(
        select(CrmOwnerWorkspace).where(
            CrmOwnerWorkspace.user_id == user_id,
            CrmOwnerWorkspace.organization_id == organization_id,
            CrmOwnerWorkspace.owner_key.in_(owner_keys),  # type: ignore[union-attr]
        )
    )
    existing = {workspace.owner_key: workspace for workspace in workspace_result.all()}
    now = _utcnow()
    touched: list[CrmOwnerWorkspace] = []
    note_body = (payload.note or "").strip()
    for owner_key in owner_keys:
        workspace = existing.get(owner_key)
        if workspace is None:
            workspace = CrmOwnerWorkspace(
                user_id=user_id,
                organization_id=organization_id,
                owner_key=owner_key,
                pipeline_status="new",
                highlight_color="none",
                tags=[],
                created_at=now,
                updated_at=now,
            )
        if payload.pipeline_status is not None:
            workspace.pipeline_status = payload.pipeline_status
        if payload.highlight_color is not None:
            workspace.highlight_color = payload.highlight_color
        workspace.updated_at = now
        db.add(workspace)
        await db.flush()
        if note_body and workspace.id is not None:
            db.add(
                CrmOwnerNote(
                    workspace_id=workspace.id,
                    user_id=user_id,
                    organization_id=organization_id,
                    body=note_body,
                    created_at=now,
                    updated_at=now,
                )
            )
        touched.append(workspace)
    await db.commit()
    return await list_owner_workspaces(
        db,
        user_id=user_id,
        organization_id=organization_id,
    )
