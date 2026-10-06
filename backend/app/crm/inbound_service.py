from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import openpyxl
from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, exists, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.clickhouse.client import query
from app.config import settings
from app.core.reelly_scope import reelly_dubai_project_scope
from app.crm.import_models import CrmPropertyContactClaim
from app.crm.import_service import _normalize_email, _normalize_phone
from app.crm.inbound_models import (
    CrmInboundActivity,
    CrmInboundContact,
    CrmInboundEnquiry,
    CrmInboundImport,
    CrmInboundMatch,
    CrmInboundNote,
    InboundActivityResponse,
    InboundContactResponse,
    InboundEnquiryCreate,
    InboundEnquiryListResponse,
    InboundEnquiryResponse,
    InboundEnquiryUpdate,
    InboundImportPreviewResponse,
    InboundImportPreviewSheet,
    InboundImportResponse,
    InboundImportSummary,
    InboundMatchesResponse,
    InboundMatchResponse,
    InboundNoteResponse,
    InboundOwnershipEnrichmentResponse,
    InboundPriorityResponse,
    InboundRegistryProfileResponse,
)
from app.listings.service import list_listings_from_clickhouse

_MAX_FILE_BYTES = 50 * 1024 * 1024
_ALGORITHM_VERSION = "inbound-v1"
_LISTING_MAX_AGE_HOURS = 48
_FIRST_RESPONSE_MINUTES = 5
_QUALIFIED_STATUSES = {"qualified", "viewing", "valuation", "signed", "active", "won"}
_NON_KEY = re.compile(r"[^a-z0-9]+")
_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?971|0)?[\s().-]*5\d(?:[\s().-]*\d){7}(?!\d)")
_ID_RE = re.compile(r"\b\d{9,18}\b")

_ALIASES: dict[str, set[str]] = {
    "full_name": {"name", "fullname", "leadname", "contactname", "customername"},
    "first_name": {"firstname", "first"},
    "last_name": {"lastname", "surname", "last"},
    "phone": {"phone", "phonenumber", "mobile", "mobilenumber", "telephone"},
    "email": {"email", "emailaddress"},
    "whatsapp": {"whatsapp", "whatsappnumber"},
    "intent": {"intent", "leadtype", "enquirytype", "transactiontype", "lookingfor"},
    "source": {"source", "leadsource", "channel", "platform"},
    "campaign": {"campaign", "campaignname", "formname", "adname", "adsetname"},
    "source_lead_id": {"leadid", "sourceleadid", "recordid", "submissionid"},
    "notes": {"notes", "message", "comments", "requirements", "description", "enquiry"},
    "locations": {"area", "location", "community", "project", "preferredlocation"},
    "property_type": {"propertytype", "unittype", "assettype"},
    "bedrooms": {"bedrooms", "beds", "bedroom"},
    "budget_min": {"budgetmin", "minbudget", "minimumprice"},
    "budget_max": {"budget", "budgetmax", "maxbudget", "maximumprice", "price"},
    "timeline": {"timeline", "movingdate", "purchasedate", "when", "urgency"},
    "financing": {"financing", "paymentmethod", "mortgage", "finance"},
    "language": {"language", "preferredlanguage"},
    "consent": {"consent", "marketingconsent", "optin", "permissiontocontact"},
    "created_at": {"createdat", "createdtime", "submissiondate", "leaddate", "date"},
    "unit_number": {"unit", "unitnumber", "villanumber"},
    "building": {"building", "tower", "buildingname"},
}

_KNOWN_LOCATIONS = (
    "JBR",
    "Dubai Marina",
    "Downtown Dubai",
    "Business Bay",
    "Palm Jumeirah",
    "Jumeirah Village Circle",
    "JVC",
    "Dubai Hills",
    "Arabian Ranches",
    "Tilal Al Ghaf",
    "Damac Hills",
    "Dubai Creek Harbour",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token(value: Any) -> str:
    return _NON_KEY.sub("", str(value or "").strip().lower())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _amount(value: Any) -> int | None:
    if isinstance(value, int | float) and value > 0:
        return int(value)
    raw = _text(value).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(m|mn|million|k|thousand)?", raw)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2) or ""
    if suffix in {"m", "mn", "million"}:
        number *= 1_000_000
    elif suffix in {"k", "thousand"}:
        number *= 1_000
    return int(number) if number > 0 else None


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    raw = _text(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _utcnow()


def _normalize_intent(value: Any, notes: str = "") -> str | None:
    raw = f"{_text(value)} {notes}".lower()
    if any(word in raw for word in ("landlord", "list for rent", "rent out", "to let")):
        return "let"
    if any(word in raw for word in ("seller", "sell my", "want to sell", "valuation")):
        return "sell"
    if any(word in raw for word in ("tenant", "looking to rent", "for rent", "lease")):
        return "rent"
    if any(word in raw for word in ("buyer", "looking to buy", "purchase", "for sale")):
        return "buy"
    return None


def _qualification_complete(enquiry: CrmInboundEnquiry) -> bool:
    if (
        enquiry.record_kind != "opportunity"
        or enquiry.intent not in {"buy", "rent", "sell", "let"}
        or enquiry.status not in _QUALIFIED_STATUSES
    ):
        return False
    criteria = enquiry.criteria or {}
    if enquiry.intent in {"sell", "let"}:
        return bool(criteria.get("building") and criteria.get("unit_number"))
    has_location = bool(_locations(criteria))
    has_brief = any(
        criteria.get(field) not in (None, "", [])
        for field in ("budget_max_aed", "bedrooms_min", "property_type")
    )
    return has_location and has_brief


def _sla_state(enquiry: CrmInboundEnquiry) -> str:
    if enquiry.first_contact_at:
        return "responded"
    due = enquiry.first_response_due_at
    if not due:
        return "on_time"
    now = _utcnow()
    if due <= now:
        return "overdue"
    return "due_soon" if due - now <= timedelta(minutes=2) else "on_time"


def _belongs_in_inbox(enquiry: CrmInboundEnquiry) -> bool:
    """Keep the inbox operational: an untouched qualified lead still needs a response."""
    if enquiry.record_kind != "opportunity" or enquiry.status in {
        "won",
        "nurture",
        "closed_lost",
        "disqualified",
    }:
        return False
    if enquiry.first_contact_at is None:
        return True
    if enquiry.status in {"new", "assigned", "attempted", "contacted", "needs_review"}:
        return True
    # Follow-up is a calendar-date commitment in the agent's local workspace,
    # unlike response timestamps which are stored in UTC.
    return bool(enquiry.next_follow_up and enquiry.next_follow_up <= date.today())


def _redact(text: str, contact_values: list[str]) -> str:
    redacted = text
    for value in sorted((v for v in contact_values if len(v.strip()) >= 3), key=len, reverse=True):
        redacted = re.sub(re.escape(value), "[REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = _EMAIL_RE.sub("[EMAIL]", redacted)
    redacted = _PHONE_RE.sub("[PHONE]", redacted)
    return _ID_RE.sub("[ID]", redacted)[:2_000]


def _deterministic_criteria(row: dict[str, Any], notes: str) -> dict[str, Any]:
    criteria: dict[str, Any] = {}
    location_value = _text(row.get("locations"))
    locations = [item.strip() for item in re.split(r"[,;/|]", location_value) if item.strip()]
    if not locations:
        lowered = notes.lower()
        locations = [location for location in _KNOWN_LOCATIONS if location.lower() in lowered]
    if locations:
        criteria["locations"] = list(dict.fromkeys(locations))

    bedroom_value = _text(row.get("bedrooms"))
    bedroom_match = re.search(r"(studio|\d+)\s*(?:bed|br|bedroom)?", bedroom_value, re.I)
    if not bedroom_match:
        bedroom_match = re.search(r"(studio|\d+)\s*(?:bed|br|bedroom)s?", notes, re.I)
    if bedroom_match:
        bedrooms = 0 if bedroom_match.group(1).lower() == "studio" else int(bedroom_match.group(1))
        criteria["bedrooms_min"] = bedrooms
        criteria["bedrooms_max"] = bedrooms

    minimum = _amount(row.get("budget_min"))
    maximum = _amount(row.get("budget_max"))
    if maximum is None:
        budget_match = re.search(
            r"(?:budget|around|up to|max(?:imum)?)[^\d]{0,12}(\d+(?:\.\d+)?\s*(?:m|mn|million|k)?)",
            notes,
            re.I,
        )
        maximum = _amount(budget_match.group(1)) if budget_match else None
    if minimum:
        criteria["budget_min_aed"] = minimum
    if maximum:
        criteria["budget_max_aed"] = maximum
    if property_type := _text(row.get("property_type")):
        criteria["property_type"] = property_type
    if timeline := _text(row.get("timeline")):
        criteria["timeline"] = timeline
    if financing := _text(row.get("financing")):
        criteria["financing"] = financing
    if unit := _text(row.get("unit_number")):
        criteria["unit_number"] = unit
    if building := _text(row.get("building")):
        criteria["building"] = building
    return criteria


async def _ai_extract(notes: str, known: dict[str, Any]) -> tuple[dict[str, Any], float, list[str]]:
    if not notes or not settings.OPENROUTER_API_KEY:
        return {}, 0.0, []
    prompt = {
        "task": "Extract a Dubai real-estate enquiry from redacted text.",
        "text": notes,
        "already_extracted": known,
        "allowed_intents": ["buy", "rent", "sell", "let"],
        "output": {
            "intent": "string or null",
            "criteria": {
                "locations": ["strings"],
                "property_type": "string or null",
                "bedrooms_min": "integer or null",
                "bedrooms_max": "integer or null",
                "budget_min_aed": "integer or null",
                "budget_max_aed": "integer or null",
                "timeline": "string or null",
                "financing": "string or null",
            },
            "strict_fields": ["criteria keys explicitly stated as hard requirements"],
            "confidence": "0 to 1",
        },
        "rules": ["Return JSON only", "Use null for unknown values", "Do not infer identity"],
    }
    try:
        async with httpx.AsyncClient(timeout=25) as client:
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
                            "content": "Extract structured property demand. Never invent missing facts.",
                        },
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                    "max_tokens": 500,
                    "provider": {"zdr": True, "data_collection": "deny"},
                },
            )
            response.raise_for_status()
            payload = json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception:
        return {}, 0.0, []
    criteria = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    criteria = {key: value for key, value in criteria.items() if value not in (None, "", [])}
    if payload.get("intent"):
        criteria["_intent"] = payload["intent"]
    confidence = float(payload.get("confidence") or 0)
    strict = [str(item) for item in payload.get("strict_fields", []) if item]
    return criteria, max(0.0, min(1.0, confidence)), strict


def _header_mapping(headers: list[Any]) -> dict[str, int]:
    tokens = {_token(header): index for index, header in enumerate(headers) if _text(header)}
    mapping: dict[str, int] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in tokens:
                mapping[canonical] = tokens[alias]
                break
    return mapping


def _best_header(rows: list[tuple[Any, ...]]) -> tuple[int, tuple[Any, ...], dict[str, int]]:
    """Find the most likely header row in exports with titles or blank preambles."""
    candidates = []
    for index, values in enumerate(rows[:15]):
        mapping = _header_mapping(list(values))
        identity_fields = len({"full_name", "first_name", "phone", "email"} & mapping.keys())
        candidates.append((len(mapping), identity_fields, -index, index, values, mapping))
    if not candidates:
        return 0, (), {}
    _, _, _, index, values, mapping = max(candidates, key=lambda item: item[:3])
    return index, values, mapping


def _mapping_override_for_sheet(
    override: dict[str, Any] | None,
    sheet_name: str,
    headers: list[Any],
    detected: dict[str, int],
) -> dict[str, int]:
    if not override:
        return detected
    sheets = override.get("sheets", [])
    sheet_config = next((item for item in sheets if item.get("sheet") == sheet_name), None)
    if not sheet_config:
        return detected
    by_header = {_text(header): index for index, header in enumerate(headers)}
    mapped = {
        canonical: by_header[header]
        for canonical, header in sheet_config.get("field_map", {}).items()
        if header in by_header and canonical in _ALIASES
    }
    return mapped or detected


def _file_rows(
    data: bytes,
    filename: str,
    mapping_override: dict[str, Any] | None = None,
) -> tuple[list[tuple[str, int, dict[str, Any]]], dict[str, Any]]:
    rows: list[tuple[str, int, dict[str, Any]]] = []
    mappings: list[dict[str, Any]] = []
    if filename.lower().endswith(".csv"):
        raw = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        header_index, header_values, mapping = _best_header([tuple(row) for row in raw])
        headers = list(header_values)
        sheet_name = Path(filename).stem
        mapping = _mapping_override_for_sheet(mapping_override, sheet_name, headers, mapping)
        for row_number, values in enumerate(raw[header_index + 1 :], start=header_index + 2):
            if any(_text(value) for value in values):
                rows.append(
                    (
                        sheet_name,
                        row_number,
                        {
                            key: values[index] if index < len(values) else None
                            for key, index in mapping.items()
                        },
                    )
                )
        mappings.append(
            {
                "sheet": sheet_name,
                "header_row": header_index + 1,
                "headers": [_text(value) for value in headers if _text(value)],
                "field_map": {key: headers[index] for key, index in mapping.items()},
            }
        )
        return rows, {"sheets": mappings}

    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            preview = list(sheet.iter_rows(min_row=1, max_row=15, values_only=True))
            header_index, header_values, mapping = _best_header(preview)
            mapping = _mapping_override_for_sheet(
                mapping_override, sheet.title, list(header_values), mapping
            )
            mappings.append(
                {
                    "sheet": sheet.title,
                    "header_row": header_index + 1,
                    "headers": [_text(value) for value in header_values if _text(value)],
                    "field_map": {
                        key: _text(header_values[index]) for key, index in mapping.items()
                    },
                }
            )
            for row_number, values in enumerate(
                sheet.iter_rows(min_row=header_index + 2, values_only=True), start=header_index + 2
            ):
                if any(value not in (None, "") for value in values):
                    rows.append(
                        (
                            sheet.title,
                            row_number,
                            {
                                key: values[index] if index < len(values) else None
                                for key, index in mapping.items()
                            },
                        )
                    )
    finally:
        workbook.close()
    return rows, {"sheets": mappings}


def _preview_file(
    data: bytes,
    filename: str,
    mapping_override: dict[str, Any] | None = None,
    ai_mapped_sheets: set[str] | None = None,
) -> InboundImportPreviewResponse:
    rows, audit = _file_rows(data, filename, mapping_override)
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for sheet, row_number, row in rows:
        grouped.setdefault(sheet, []).append((row_number, row))
    sheets = []
    for item in audit.get("sheets", []):
        sheet_name = item["sheet"]
        field_map = item.get("field_map", {})
        headers = item.get("headers", [])
        samples = []
        for row_number, row in grouped.get(sheet_name, [])[:5]:
            samples.append(
                {
                    "row": str(row_number),
                    **{
                        key: _redact(_text(value), [])[:160]
                        for key, value in row.items()
                        if value not in (None, "") and key not in {"phone", "email", "whatsapp"}
                    },
                    **{key: "Present" for key in ("phone", "email", "whatsapp") if row.get(key)},
                }
            )
        sheets.append(
            InboundImportPreviewSheet(
                sheet=sheet_name,
                header_row=item.get("header_row", 1),
                headers=headers,
                field_map=field_map,
                sample_rows=samples,
                row_count=len(grouped.get(sheet_name, [])),
                mapping_source=(
                    "ai_assisted" if sheet_name in (ai_mapped_sheets or set()) else "deterministic"
                ),
            )
        )
    warnings = []
    if not any("full_name" in sheet.field_map for sheet in sheets):
        warnings.append("No name column was detected")
    if not any({"phone", "email"} & set(sheet.field_map) for sheet in sheets):
        warnings.append("No phone or email column was detected")
    return InboundImportPreviewResponse(
        original_filename=filename,
        size_bytes=len(data),
        total_rows=len(rows),
        sheets=sheets,
        warnings=warnings,
    )


async def _ai_header_mapping(headers: list[str], campaign_context: str) -> dict[str, str]:
    if not headers or not settings.OPENROUTER_API_KEY:
        return {}
    prompt = {
        "task": "Map spreadsheet columns to a real-estate lead import schema.",
        "headers": headers,
        "source_context": campaign_context,
        "allowed_fields": list(_ALIASES),
        "rules": [
            "Return JSON with a field_map object only",
            "Keys must be allowed_fields",
            "Values must exactly match one supplied header",
            "Do not map uncertain columns",
            "Campaign context describes the source and must not be treated as individual intent",
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
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
                            "content": "Map headers conservatively. Never invent columns or lead facts.",
                        },
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                    "max_tokens": 600,
                    "provider": {"zdr": True, "data_collection": "deny"},
                },
            )
            response.raise_for_status()
            payload = json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception:
        return {}
    proposed = payload.get("field_map", {})
    return {
        canonical: header
        for canonical, header in proposed.items()
        if canonical in _ALIASES and header in headers
    }


async def preview_inbound_import(
    upload: UploadFile, campaign_context: str = ""
) -> InboundImportPreviewResponse:
    filename = Path(upload.filename or "inbound-leads.xlsx").name
    if not filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=415, detail="Upload a CSV or XLSX file")
    data = await upload.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Inbound import exceeds 50 MB")
    try:
        preview = _preview_file(data, filename)
        ai_mapped_sheets: set[str] = set()
        for sheet in preview.sheets:
            has_identity = bool(
                {"full_name", "first_name", "phone", "email"} & set(sheet.field_map)
            )
            if has_identity and len(sheet.field_map) >= 4:
                continue
            suggested = await _ai_header_mapping(sheet.headers, campaign_context.strip()[:4_000])
            for canonical, header in suggested.items():
                sheet.field_map.setdefault(canonical, header)
            if suggested:
                ai_mapped_sheets.add(sheet.sheet)
        if ai_mapped_sheets:
            override = {
                "sheets": [
                    {"sheet": sheet.sheet, "field_map": sheet.field_map} for sheet in preview.sheets
                ]
            }
            preview = _preview_file(data, filename, override, ai_mapped_sheets)
            preview.warnings.append(
                "AI suggested mappings are highlighted for review and are not applied until approval"
            )
        return preview
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read import: {exc}") from exc


async def _find_or_create_contact(
    db: AsyncSession,
    *,
    organization_id: str,
    full_name: str,
    phone: str | None,
    email: str | None,
    whatsapp: str | None,
    language: str | None,
    consent_status: str,
) -> CrmInboundContact:
    conditions = []
    if phone:
        conditions.append(CrmInboundContact.phone == phone)
    if email:
        conditions.append(CrmInboundContact.email == email)
    existing = None
    if conditions:
        result = await db.exec(
            select(CrmInboundContact).where(
                CrmInboundContact.organization_id == organization_id, or_(*conditions)
            )
        )
        existing = result.first()
    now = _utcnow()
    if existing:
        existing.full_name = full_name or existing.full_name
        existing.phone = phone or existing.phone
        existing.email = email or existing.email
        existing.whatsapp = whatsapp or existing.whatsapp
        existing.preferred_language = language or existing.preferred_language
        existing.updated_at = now
        db.add(existing)
        return existing
    contact = CrmInboundContact(
        organization_id=organization_id,
        full_name=full_name or "Unnamed lead",
        phone=phone,
        email=email,
        whatsapp=whatsapp,
        preferred_language=language,
        consent_status=consent_status,
        created_at=now,
        updated_at=now,
    )
    db.add(contact)
    await db.flush()
    return contact


def _claim_property_identity(claim: CrmPropertyContactClaim) -> str:
    return claim.property_key or "|".join(
        (
            _token(claim.building_name or claim.project_name),
            _token(claim.unit_number),
        )
    )


def _claim_observed_value(claim: CrmPropertyContactClaim) -> int:
    evidence = claim.evidence or {}
    candidates = (
        claim.latest_sale_price_aed,
        claim.transaction_price_aed,
        evidence.get("latest_sale_price_aed"),
        evidence.get("sale_amount_aed"),
        evidence.get("transaction_price_aed"),
        evidence.get("purchase_price_aed"),
    )
    return next((amount for value in candidates if (amount := _amount(value))), 0)


def _ownership_enrichment(
    matches: list[tuple[CrmPropertyContactClaim, str]],
) -> InboundOwnershipEnrichmentResponse:
    if not matches:
        return InboundOwnershipEnrichmentResponse()
    basis_order = {"phone": 3, "email": 2, "name": 1}
    match_basis = max((basis for _, basis in matches), key=basis_order.__getitem__)
    best_by_property: dict[str, CrmPropertyContactClaim] = {}
    status_order = {
        "verified_current_owner": 5,
        "probable_current_owner": 4,
        "former_owner": 3,
        "unit_linked_unverified": 2,
        "conflicting_claim": 1,
        "registry_not_observed": 0,
        "insufficient_property_data": 0,
        "unmatched": 0,
    }
    for claim, _ in matches:
        property_identity = _claim_property_identity(claim)
        current = best_by_property.get(property_identity)
        if current is None or (
            status_order.get(claim.ownership_status, 0),
            claim.confidence_score,
        ) > (status_order.get(current.ownership_status, 0), current.confidence_score):
            best_by_property[property_identity] = claim
    claims = list(best_by_property.values())
    current = [
        claim
        for claim in claims
        if claim.ownership_status in {"verified_current_owner", "probable_current_owner"}
    ]
    former = [claim for claim in claims if claim.ownership_status == "former_owner"]
    rental = [claim for claim in current if claim.lease_end or claim.lead_id]
    portfolio_value = sum(_claim_observed_value(claim) for claim in claims)
    reasons = [
        "Phone matched owner records"
        if match_basis == "phone"
        else "Email matched owner records"
        if match_basis == "email"
        else "Name matched owner records; verify identity"
    ]
    if current:
        reasons.append(
            f"{len(current)} current propert{'y' if len(current) == 1 else 'ies'} observed"
        )
    if former:
        reasons.append(f"{len(former)} prior propert{'y' if len(former) == 1 else 'ies'} observed")
    if rental:
        reasons.append(f"{len(rental)} rental propert{'y' if len(rental) == 1 else 'ies'} observed")
    if len(claims) >= 2:
        reasons.append(f"Known across {len(claims)} properties")
    if portfolio_value:
        reasons.append(f"AED {portfolio_value:,} in observed property-value evidence")
    return InboundOwnershipEnrichmentResponse(
        matched=True,
        match_basis=match_basis,  # type: ignore[arg-type]
        verification="contact_exact" if match_basis in {"phone", "email"} else "name_only",
        current_owner=bool(current),
        former_owner=bool(former),
        rental_owner=bool(rental),
        multiple_property_owner=len(claims) >= 2,
        current_property_count=len(current),
        prior_property_count=len(former),
        rental_property_count=len(rental),
        known_property_count=len(claims),
        observed_portfolio_value_aed=portfolio_value,
        reasons=reasons,
    )


async def _bulk_ownership_enrichments(
    db: AsyncSession,
    *,
    organization_id: str,
    contacts: list[CrmInboundContact],
) -> dict[int, InboundOwnershipEnrichmentResponse]:
    if not contacts:
        return {}
    name_to_ids: dict[str, set[int]] = {}
    phone_to_ids: dict[str, set[int]] = {}
    email_to_ids: dict[str, set[int]] = {}
    for contact in contacts:
        contact_id = contact.id or 0
        name = contact.full_name.strip().casefold()
        if name:
            name_to_ids.setdefault(name, set()).add(contact_id)
        if contact.phone:
            phone_to_ids.setdefault(contact.phone, set()).add(contact_id)
        if contact.email:
            email_to_ids.setdefault(contact.email.casefold(), set()).add(contact_id)
    conditions = []
    if name_to_ids:
        conditions.append(
            func.lower(func.trim(CrmPropertyContactClaim.contact_name)).in_(list(name_to_ids))
        )
    if phone_to_ids:
        conditions.extend(
            [
                CrmPropertyContactClaim.phone_primary.in_(list(phone_to_ids)),
                CrmPropertyContactClaim.phone_alternate.in_(list(phone_to_ids)),
            ]
        )
    if email_to_ids:
        conditions.append(func.lower(CrmPropertyContactClaim.email_primary).in_(list(email_to_ids)))
    if not conditions:
        return {}
    result = await db.exec(
        select(CrmPropertyContactClaim).where(
            CrmPropertyContactClaim.organization_id == organization_id,
            or_(*conditions),
        )
    )
    matches: dict[int, list[tuple[CrmPropertyContactClaim, str]]] = {}
    for claim in result.all():
        claim_phone_values = {claim.phone_primary, claim.phone_alternate} - {None, ""}
        phone_ids = {
            contact_id
            for value in claim_phone_values
            for contact_id in phone_to_ids.get(str(value), set())
        }
        email_ids = email_to_ids.get((claim.email_primary or "").casefold(), set())
        name_ids = name_to_ids.get(claim.contact_name.strip().casefold(), set())
        for contact_id in phone_ids | email_ids | name_ids:
            basis = (
                "phone"
                if contact_id in phone_ids
                else "email"
                if contact_id in email_ids
                else "name"
            )
            matches.setdefault(contact_id, []).append((claim, basis))
    return {
        contact_id: _ownership_enrichment(contact_matches)
        for contact_id, contact_matches in matches.items()
    }


async def _registry_transaction_evidence(
    claims: list[CrmPropertyContactClaim],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Hydrate owner-import claims with transaction and lease evidence in one batch."""
    buildings = sorted(
        {claim.building_name.strip().casefold() for claim in claims if claim.building_name.strip()}
    )
    units = sorted({claim.unit_number.strip().casefold() for claim in claims if claim.unit_number})
    candidate_keys = sorted(
        {claim.unit_candidate_key for claim in claims if claim.unit_candidate_key}
    )
    sales: dict[str, dict[str, Any]] = {}
    leases: dict[str, dict[str, Any]] = {}
    if buildings and units:
        try:
            rows = await query(
                """
                SELECT
                    building_name,
                    unit_number,
                    transaction_date,
                    sale_amount_aed,
                    ltv_pct,
                    seller_type,
                    detail_url
                FROM dxbi_sales_unit_events FINAL
                WHERE
                    lowerUTF8(building_name) IN {buildings:Array(String)}
                    AND lowerUTF8(unit_number) IN {units:Array(String)}
                ORDER BY transaction_date DESC
                LIMIT 500
                """,
                {"buildings": buildings, "units": units},
            )
            for row in rows:
                key = f"{_token(row.get('building_name'))}|{_token(row.get('unit_number'))}"
                sales.setdefault(key, row)
        except Exception:
            sales = {}
    if candidate_keys:
        try:
            rows = await query(
                """
                SELECT
                    c.unit_candidate_key,
                    c.lease_start,
                    c.lease_end,
                    c.annual_rent_aed,
                    c.contract_state,
                    c.observed_contracts
                FROM dxbi_rental_unit_candidates AS c FINAL
                WHERE c.unit_candidate_key IN {candidate_keys:Array(String)}
                LIMIT 200
                """,
                {"candidate_keys": candidate_keys},
            )
            leases = {str(row["unit_candidate_key"]): row for row in rows}
        except Exception:
            leases = {}
    return sales, leases


def _lead_priority(
    enquiry: CrmInboundEnquiry,
    enrichment: InboundOwnershipEnrichmentResponse,
) -> InboundPriorityResponse:
    """Rank commercial follow-up priority without presenting it as a probability."""
    criteria = enquiry.criteria or {}
    opportunity_value = (
        _amount(
            criteria.get("expected_price_aed")
            or criteria.get("budget_max_aed")
            or criteria.get("budget_min_aed")
            or 0
        )
        or 0
    )
    score = 18 if enquiry.record_kind == "opportunity" and enquiry.intent != "unknown" else 8
    reasons: list[str] = []

    if opportunity_value:
        if enquiry.intent in {"rent", "let"}:
            value_points = (
                24
                if opportunity_value >= 1_000_000
                else 19
                if opportunity_value >= 500_000
                else 14
                if opportunity_value >= 300_000
                else 9
                if opportunity_value >= 150_000
                else 4
            )
            reasons.append(f"AED {opportunity_value:,} stated annual rental requirement")
        else:
            value_points = (
                24
                if opportunity_value >= 20_000_000
                else 19
                if opportunity_value >= 10_000_000
                else 14
                if opportunity_value >= 5_000_000
                else 9
                if opportunity_value >= 2_000_000
                else 4
            )
            reasons.append(f"AED {opportunity_value:,} stated transaction requirement")
        score += value_points
    else:
        reasons.append("Opportunity value has not been qualified")

    if enrichment.matched:
        reasons.extend(enrichment.reasons)
        score += 20 if enrichment.verification == "contact_exact" else 5
        score += 10 if enrichment.current_owner else 0
        score += 6 if enrichment.former_owner else 0
        score += 8 if enrichment.rental_owner else 0
        score += 8 if enrichment.multiple_property_owner else 0
        if enrichment.observed_portfolio_value_aed >= 20_000_000:
            score += 6
        elif enrichment.observed_portfolio_value_aed >= 5_000_000:
            score += 3
    else:
        reasons.append("No owner-registry relationship observed")

    score = min(score, 100)
    if enrichment.verification == "name_only":
        band = "medium"
    elif score >= 60 and enrichment.verification == "contact_exact":
        band = "high"
    elif score >= 40:
        band = "medium"
    else:
        band = "standard"
    return InboundPriorityResponse(
        band=band,
        score=score,
        opportunity_value_aed=opportunity_value,
        reasons=reasons,
    )


async def create_inbound_enquiry(
    db: AsyncSession,
    *,
    payload: InboundEnquiryCreate,
    user_id: str,
    organization_id: str,
) -> InboundEnquiryResponse:
    contact = await _find_or_create_contact(
        db,
        organization_id=organization_id,
        full_name=payload.full_name.strip(),
        phone=_normalize_phone(payload.phone),
        email=_normalize_email(payload.email),
        whatsapp=_normalize_phone(payload.whatsapp),
        language=None,
        consent_status=payload.consent_status,
    )
    now = _utcnow()
    record_kind = (
        "opportunity"
        if payload.record_kind == "opportunity" and payload.intent != "unknown"
        else "unqualified_contact"
    )
    enquiry = CrmInboundEnquiry(
        organization_id=organization_id,
        contact_id=contact.id or 0,
        created_by_user_id=user_id,
        assigned_user_id=payload.assigned_user_id or user_id,
        record_kind=record_kind,
        intent=payload.intent if record_kind == "opportunity" else "unknown",
        status="new",
        source=payload.source,
        campaign=payload.campaign,
        enquiry_date=now,
        criteria=payload.criteria,
        strict_fields=payload.strict_fields,
        raw_notes=payload.notes,
        observed_data={
            "intent": payload.intent if payload.intent != "unknown" else None,
            "message": payload.notes,
            "criteria": payload.criteria,
        },
        confirmed_data=(
            {"intent": payload.intent, "criteria": payload.criteria}
            if record_kind == "opportunity"
            else {}
        ),
        qualification={},
        extraction_confidence=1,
        first_response_due_at=now + timedelta(minutes=_FIRST_RESPONSE_MINUTES),
        created_at=now,
        updated_at=now,
    )
    db.add(enquiry)
    await db.flush()
    db.add(
        CrmInboundActivity(
            enquiry_id=enquiry.id or 0,
            organization_id=organization_id,
            user_id=user_id,
            activity_type="created",
            body="Manually added to the lead inbox",
            metadata_json={"source": payload.source},
            created_at=now,
        )
    )
    await db.commit()
    await db.refresh(enquiry)
    return await _enquiry_response(db, enquiry, contact=contact, include_registry_profiles=True)


async def process_inbound_import(
    db: AsyncSession,
    *,
    upload: UploadFile,
    name: str,
    user_id: str,
    organization_id: str,
    campaign_context: str = "",
    mapping_override: dict[str, Any] | None = None,
) -> InboundImportResponse:
    filename = Path(upload.filename or "inbound-leads.xlsx").name
    if not filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=415, detail="Upload a CSV or XLSX file")
    data = await upload.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Inbound import exceeds 50 MB")
    campaign_context = campaign_context.strip()[:4_000]
    digest = hashlib.sha256(data + b"\0" + campaign_context.casefold().encode()).hexdigest()
    existing_result = await db.exec(
        select(CrmInboundImport).where(
            CrmInboundImport.organization_id == organization_id,
            CrmInboundImport.sha256 == digest,
        )
    )
    if existing := existing_result.first():
        return _import_response(existing)

    now = _utcnow()
    record = CrmInboundImport(
        organization_id=organization_id,
        created_by_user_id=user_id,
        name=name.strip() or Path(filename).stem,
        original_filename=filename,
        sha256=digest,
        size_bytes=len(data),
        status="processing",
        mapping={},
        summary={},
        created_at=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    summary = InboundImportSummary()
    imported_enquiries: list[CrmInboundEnquiry] = []
    imported_contacts: dict[int, CrmInboundContact] = {}
    try:
        rows, mapping = _file_rows(data, filename, mapping_override)
        mapping["campaign_context"] = campaign_context
        record.mapping = mapping
        summary.total_rows = len(rows)
        for sheet_mapping in mapping.get("sheets", []):
            fields = set(sheet_mapping.get("field_map", {}))
            if not ({"full_name", "first_name"} & fields):
                raise ValueError(
                    f"Map a full-name or first-name column for {sheet_mapping.get('sheet', 'the import')}"
                )
            if not ({"phone", "email", "whatsapp"} & fields):
                raise ValueError(
                    f"Map a phone, email, or WhatsApp column for {sheet_mapping.get('sheet', 'the import')}"
                )
        if summary.total_rows > 10_000:
            raise ValueError("Inbound import exceeds the 10,000-row synchronous import limit")
        row_fingerprints: set[str] = set()
        for sheet, row_number, row in rows:
            first = _text(row.get("first_name"))
            last = _text(row.get("last_name"))
            full_name = _text(row.get("full_name")) or " ".join(
                part for part in (first, last) if part
            )
            phone = _normalize_phone(row.get("phone"))
            email = _normalize_email(row.get("email"))
            if not any((full_name, phone, email)):
                continue
            source_id = _text(row.get("source_lead_id"))
            fingerprint_payload = {
                "source_id": source_id,
                "name": full_name.casefold(),
                "phone": phone,
                "email": email,
                "intent": _text(row.get("intent")).casefold(),
                "notes": _text(row.get("notes")).casefold(),
                "locations": _text(row.get("locations")).casefold(),
                "budget": _text(row.get("budget_max")).casefold(),
                "created_at": _text(row.get("created_at")),
            }
            row_fingerprint = hashlib.sha256(
                json.dumps(fingerprint_payload, sort_keys=True).encode()
            ).hexdigest()
            if row_fingerprint in row_fingerprints:
                summary.duplicates += 1
                continue
            row_fingerprints.add(row_fingerprint)
            notes = _text(row.get("notes"))
            # Campaign context describes provenance, not an individual's intent.
            # Only row fields and the person's message may establish observed facts.
            row_context = notes
            intent = _normalize_intent(row.get("intent"), row_context)
            criteria = _deterministic_criteria(row, row_context)
            redacted = _redact(row_context, [full_name, phone or "", email or ""])
            needs_ai = bool(row_context) and (
                intent is None
                or not criteria.get("locations")
                or (
                    intent in {"buy", "rent"}
                    and not any(
                        criteria.get(field) is not None
                        for field in ("bedrooms_min", "budget_max_aed", "property_type")
                    )
                )
            )
            ai_values, confidence, strict = (
                await _ai_extract(redacted, criteria) if needs_ai else ({}, 1.0, [])
            )
            ai_intent = ai_values.pop("_intent", None)
            review: list[str] = []
            contact = await _find_or_create_contact(
                db,
                organization_id=organization_id,
                full_name=full_name,
                phone=phone,
                email=email,
                whatsapp=_normalize_phone(row.get("whatsapp")),
                language=_text(row.get("language")) or None,
                consent_status=_text(row.get("consent")) or "unknown",
            )
            inferred_data: dict[str, Any] = {}
            if ai_intent in {"buy", "rent", "sell", "let"} and intent is None:
                inferred_data["intent"] = ai_intent
            if ai_values:
                inferred_data["criteria"] = ai_values
            if intent is None:
                review.append("Intent was not explicitly supplied and must be qualified")
            if intent in {"buy", "rent"} and not criteria.get("locations"):
                review.append("Preferred location is missing")
            if confidence and confidence < 0.85:
                review.append("Message extraction should be reviewed")
            record_kind = "opportunity" if intent else "unqualified_contact"
            observed_data = {
                "intent": intent,
                "message": notes or None,
                "criteria": criteria,
                "source": _text(row.get("source")) or "Imported",
                "campaign": _text(row.get("campaign")) or record.name,
                "campaign_context": campaign_context or None,
            }
            enquiry_date = _parse_datetime(row.get("created_at"))
            enquiry = CrmInboundEnquiry(
                organization_id=organization_id,
                contact_id=contact.id or 0,
                source_import_id=record.id,
                created_by_user_id=user_id,
                assigned_user_id=user_id,
                record_kind=record_kind,
                intent=intent or "unknown",
                status="needs_review" if review else "new",
                source=_text(row.get("source")) or "Imported",
                campaign=_text(row.get("campaign")) or record.name,
                source_lead_id=source_id or None,
                source_sheet=sheet,
                source_row_number=row_number,
                enquiry_date=enquiry_date,
                criteria=criteria,
                strict_fields=strict,
                raw_notes=notes or None,
                observed_data=observed_data,
                inferred_data=inferred_data,
                confirmed_data={},
                qualification={},
                extraction_confidence=confidence or (0.8 if review else 0.9),
                extraction_evidence={
                    "redacted_ai": bool(ai_values),
                    "campaign_context_used": bool(campaign_context),
                    "classification_source": "row_or_message" if intent else "unknown",
                    "mapping": mapping,
                },
                review_reasons=review,
                first_response_due_at=enquiry_date + timedelta(minutes=_FIRST_RESPONSE_MINUTES),
                created_at=now,
                updated_at=now,
            )
            db.add(enquiry)
            await db.flush()
            imported_enquiries.append(enquiry)
            imported_contacts[contact.id or 0] = contact
            db.add(
                CrmInboundActivity(
                    enquiry_id=enquiry.id or 0,
                    organization_id=organization_id,
                    user_id=user_id,
                    activity_type="imported",
                    body=f"Imported from {record.name}",
                    metadata_json={"sheet": sheet, "row": row_number},
                    created_at=now,
                )
            )
            summary.imported += 1
            summary.needs_review += int(bool(review))
            if intent == "buy":
                summary.buyers += 1
            elif intent == "rent":
                summary.tenants += 1
            elif intent == "sell":
                summary.sellers += 1
            elif intent == "let":
                summary.landlords += 1
            else:
                summary.unqualified_contacts += 1
        enrichments = await _bulk_ownership_enrichments(
            db,
            organization_id=organization_id,
            contacts=list(imported_contacts.values()),
        )
        for enquiry in imported_enquiries:
            enrichment = enrichments.get(enquiry.contact_id, InboundOwnershipEnrichmentResponse())
            summary.owner_matches += int(enrichment.matched)
            summary.current_owners += int(enrichment.current_owner)
            summary.former_owners += int(enrichment.former_owner)
            summary.rental_owners += int(enrichment.rental_owner)
            summary.portfolio_owners += int(enrichment.multiple_property_owner)
            summary.high_priority += int(_lead_priority(enquiry, enrichment).band == "high")
        record.status = "completed"
        record.summary = summary.model_dump()
        record.completed_at = _utcnow()
        db.add(record)
        await db.commit()
        await db.refresh(record)
    except Exception as exc:
        await db.rollback()
        record.status = "failed"
        record.error_message = str(exc)[:1_000]
        record.summary = summary.model_dump()
        record.completed_at = _utcnow()
        db.add(record)
        await db.commit()
    return _import_response(record)


def _import_response(record: CrmInboundImport) -> InboundImportResponse:
    return InboundImportResponse(
        id=record.id or 0,
        name=record.name,
        original_filename=record.original_filename,
        status=record.status,  # type: ignore[arg-type]
        summary=InboundImportSummary.model_validate(record.summary or {}),
        mapping=record.mapping or {},
        error_message=record.error_message,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


async def list_inbound_imports(
    db: AsyncSession, organization_id: str
) -> list[InboundImportResponse]:
    result = await db.exec(
        select(CrmInboundImport)
        .where(CrmInboundImport.organization_id == organization_id)
        .order_by(CrmInboundImport.created_at.desc())
    )
    return [_import_response(item) for item in result.all()]


async def delete_inbound_import(db: AsyncSession, import_id: int, organization_id: str) -> None:
    result = await db.exec(
        select(CrmInboundImport).where(
            CrmInboundImport.id == import_id,
            CrmInboundImport.organization_id == organization_id,
        )
    )
    record = result.first()
    if not record:
        raise HTTPException(status_code=404, detail="Inbound import not found")
    imported_enquiries = await db.exec(
        select(CrmInboundEnquiry.contact_id).where(
            CrmInboundEnquiry.source_import_id == import_id,
            CrmInboundEnquiry.organization_id == organization_id,
        )
    )
    contact_ids = list(dict.fromkeys(imported_enquiries.all()))
    await db.exec(
        delete(CrmInboundEnquiry).where(
            CrmInboundEnquiry.source_import_id == import_id,
            CrmInboundEnquiry.organization_id == organization_id,
        )
    )
    if contact_ids:
        await db.exec(
            delete(CrmInboundContact).where(
                CrmInboundContact.organization_id == organization_id,
                CrmInboundContact.id.in_(contact_ids),  # type: ignore[union-attr]
                ~exists(
                    select(CrmInboundEnquiry.id).where(
                        CrmInboundEnquiry.contact_id == CrmInboundContact.id
                    )
                ),
            )
        )
    await db.delete(record)
    await db.commit()


async def _registry_profiles(
    db: AsyncSession,
    *,
    contact: CrmInboundContact,
    criteria: dict[str, Any],
) -> list[InboundRegistryProfileResponse]:
    conditions = [
        func.lower(func.trim(CrmPropertyContactClaim.contact_name))
        == contact.full_name.strip().lower()
    ]
    if contact.phone:
        conditions.extend(
            [
                CrmPropertyContactClaim.phone_primary == contact.phone,
                CrmPropertyContactClaim.phone_alternate == contact.phone,
            ]
        )
    if contact.email:
        conditions.append(
            func.lower(CrmPropertyContactClaim.email_primary) == contact.email.lower()
        )
    result = await db.exec(
        select(CrmPropertyContactClaim)
        .where(
            CrmPropertyContactClaim.organization_id == contact.organization_id,
            or_(*conditions),
        )
        .order_by(CrmPropertyContactClaim.confidence_score.desc())
        .limit(100)
    )
    claims = list(result.all())
    sale_evidence, lease_evidence = await _registry_transaction_evidence(claims)
    building = _token(criteria.get("building"))
    unit_number = _token(criteria.get("unit_number"))
    location_tokens = [_token(item) for item in _locations(criteria)]
    profiles: list[InboundRegistryProfileResponse] = []
    seen: set[tuple[str, str]] = set()
    for claim in claims:
        property_identity = (claim.owner_key, claim.property_key)
        if property_identity in seen:
            continue
        seen.add(property_identity)
        phone_match = bool(
            contact.phone and contact.phone in {claim.phone_primary, claim.phone_alternate}
        )
        email_match = bool(
            contact.email
            and claim.email_primary
            and contact.email.casefold() == claim.email_primary.casefold()
        )
        claim_building = _token(claim.building_name or claim.project_name)
        exact_property = bool(
            building
            and unit_number
            and building in claim_building
            and unit_number == _token(claim.unit_number)
        )
        location_match = bool(
            location_tokens
            and any(
                location
                and location
                in _token(f"{claim.area_name} {claim.project_name} {claim.building_name}")
                for location in location_tokens
            )
        )
        if phone_match or email_match:
            identity_strength = "exact"
            identity_reason = "Contact detail matches the owner registry"
        elif exact_property:
            identity_strength = "exact"
            identity_reason = "Name, building, and unit match the owner registry"
        elif building and building in claim_building:
            identity_strength = "possible"
            identity_reason = "Name and building match; unit confirmation is still required"
        elif location_match:
            identity_strength = "possible"
            identity_reason = "Name and stated location match a registry profile"
        else:
            identity_strength = "weak"
            identity_reason = "Name-only registry match; verify identity before using it"
        sale = sale_evidence.get(f"{_token(claim.building_name)}|{_token(claim.unit_number)}", {})
        lease = lease_evidence.get(claim.unit_candidate_key or "", {})
        sale_date = sale.get("transaction_date")
        lease_start = lease.get("lease_start")
        lease_end = lease.get("lease_end") or claim.lease_end
        profiles.append(
            InboundRegistryProfileResponse(
                owner_key=claim.owner_key,
                contact_name=claim.contact_name,
                ownership_status=claim.ownership_status,
                identity_strength=identity_strength,  # type: ignore[arg-type]
                identity_reason=identity_reason,
                area_name=claim.area_name,
                project_name=claim.project_name,
                building_name=claim.building_name,
                unit_number=claim.unit_number,
                property_type=claim.property_type,
                transaction_date=claim.transaction_date,
                transaction_price_aed=claim.transaction_price_aed,
                latest_sale_date=claim.latest_sale_date
                or (sale_date if isinstance(sale_date, date) else None),
                latest_sale_price_aed=claim.latest_sale_price_aed
                or _amount(sale.get("sale_amount_aed")),
                later_sale_date=claim.later_sale_date,
                ltv_pct=float(sale["ltv_pct"]) if sale.get("ltv_pct") is not None else None,
                seller_type=_text(sale.get("seller_type")) or None,
                lease_start=lease_start if isinstance(lease_start, date) else None,
                lease_end=lease_end if isinstance(lease_end, date) else None,
                annual_rent_aed=_amount(lease.get("annual_rent_aed")) or claim.annual_rent_aed,
                contract_state=_text(lease.get("contract_state")) or None,
                lead_id=claim.lead_id,
            )
        )
    strength_order = {"exact": 3, "possible": 2, "weak": 1}
    profiles.sort(
        key=lambda item: (
            strength_order[item.identity_strength],
            item.latest_sale_date or date.min,
        ),
        reverse=True,
    )
    return profiles[:10]


def _contact_response(
    contact: CrmInboundContact,
    registry_profiles: list[InboundRegistryProfileResponse] | None = None,
) -> InboundContactResponse:
    return InboundContactResponse(
        id=contact.id or 0,
        full_name=contact.full_name,
        phone=contact.phone,
        email=contact.email,
        whatsapp=contact.whatsapp,
        preferred_language=contact.preferred_language,
        preferred_channel=contact.preferred_channel,
        consent_status=contact.consent_status,
        do_not_contact=contact.do_not_contact,
        registry_profiles=registry_profiles or [],
    )


async def _enquiry_response(
    db: AsyncSession,
    enquiry: CrmInboundEnquiry,
    *,
    contact: CrmInboundContact | None = None,
    include_registry_profiles: bool = False,
    include_history: bool = False,
    match_counts: tuple[int, int] | None = None,
    ownership_enrichment: InboundOwnershipEnrichmentResponse | None = None,
) -> InboundEnquiryResponse:
    contact = contact or await db.get(CrmInboundContact, enquiry.contact_id)
    if not contact or contact.organization_id != enquiry.organization_id:
        raise HTTPException(status_code=500, detail="Inbound contact is missing")
    notes = []
    activities = []
    if include_history:
        notes_result = await db.exec(
            select(CrmInboundNote)
            .where(CrmInboundNote.enquiry_id == enquiry.id)
            .order_by(CrmInboundNote.created_at.desc())
        )
        notes = list(notes_result.all())
        activities_result = await db.exec(
            select(CrmInboundActivity)
            .where(CrmInboundActivity.enquiry_id == enquiry.id)
            .order_by(CrmInboundActivity.created_at.desc())
        )
        activities = list(activities_result.all())
    if match_counts is None:
        matches_result = await db.exec(
            select(CrmInboundMatch).where(CrmInboundMatch.enquiry_id == enquiry.id)
        )
        matches = matches_result.all()
        match_counts = (
            len([item for item in matches if item.state not in {"dismissed", "stale"}]),
            len([item for item in matches if item.state == "saved"]),
        )
    registry_profiles = (
        await _registry_profiles(db, contact=contact, criteria=enquiry.criteria)
        if include_registry_profiles
        else []
    )
    if ownership_enrichment is None:
        ownership_enrichment = (
            await _bulk_ownership_enrichments(
                db,
                organization_id=enquiry.organization_id,
                contacts=[contact],
            )
        ).get(contact.id or 0, InboundOwnershipEnrichmentResponse())
    return InboundEnquiryResponse(
        id=enquiry.id or 0,
        contact=_contact_response(contact, registry_profiles),
        record_kind=enquiry.record_kind,  # type: ignore[arg-type]
        intent=enquiry.intent,  # type: ignore[arg-type]
        status=enquiry.status,  # type: ignore[arg-type]
        assigned_user_id=enquiry.assigned_user_id,
        source=enquiry.source,
        campaign=enquiry.campaign,
        source_import_id=enquiry.source_import_id,
        enquiry_date=enquiry.enquiry_date,
        criteria=enquiry.criteria,
        strict_fields=enquiry.strict_fields,
        raw_notes=enquiry.raw_notes,
        observed_data=enquiry.observed_data,
        inferred_data=enquiry.inferred_data,
        confirmed_data=enquiry.confirmed_data,
        qualification=enquiry.qualification,
        extraction_confidence=enquiry.extraction_confidence,
        review_reasons=enquiry.review_reasons,
        next_follow_up=enquiry.next_follow_up,
        first_response_due_at=enquiry.first_response_due_at,
        first_contact_at=enquiry.first_contact_at,
        last_contact_at=enquiry.last_contact_at,
        contact_attempt_count=enquiry.contact_attempt_count,
        lost_reason=enquiry.lost_reason,
        sla_state=_sla_state(enquiry),  # type: ignore[arg-type]
        qualification_complete=_qualification_complete(enquiry),
        ownership_enrichment=ownership_enrichment,
        priority=_lead_priority(enquiry, ownership_enrichment),
        tags=enquiry.tags,
        notes=[
            InboundNoteResponse(
                id=note.id or 0, body=note.body, user_id=note.user_id, created_at=note.created_at
            )
            for note in notes
        ],
        activities=[
            InboundActivityResponse(
                id=activity.id or 0,
                activity_type=activity.activity_type,
                body=activity.body,
                user_id=activity.user_id,
                metadata=activity.metadata_json,
                created_at=activity.created_at,
            )
            for activity in activities
        ],
        match_count=match_counts[0],
        saved_match_count=match_counts[1],
        created_at=enquiry.created_at,
        updated_at=enquiry.updated_at,
    )


async def list_inbound_enquiries(
    db: AsyncSession,
    *,
    organization_id: str,
    intent_group: str | None,
    workspace: str | None,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> InboundEnquiryListResponse:
    result = await db.exec(
        select(CrmInboundEnquiry)
        .where(CrmInboundEnquiry.organization_id == organization_id)
        .order_by(CrmInboundEnquiry.enquiry_date.desc())
    )
    enquiries = list(result.all())
    all_enquiries = enquiries[:]
    all_contacts: dict[int, CrmInboundContact] = {}
    if all_enquiries:
        contacts_result = await db.exec(
            select(CrmInboundContact).where(
                CrmInboundContact.id.in_([item.contact_id for item in all_enquiries])  # type: ignore[union-attr]
            )
        )
        all_contacts = {item.id or 0: item for item in contacts_result.all()}
    all_enrichments = await _bulk_ownership_enrichments(
        db,
        organization_id=organization_id,
        contacts=list(all_contacts.values()),
    )
    all_priorities = {
        item.id or 0: _lead_priority(
            item,
            all_enrichments.get(item.contact_id, InboundOwnershipEnrichmentResponse()),
        )
        for item in all_enquiries
    }
    if intent_group == "demand":
        enquiries = [item for item in enquiries if item.intent in {"buy", "rent"}]
    elif intent_group == "instructions":
        enquiries = [item for item in enquiries if item.intent in {"sell", "let"}]
    if workspace == "inbox":
        enquiries = [item for item in enquiries if _belongs_in_inbox(item)]
    elif workspace == "unqualified":
        enquiries = [item for item in enquiries if item.record_kind == "unqualified_contact"]
    elif workspace == "qualified":
        enquiries = [item for item in enquiries if item.status in _QUALIFIED_STATUSES]
    elif workspace == "closed":
        enquiries = [
            item for item in enquiries if item.status in {"nurture", "closed_lost", "disqualified"}
        ]
    if status:
        enquiries = [item for item in enquiries if item.status == status]
    contacts = {
        contact_id: contact
        for contact_id, contact in all_contacts.items()
        if contact_id in {item.contact_id for item in enquiries}
    }
    if search:
        term = search.casefold()
        enquiries = [
            item
            for item in enquiries
            if term
            in contacts.get(
                item.contact_id,
                CrmInboundContact(
                    organization_id="", full_name="", created_at=_utcnow(), updated_at=_utcnow()
                ),
            ).full_name.casefold()
            or term in json.dumps(item.criteria).casefold()
            or term in (item.campaign or "").casefold()
        ]
    enrichments = {
        contact_id: enrichment
        for contact_id, enrichment in all_enrichments.items()
        if contact_id in {item.contact_id for item in enquiries}
    }
    priorities = {
        item.id or 0: _lead_priority(
            item,
            enrichments.get(item.contact_id, InboundOwnershipEnrichmentResponse()),
        )
        for item in enquiries
    }
    enquiries.sort(
        key=lambda item: (
            priorities[item.id or 0].score,
            item.enquiry_date,
        ),
        reverse=True,
    )
    total = len(enquiries)
    page = enquiries[offset : offset + limit]
    count_map: dict[int, tuple[int, int]] = {}
    if page:
        counts_result = await db.exec(
            select(CrmInboundMatch.enquiry_id, CrmInboundMatch.state, func.count())
            .where(CrmInboundMatch.enquiry_id.in_([item.id for item in page]))  # type: ignore[union-attr]
            .group_by(CrmInboundMatch.enquiry_id, CrmInboundMatch.state)
        )
        aggregate: dict[int, list[int]] = {}
        for enquiry_id, match_state, count in counts_result.all():
            values = aggregate.setdefault(enquiry_id, [0, 0])
            if match_state not in {"dismissed", "stale"}:
                values[0] += count
            if match_state == "saved":
                values[1] += count
        count_map = {key: (value[0], value[1]) for key, value in aggregate.items()}
    responses = [
        await _enquiry_response(
            db,
            item,
            contact=contacts.get(item.contact_id),
            match_counts=count_map.get(item.id or 0, (0, 0)),
            ownership_enrichment=enrichments.get(
                item.contact_id, InboundOwnershipEnrichmentResponse()
            ),
        )
        for item in page
    ]
    return InboundEnquiryListResponse(
        enquiries=responses,
        total=total,
        summary={
            "total": len(all_enquiries),
            "demand": len([item for item in all_enquiries if item.intent in {"buy", "rent"}]),
            "instructions": len([item for item in all_enquiries if item.intent in {"sell", "let"}]),
            "needs_review": len([item for item in all_enquiries if item.status == "needs_review"]),
            "unassigned": len([item for item in all_enquiries if not item.assigned_user_id]),
            "unqualified": len(
                [item for item in all_enquiries if item.record_kind == "unqualified_contact"]
            ),
            "qualified": len(
                [item for item in all_enquiries if item.status in _QUALIFIED_STATUSES]
            ),
            "overdue": len([item for item in all_enquiries if _sla_state(item) == "overdue"]),
            "follow_up_due": len(
                [
                    item
                    for item in all_enquiries
                    if item.next_follow_up and item.next_follow_up <= _utcnow().date()
                ]
            ),
            "owner_matched": len(
                [
                    item
                    for item in all_enquiries
                    if all_enrichments.get(
                        item.contact_id, InboundOwnershipEnrichmentResponse()
                    ).matched
                ]
            ),
            "portfolio_owners": len(
                [
                    item
                    for item in all_enquiries
                    if all_enrichments.get(
                        item.contact_id, InboundOwnershipEnrichmentResponse()
                    ).multiple_property_owner
                ]
            ),
            "high_priority": len(
                [item for item in all_enquiries if all_priorities[item.id or 0].band == "high"]
            ),
        },
    )


async def get_inbound_enquiry(
    db: AsyncSession, enquiry_id: int, organization_id: str
) -> InboundEnquiryResponse:
    enquiry = await db.get(CrmInboundEnquiry, enquiry_id)
    if not enquiry or enquiry.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Inbound enquiry not found")
    return await _enquiry_response(
        db, enquiry, include_registry_profiles=True, include_history=True
    )


async def update_inbound_enquiry(
    db: AsyncSession,
    *,
    enquiry_id: int,
    organization_id: str,
    user_id: str,
    payload: InboundEnquiryUpdate,
) -> InboundEnquiryResponse:
    enquiry = await db.get(CrmInboundEnquiry, enquiry_id)
    if not enquiry or enquiry.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Inbound enquiry not found")
    changes = payload.model_dump(exclude_unset=True)
    contact_changes = {
        key: changes.pop(key)
        for key in ("consent_status", "do_not_contact", "preferred_channel")
        if key in changes
    }
    previous_status = enquiry.status
    matching_changed = bool(
        {"intent", "record_kind", "criteria", "strict_fields", "confirmed_data"} & changes.keys()
    )
    for key, value in changes.items():
        if key == "notes":
            enquiry.raw_notes = value
        else:
            setattr(enquiry, key, value)
    if changes.get("intent") and changes["intent"] != "unknown":
        enquiry.record_kind = "opportunity"
        enquiry.confirmed_data = {
            **(enquiry.confirmed_data or {}),
            "intent": changes["intent"],
        }
    if changes.get("criteria") is not None:
        enquiry.confirmed_data = {
            **(enquiry.confirmed_data or {}),
            "criteria": changes["criteria"],
        }
    if enquiry.intent == "unknown":
        enquiry.record_kind = "unqualified_contact"
    enquiry.updated_at = _utcnow()
    db.add(enquiry)
    if contact_changes:
        contact = await db.get(CrmInboundContact, enquiry.contact_id)
        if not contact or contact.organization_id != organization_id:
            raise HTTPException(status_code=500, detail="Inbound contact is missing")
        for key, value in contact_changes.items():
            setattr(contact, key, value)
        contact.updated_at = enquiry.updated_at
        db.add(contact)
        db.add(
            CrmInboundActivity(
                enquiry_id=enquiry_id,
                organization_id=organization_id,
                user_id=user_id,
                activity_type="contactability_updated",
                body="Contact permissions or preferred channel updated",
                metadata_json=contact_changes,
                created_at=enquiry.updated_at,
            )
        )
    if matching_changed:
        await db.exec(
            CrmInboundMatch.__table__.update()
            .where(CrmInboundMatch.enquiry_id == enquiry_id)
            .values(state="stale", updated_at=enquiry.updated_at)
        )
    if enquiry.status != previous_status:
        db.add(
            CrmInboundActivity(
                enquiry_id=enquiry_id,
                organization_id=organization_id,
                user_id=user_id,
                activity_type="status_changed",
                body=f"Stage changed from {previous_status} to {enquiry.status}",
                metadata_json={"from": previous_status, "to": enquiry.status},
                created_at=enquiry.updated_at,
            )
        )
    await db.commit()
    await db.refresh(enquiry)
    return await _enquiry_response(
        db, enquiry, include_registry_profiles=True, include_history=True
    )


async def add_inbound_note(
    db: AsyncSession, *, enquiry_id: int, organization_id: str, user_id: str, body: str
) -> InboundEnquiryResponse:
    enquiry = await db.get(CrmInboundEnquiry, enquiry_id)
    if not enquiry or enquiry.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Inbound enquiry not found")
    db.add(
        CrmInboundNote(
            enquiry_id=enquiry_id,
            organization_id=organization_id,
            user_id=user_id,
            body=body.strip(),
            created_at=_utcnow(),
        )
    )
    enquiry.updated_at = _utcnow()
    db.add(enquiry)
    db.add(
        CrmInboundActivity(
            enquiry_id=enquiry_id,
            organization_id=organization_id,
            user_id=user_id,
            activity_type="note",
            body=body.strip(),
            metadata_json={},
            created_at=enquiry.updated_at,
        )
    )
    await db.commit()
    return await _enquiry_response(
        db, enquiry, include_registry_profiles=True, include_history=True
    )


async def add_inbound_activity(
    db: AsyncSession,
    *,
    enquiry_id: int,
    organization_id: str,
    user_id: str,
    activity_type: str,
    body: str | None,
) -> InboundEnquiryResponse:
    enquiry = await db.get(CrmInboundEnquiry, enquiry_id)
    if not enquiry or enquiry.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Inbound enquiry not found")
    now = _utcnow()
    enquiry.contact_attempt_count += 1
    enquiry.last_contact_at = now
    enquiry.first_contact_at = enquiry.first_contact_at or now
    if enquiry.status in {"new", "assigned", "needs_review"}:
        enquiry.status = "attempted"
    enquiry.updated_at = now
    db.add(enquiry)
    db.add(
        CrmInboundActivity(
            enquiry_id=enquiry_id,
            organization_id=organization_id,
            user_id=user_id,
            activity_type=activity_type,
            body=body.strip() if body else None,
            metadata_json={"attempt": enquiry.contact_attempt_count},
            created_at=now,
        )
    )
    await db.commit()
    await db.refresh(enquiry)
    return await _enquiry_response(
        db, enquiry, include_registry_profiles=True, include_history=True
    )


def _locations(criteria: dict[str, Any]) -> list[str]:
    value = criteria.get("locations", [])
    return (
        [str(item) for item in value] if isinstance(value, list) else [str(value)] if value else []
    )


def _location_fit(criteria: dict[str, Any], *values: str) -> tuple[int, str]:
    requested = _locations(criteria)
    if not requested:
        return 0, "Preferred location is missing"
    haystack = " ".join(values).casefold()
    if any(item.casefold() in haystack or haystack in item.casefold() for item in requested):
        return 20, f"Matches {requested[0]}"
    return 0, "Outside preferred location"


def _budget_fit(criteria: dict[str, Any], value: int | None) -> tuple[int, str]:
    maximum = int(criteria.get("budget_max_aed") or 0)
    minimum = int(criteria.get("budget_min_aed") or 0)
    if not maximum and not minimum:
        return 0, "Budget is missing"
    if not value:
        return 5, "Price requires verification"
    if (not minimum or value >= minimum) and (not maximum or value <= maximum):
        return 15, "Within stated budget"
    if maximum and value <= maximum * 1.1 and value >= minimum * 0.9:
        return 9, "Within flexible budget margin"
    return 0, "Outside budget"


def _bedroom_fit(criteria: dict[str, Any], value: str) -> tuple[int, str]:
    requested = criteria.get("bedrooms_min")
    if requested is None:
        return 0, "Bedroom requirement is missing"
    match = re.search(r"\d+", value)
    observed = int(match.group()) if match else 0 if "studio" in value.lower() else None
    if observed == int(requested):
        return 10, "Exact bedroom match"
    if observed is not None and abs(observed - int(requested)) <= 1:
        return 6, "Within flexible bedroom range"
    return 0, "Bedroom mismatch"


def _property_fit(criteria: dict[str, Any], value: str) -> int:
    requested = _canonical_property_type(criteria.get("property_type"))
    if not requested:
        return 0
    observed = _canonical_property_type(value)
    return 10 if requested == observed else 0


def _canonical_property_type(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    aliases = {
        "flat": "apartment",
        "apartments": "apartment",
        "residential flat": "apartment",
        "residential flats": "apartment",
        "residential": "apartment",
        "unit": "apartment",
        "condo": "apartment",
        "condominium": "apartment",
        "hotel apartments": "apartment",
        "townhouses": "townhouse",
        "villas": "villa",
        "offices": "office",
    }
    return aliases.get(normalized, normalized)


def _listing_property_type(value: Any) -> str | None:
    normalized = _canonical_property_type(value)
    return normalized.title() if normalized else None


def _violates_strict_fields(
    strict_fields: list[str],
    *,
    location_points: int,
    budget_points: int,
    bedroom_points: int,
    property_points: int,
) -> bool:
    checks = {
        "locations": location_points,
        "budget_min_aed": budget_points,
        "budget_max_aed": budget_points,
        "bedrooms_min": bedroom_points,
        "bedrooms_max": bedroom_points,
        "property_type": property_points,
    }
    return any(checks.get(field, 1) == 0 for field in strict_fields)


def _optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def _listing_freshness() -> tuple[datetime | None, bool]:
    try:
        rows = await query(
            "SELECT max(parseDateTimeBestEffortOrNull(scraped_at)) AS refreshed FROM pf_listings_bronze",
            {},
        )
        refreshed = _optional_datetime(rows[0].get("refreshed") if rows else None)
        fresh = bool(
            refreshed and (_utcnow() - refreshed).total_seconds() <= _LISTING_MAX_AGE_HOURS * 3600
        )
        return refreshed, fresh
    except Exception:
        return None, False


async def _offplan_project_rows(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    requested_locations = _locations(criteria)
    return await query(
        f"""
        SELECT
            p.project_id,
            p.project_name,
            p.developer_name,
            p.area_name,
            p.sale_status,
            p.units_in_sale,
            p.min_price_aed,
            p.max_price_aed,
            p.completion_date,
            p.readiness_progress,
            p.website_url,
            p.scraped_at,
            u.unit_type_key,
            u.unit_bedrooms,
            u.unit_type,
            u.price_from_aed AS unit_price_from,
            u.price_to_aed AS unit_price_to,
            u.area_from_sqft,
            u.area_to_sqft,
            u.units_amount
        FROM (
            SELECT
                project_id,
                project_name,
                developer_name,
                area_name,
                sale_status,
                units_in_sale,
                min_price_aed,
                max_price_aed,
                completion_date,
                readiness_progress,
                website_url,
                scraped_at
            FROM reelly_projects_bronze
            WHERE {reelly_dubai_project_scope()}
            ORDER BY parseDateTimeBestEffortOrNull(scraped_at) DESC
            LIMIT 1 BY project_id
        ) AS p
        LEFT JOIN (
            SELECT
                project_id,
                unit_type_key,
                unit_bedrooms,
                unit_type,
                price_from_aed,
                price_to_aed,
                area_from_sqft,
                area_to_sqft,
                units_amount
            FROM reelly_project_unit_types_bronze
            ORDER BY parseDateTimeBestEffortOrNull(scraped_at) DESC
            LIMIT 1 BY unit_type_key
        ) AS u USING (project_id)
        WHERE
            lowerUTF8(p.sale_status) = 'on sale'
            AND (
                {{area:String}} = ''
                OR positionCaseInsensitiveUTF8(p.area_name, {{area:String}}) > 0
                OR positionCaseInsensitiveUTF8(p.project_name, {{area:String}}) > 0
            )
        ORDER BY coalesce(u.price_from_aed, p.min_price_aed) ASC
        LIMIT 120
        """,
        {"area": requested_locations[0] if requested_locations else ""},
    )


async def _offplan_catalog_freshness() -> datetime | None:
    try:
        rows = await query(
            "SELECT max(parseDateTimeBestEffortOrNull(scraped_at)) AS refreshed "
            "FROM reelly_projects_bronze "
            f"WHERE {reelly_dubai_project_scope()}",
            {},
        )
        return _optional_datetime(rows[0].get("refreshed") if rows else None)
    except Exception:
        return None


def _json_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.isoformat() if isinstance(value, date | datetime) else value
        for key, value in row.items()
    }


async def _rental_opportunity_rows(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    requested_locations = _locations(criteria)
    return await query(
        """
        SELECT
            c.unit_candidate_key,
            c.event_key,
            c.building_name,
            c.project_name,
            c.area_name,
            c.property_type,
            c.bedrooms,
            c.size_sqft,
            c.annual_rent_aed,
            c.purchase_price_aed,
            c.lease_start,
            c.lease_end,
            c.contract_state,
            c.observed_contracts,
            m.unit_number,
            m.last_purchase_date,
            m.matched_sale_price,
            m.match_status,
            m.latest_detail_url
        FROM dxbi_rental_unit_candidates AS c FINAL
        LEFT JOIN dxbi_rental_sale_matches AS m FINAL USING (unit_candidate_key)
        WHERE
            c.lease_end BETWEEN today() - 1825 AND today() + 90
            AND (
                {area:String} = ''
                OR positionCaseInsensitiveUTF8(c.area_name, {area:String}) > 0
                OR positionCaseInsensitiveUTF8(c.project_name, {area:String}) > 0
                OR positionCaseInsensitiveUTF8(c.building_name, {area:String}) > 0
            )
            AND (
                {property_type:String} = ''
                OR lowerUTF8(c.property_type) = lowerUTF8({property_type:String})
            )
        ORDER BY
            abs(dateDiff('day', today(), c.lease_end)) ASC,
            c.annual_rent_aed DESC
        LIMIT 40
        """,
        {
            "area": requested_locations[0] if requested_locations else "",
            "property_type": str(criteria.get("property_type") or ""),
        },
    )


def _match_response(item: CrmInboundMatch) -> InboundMatchResponse:
    return InboundMatchResponse(
        id=item.id or 0,
        target_type=item.target_type,  # type: ignore[arg-type]
        target_key=item.target_key,
        state=item.state,  # type: ignore[arg-type]
        fit=item.fit,  # type: ignore[arg-type]
        title=item.title,
        subtitle=item.subtitle,
        reasons=item.reasons,
        missing_fields=item.missing_fields,
        snapshot=item.snapshot,
        generated_at=item.generated_at,
    )


async def _upsert_match(
    db: AsyncSession,
    *,
    enquiry: CrmInboundEnquiry,
    target_type: str,
    target_key: str,
    score: int,
    title: str,
    subtitle: str,
    reasons: list[str],
    breakdown: dict[str, Any],
    snapshot: dict[str, Any],
) -> CrmInboundMatch | None:
    if score < 50:
        return None
    result = await db.exec(
        select(CrmInboundMatch).where(
            CrmInboundMatch.enquiry_id == enquiry.id,
            CrmInboundMatch.target_type == target_type,
            CrmInboundMatch.target_key == target_key,
        )
    )
    item = result.first()
    now = _utcnow()
    missing_fields = [
        label
        for label, present in (
            ("location", bool(_locations(enquiry.criteria))),
            (
                "budget",
                bool(
                    enquiry.criteria.get("budget_min_aed")
                    or enquiry.criteria.get("budget_max_aed")
                    or enquiry.criteria.get("expected_price_aed")
                ),
            ),
            (
                "property details",
                bool(
                    enquiry.criteria.get("property_type")
                    or enquiry.criteria.get("bedrooms_min") is not None
                    or enquiry.criteria.get("unit_number")
                ),
            ),
        )
        if not present
    ]
    fit = "exact" if score >= 85 and not missing_fields else "near" if score >= 65 else "review"
    if item is None:
        item = CrmInboundMatch(
            enquiry_id=enquiry.id or 0,
            organization_id=enquiry.organization_id,
            target_type=target_type,
            target_key=target_key,
            score=score,
            title=title,
            subtitle=subtitle,
            reasons=reasons,
            score_breakdown=breakdown,
            fit=fit,
            missing_fields=missing_fields,
            snapshot=snapshot,
            generated_at=now,
            updated_at=now,
        )
    elif item.state != "dismissed":
        if item.state == "stale":
            item.state = "suggested"
        item.score = score
        item.title = title
        item.subtitle = subtitle
        item.reasons = reasons
        item.score_breakdown = breakdown
        item.fit = fit
        item.missing_fields = missing_fields
        item.snapshot = snapshot
        item.generated_at = now
        item.updated_at = now
    db.add(item)
    return item


async def refresh_inbound_matches(
    db: AsyncSession,
    *,
    enquiry_id: int,
    organization_id: str,
    expand_units: bool = False,
) -> InboundMatchesResponse:
    enquiry = await db.get(CrmInboundEnquiry, enquiry_id)
    if not enquiry or enquiry.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Inbound enquiry not found")
    if not _qualification_complete(enquiry):
        raise HTTPException(
            status_code=409,
            detail="Confirm the enquiry intent and minimum property requirements before matching",
        )
    criteria = enquiry.criteria or {}
    await db.exec(
        CrmInboundMatch.__table__.update()
        .where(
            CrmInboundMatch.enquiry_id == enquiry_id,
            CrmInboundMatch.state.notin_(["saved", "dismissed"]),
        )
        .values(state="stale", updated_at=_utcnow())
    )
    generated: list[CrmInboundMatch] = []

    if enquiry.intent in {"buy", "rent"}:
        requested_locations = _locations(criteria)
        claims_statement = select(CrmPropertyContactClaim).where(
            CrmPropertyContactClaim.organization_id == organization_id,
            CrmPropertyContactClaim.ownership_status.in_(  # type: ignore[union-attr]
                ["verified_current_owner", "probable_current_owner"]
            ),
        )
        if requested_locations:
            location_pattern = f"%{requested_locations[0]}%"
            claims_statement = claims_statement.where(
                or_(
                    CrmPropertyContactClaim.area_name.ilike(location_pattern),  # type: ignore[union-attr]
                    CrmPropertyContactClaim.project_name.ilike(location_pattern),  # type: ignore[union-attr]
                    CrmPropertyContactClaim.building_name.ilike(location_pattern),  # type: ignore[union-attr]
                )
            )
        claims_result = await db.exec(
            claims_statement.order_by(CrmPropertyContactClaim.confidence_score.desc()).limit(80)
        )
        best_by_owner: dict[str, CrmPropertyContactClaim] = {}
        for claim in claims_result.all():
            current = best_by_owner.get(claim.owner_key)
            if current is None or claim.confidence_score > current.confidence_score:
                best_by_owner[claim.owner_key] = claim
        for claim in best_by_owner.values():
            location, location_reason = _location_fit(
                criteria, claim.area_name, claim.project_name, claim.building_name
            )
            owner_value = (
                claim.annual_rent_aed if enquiry.intent == "rent" else claim.latest_sale_price_aed
            )
            budget, budget_reason = _budget_fit(criteria, owner_value)
            property_points = _property_fit(criteria, claim.property_type)
            if _violates_strict_fields(
                enquiry.strict_fields,
                location_points=location,
                budget_points=budget,
                bedroom_points=5,
                property_points=property_points,
            ):
                continue
            actionability = 20 if claim.phone_primary or claim.email_primary else 10
            timing = 10 if claim.lease_end else 3
            score = min(100, location + budget + property_points + 15 + actionability + timing)
            item = await _upsert_match(
                db,
                enquiry=enquiry,
                target_type="owner",
                target_key=claim.owner_key,
                score=score,
                title=claim.contact_name,
                subtitle=f"{claim.building_name or claim.project_name} · Unit {claim.unit_number}",
                reasons=[
                    location_reason,
                    budget_reason,
                    "Current ownership evidence",
                    "Contact available" if actionability == 20 else "Contact enrichment needed",
                ],
                breakdown={
                    "requirements": location + budget + property_points + 15,
                    "actionability": actionability,
                    "timing": timing,
                },
                snapshot={
                    "owner_key": claim.owner_key,
                    "phone": claim.phone_primary,
                    "email": claim.email_primary,
                    "area_name": claim.area_name,
                    "project_name": claim.project_name,
                    "building_name": claim.building_name,
                    "unit_number": claim.unit_number,
                    "latest_sale_price_aed": claim.latest_sale_price_aed,
                    "lease_end": claim.lease_end.isoformat() if claim.lease_end else None,
                },
            )
            if item:
                generated.append(item)

        for lead in await _rental_opportunity_rows(criteria):
            location, location_reason = _location_fit(
                criteria,
                str(lead.get("area_name") or ""),
                str(lead.get("project_name") or ""),
                str(lead.get("building_name") or ""),
            )
            price = (
                int(lead.get("annual_rent_aed") or 0) or None
                if enquiry.intent == "rent"
                else int(lead.get("matched_sale_price") or lead.get("purchase_price_aed") or 0)
                or None
            )
            budget, budget_reason = _budget_fit(criteria, price)
            bedrooms = str(lead.get("bedrooms") or "")
            bedroom, bedroom_reason = _bedroom_fit(criteria, bedrooms)
            property_type = str(lead.get("property_type") or "")
            property_points = _property_fit(criteria, property_type)
            if _violates_strict_fields(
                enquiry.strict_fields,
                location_points=location,
                budget_points=budget,
                bedroom_points=bedroom,
                property_points=property_points,
            ):
                continue
            score = min(100, location + budget + bedroom + property_points + 7 + 10 + 10)
            item = await _upsert_match(
                db,
                enquiry=enquiry,
                target_type="unit",
                target_key=str(lead["unit_candidate_key"]),
                score=score,
                title=f"{lead.get('building_name') or 'Building'} · Unit {lead.get('unit_number') or 'unresolved'}",
                subtitle=f"{bedrooms or 'Layout pending'} · AED {price:,}"
                if price
                else f"{bedrooms or 'Layout pending'} · value pending",
                reasons=[
                    location_reason,
                    budget_reason,
                    bedroom_reason,
                    f"Lease ends {lead.get('lease_end')}",
                ],
                breakdown={
                    "requirements": location + budget + bedroom + property_points,
                    "actionability": 7,
                    "timing": 10,
                },
                snapshot=_json_snapshot(lead),
            )
            if item:
                generated.append(item)

        if expand_units and enquiry.intent == "buy":
            sales_rows = await query(
                """
                SELECT
                    sales.building_key,
                    lowerUTF8(sales.unit_number) AS normalized_unit,
                    argMax(sales.sale_key, sales.transaction_date) AS sale_key,
                    argMax(sales.building_name, sales.transaction_date) AS building_name,
                    argMax(sales.unit_number, sales.transaction_date) AS unit_number,
                    argMax(sales.area_name, sales.transaction_date) AS area_name,
                    argMax(sales.property_type, sales.transaction_date) AS property_type,
                    argMax(sales.bedrooms, sales.transaction_date) AS bedrooms,
                    argMax(sales.size_sqft, sales.transaction_date) AS size_sqft,
                    argMax(sales.sale_amount_aed, sales.transaction_date) AS sale_amount_aed,
                    max(sales.transaction_date) AS latest_sale_date
                FROM (
                    SELECT *
                    FROM dxbi_sales_unit_events FINAL
                    WHERE
                        unit_number != ''
                        AND (
                            {area:String} = ''
                            OR positionCaseInsensitiveUTF8(area_name, {area:String}) > 0
                            OR positionCaseInsensitiveUTF8(building_name, {area:String}) > 0
                        )
                ) AS sales
                GROUP BY sales.building_key, normalized_unit
                ORDER BY latest_sale_date DESC
                LIMIT 120
                """,
                {"area": requested_locations[0] if requested_locations else ""},
            )
            existing_keys = {item.target_key for item in generated if item.target_type == "unit"}
            for row in sales_rows:
                target_key = (
                    f"registry:{row.get('building_key', '')}|{row.get('normalized_unit', '')}"
                )
                if target_key in existing_keys:
                    continue
                location, location_reason = _location_fit(
                    criteria, str(row.get("area_name") or ""), str(row.get("building_name") or "")
                )
                price = int(row.get("sale_amount_aed") or 0) or None
                budget, budget_reason = _budget_fit(criteria, price)
                bedroom, bedroom_reason = _bedroom_fit(criteria, str(row.get("bedrooms") or ""))
                property_points = _property_fit(criteria, str(row.get("property_type") or ""))
                if _violates_strict_fields(
                    enquiry.strict_fields,
                    location_points=location,
                    budget_points=budget,
                    bedroom_points=bedroom,
                    property_points=property_points,
                ):
                    continue
                score = min(100, location + budget + bedroom + property_points + 5 + 5 + 10)
                latest_sale_date = row.get("latest_sale_date")
                item = await _upsert_match(
                    db,
                    enquiry=enquiry,
                    target_type="unit",
                    target_key=target_key,
                    score=score,
                    title=f"{row.get('building_name') or 'Building'} · Unit {row.get('unit_number')}",
                    subtitle=f"{row.get('bedrooms') or 'Layout pending'} · {f'AED {price:,}' if price else 'value pending'}",
                    reasons=[
                        location_reason,
                        budget_reason,
                        bedroom_reason,
                        "Expanded sales-registry universe",
                    ],
                    breakdown={
                        "requirements": location + budget + bedroom + property_points,
                        "actionability": 5,
                        "timing": 5,
                    },
                    snapshot={
                        **row,
                        "latest_sale_date": latest_sale_date.isoformat()
                        if isinstance(latest_sale_date, date)
                        else latest_sale_date,
                        "source": "sales_registry",
                    },
                )
                if item:
                    generated.append(item)
                    existing_keys.add(target_key)
    else:
        reverse_intent = "buy" if enquiry.intent == "sell" else "rent"
        building = str(criteria.get("building") or "").strip()
        unit_number = str(criteria.get("unit_number") or "").strip()
        if building and unit_number:
            evidence_rows = await query(
                """
                SELECT
                    sale_key,
                    transaction_date,
                    building_name,
                    unit_number,
                    area_name,
                    property_type,
                    bedrooms,
                    size_sqft,
                    sale_amount_aed,
                    ltv_pct,
                    seller_type,
                    detail_url
                FROM dxbi_sales_unit_events FINAL
                WHERE
                    positionCaseInsensitiveUTF8(building_name, {building:String}) > 0
                    AND lowerUTF8(unit_number) = lowerUTF8({unit_number:String})
                ORDER BY transaction_date DESC
                LIMIT 1
                """,
                {"building": building, "unit_number": unit_number},
            )
            if evidence_rows:
                evidence = evidence_rows[0]
                sale_price = int(evidence.get("sale_amount_aed") or 0)
                item = await _upsert_match(
                    db,
                    enquiry=enquiry,
                    target_type="unit",
                    target_key=f"instruction:{evidence.get('sale_key')}",
                    score=98,
                    title=f"{evidence.get('building_name')} · Unit {evidence.get('unit_number')}",
                    subtitle=f"Latest recorded sale · AED {sale_price:,}",
                    reasons=[
                        "Exact building and unit match",
                        f"Purchased {evidence.get('transaction_date')}",
                        "Financing-at-purchase evidence available"
                        if evidence.get("ltv_pct") is not None
                        else "Financing evidence not exposed",
                    ],
                    breakdown={"identity": 50, "evidence": 28, "actionability": 20},
                    snapshot={**_json_snapshot(evidence), "source": "sales_registry"},
                )
                if item:
                    generated.append(item)
        reverse_result = await db.exec(
            select(CrmInboundEnquiry).where(
                CrmInboundEnquiry.organization_id == organization_id,
                CrmInboundEnquiry.intent == reverse_intent,
                CrmInboundEnquiry.id != enquiry.id,
                CrmInboundEnquiry.record_kind == "opportunity",
                CrmInboundEnquiry.status.in_(list(_QUALIFIED_STATUSES)),  # type: ignore[union-attr]
                CrmInboundEnquiry.status.notin_(["closed_lost", "won"]),  # type: ignore[union-attr]
            )
        )
        subject_locations = _locations(criteria)
        if not subject_locations and building:
            subject_locations = [building]
        subject_value = criteria.get("expected_price_aed") or criteria.get("budget_max_aed")
        for demand in reverse_result.all():
            locations = _locations(demand.criteria)
            location = (
                20
                if not subject_locations
                or not locations
                or any(
                    a.casefold() in b.casefold() or b.casefold() in a.casefold()
                    for a in subject_locations
                    for b in locations
                )
                else 0
            )
            budget, budget_reason = _budget_fit(demand.criteria, int(subject_value or 0) or None)
            bedroom, bedroom_reason = _bedroom_fit(
                demand.criteria, str(criteria.get("bedrooms_min", ""))
            )
            score = min(100, location + budget + bedroom + 10 + 20 + 10)
            contact = await db.get(CrmInboundContact, demand.contact_id)
            if not contact:
                continue
            item = await _upsert_match(
                db,
                enquiry=enquiry,
                target_type="demand",
                target_key=str(demand.id),
                score=score,
                title=contact.full_name,
                subtitle=f"Active {reverse_intent} enquiry · {demand.campaign or demand.source}",
                reasons=["Reverse demand match", budget_reason, bedroom_reason],
                breakdown={
                    "requirements": location + budget + bedroom + 10,
                    "actionability": 20,
                    "timing": 10,
                },
                snapshot={
                    "enquiry_id": demand.id,
                    "criteria": demand.criteria,
                    "phone": contact.phone,
                    "email": contact.email,
                },
            )
            if item:
                generated.append(item)

    listing_last_refresh, listing_fresh = await _listing_freshness()
    offplan_last_refresh = await _offplan_catalog_freshness()

    if listing_last_refresh and enquiry.intent in {"buy", "rent"}:
        requested_locations = _locations(criteria)
        listings = await list_listings_from_clickhouse(
            mode="sale" if enquiry.intent == "buy" else "rent",
            limit=60,
            area=requested_locations[0] if requested_locations else None,
            property_type=_listing_property_type(criteria.get("property_type")),
            bedrooms=str(criteria.get("bedrooms_min"))
            if criteria.get("bedrooms_min") is not None
            else None,
            price_max=criteria.get("budget_max_aed"),
        )
        for listing in listings.listings:
            location, location_reason = _location_fit(
                criteria,
                listing.area_name or "",
                listing.subcommunity_name or "",
                listing.tower_name or "",
            )
            listing_price = listing.price_value
            if enquiry.intent == "rent" and listing_price:
                period = (listing.price_period or "").casefold()
                if "month" in period:
                    listing_price *= 12
                elif "week" in period:
                    listing_price *= 52
                elif "day" in period:
                    listing_price *= 365
            budget, budget_reason = _budget_fit(criteria, listing_price)
            bedroom, bedroom_reason = _bedroom_fit(criteria, listing.bedrooms or "")
            property_points = _property_fit(criteria, listing.property_type or "")
            if _violates_strict_fields(
                enquiry.strict_fields,
                location_points=location,
                budget_points=budget,
                bedroom_points=bedroom,
                property_points=property_points,
            ):
                continue
            score = min(100, location + budget + bedroom + property_points + 20 + 10)
            item = await _upsert_match(
                db,
                enquiry=enquiry,
                target_type="listing",
                target_key=listing.listing_id,
                score=score,
                title=listing.title,
                subtitle=f"{listing.tower_name or listing.area_name or 'Dubai'} · AED {listing.price_value:,}"
                if listing.price_value
                else listing.tower_name or "Dubai",
                reasons=[
                    location_reason,
                    budget_reason,
                    bedroom_reason,
                    "Fresh active listing"
                    if listing_fresh
                    else "Listing catalog candidate; availability requires confirmation",
                ],
                breakdown={
                    "requirements": location + budget + bedroom + property_points,
                    "actionability": 20,
                    "timing": 10,
                },
                snapshot=listing.model_dump(mode="json"),
            )
            if item:
                generated.append(item)

    if enquiry.intent == "buy" and offplan_last_refresh:
        matched_projects: set[str] = set()
        for project in await _offplan_project_rows(criteria):
            project_id = str(project.get("project_id") or "")
            if not project_id or project_id in matched_projects:
                continue
            location, location_reason = _location_fit(
                criteria,
                str(project.get("area_name") or ""),
                str(project.get("project_name") or ""),
            )
            price = _amount(project.get("unit_price_from")) or _amount(project.get("min_price_aed"))
            budget, budget_reason = _budget_fit(criteria, price)
            bedroom, bedroom_reason = _bedroom_fit(
                criteria, str(project.get("unit_bedrooms") or "")
            )
            property_points = _property_fit(criteria, str(project.get("unit_type") or ""))
            if criteria.get("bedrooms_min") is not None and bedroom == 0:
                continue
            if criteria.get("property_type") and property_points == 0:
                continue
            if _violates_strict_fields(
                enquiry.strict_fields,
                location_points=location,
                budget_points=budget,
                bedroom_points=bedroom,
                property_points=property_points,
            ):
                continue
            score = min(100, location + budget + bedroom + property_points + 20 + 10)
            item = await _upsert_match(
                db,
                enquiry=enquiry,
                target_type="project",
                target_key=(
                    f"{project.get('project_id')}:{project.get('unit_type_key') or 'project'}"
                ),
                score=score,
                title=str(project.get("project_name") or "Off-plan project"),
                subtitle=(
                    f"{project.get('developer_name') or 'Developer pending'} · from AED {price:,}"
                    if price
                    else f"{project.get('developer_name') or 'Developer pending'} · price pending"
                ),
                reasons=[
                    location_reason,
                    budget_reason,
                    bedroom_reason,
                    "Developer inventory catalog; availability requires confirmation",
                ],
                breakdown={
                    "requirements": location + budget + bedroom + property_points,
                    "actionability": 20,
                    "timing": 10,
                },
                snapshot={**_json_snapshot(project), "source": "developer_supply_catalog"},
            )
            if item:
                generated.append(item)
                matched_projects.add(project_id)
                if len(matched_projects) >= 20:
                    break

    await db.commit()
    stored = await db.exec(
        select(CrmInboundMatch)
        .where(CrmInboundMatch.enquiry_id == enquiry_id)
        .order_by(CrmInboundMatch.score.desc())
    )
    lanes: dict[str, list[InboundMatchResponse]] = {
        "owners": [],
        "units": [],
        "listings": [],
        "offplan": [],
        "demand": [],
    }
    lane_names = {
        "owner": "owners",
        "unit": "units",
        "listing": "listings",
        "project": "offplan",
        "demand": "demand",
    }
    for item in stored.all():
        if item.state not in {"dismissed", "stale"}:
            lanes[lane_names[item.target_type]].append(_match_response(item))
    return InboundMatchesResponse(
        enquiry_id=enquiry_id,
        listing_fresh=listing_fresh,
        listing_last_refresh=listing_last_refresh,
        offplan_catalog_available=bool(offplan_last_refresh),
        offplan_last_refresh=offplan_last_refresh,
        lanes=lanes,
    )


async def get_inbound_matches(
    db: AsyncSession, enquiry_id: int, organization_id: str
) -> InboundMatchesResponse:
    enquiry = await db.get(CrmInboundEnquiry, enquiry_id)
    if not enquiry or enquiry.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Inbound enquiry not found")
    if not _qualification_complete(enquiry):
        return InboundMatchesResponse(
            enquiry_id=enquiry_id,
            listing_fresh=False,
            listing_last_refresh=None,
            offplan_catalog_available=False,
            offplan_last_refresh=None,
            lanes={"owners": [], "units": [], "listings": [], "offplan": [], "demand": []},
        )
    result = await db.exec(
        select(CrmInboundMatch)
        .where(CrmInboundMatch.enquiry_id == enquiry_id)
        .order_by(CrmInboundMatch.score.desc())
    )
    items = result.all()
    if not any(item.state != "stale" for item in items):
        return await refresh_inbound_matches(
            db, enquiry_id=enquiry_id, organization_id=organization_id
        )
    listing_last_refresh, listing_fresh = await _listing_freshness()
    offplan_last_refresh = await _offplan_catalog_freshness()
    lanes: dict[str, list[InboundMatchResponse]] = {
        "owners": [],
        "units": [],
        "listings": [],
        "offplan": [],
        "demand": [],
    }
    lane_names = {
        "owner": "owners",
        "unit": "units",
        "listing": "listings",
        "project": "offplan",
        "demand": "demand",
    }
    for item in items:
        if item.state not in {"dismissed", "stale"}:
            lanes[lane_names[item.target_type]].append(_match_response(item))
    return InboundMatchesResponse(
        enquiry_id=enquiry_id,
        listing_fresh=listing_fresh,
        listing_last_refresh=listing_last_refresh,
        offplan_catalog_available=bool(offplan_last_refresh),
        offplan_last_refresh=offplan_last_refresh,
        lanes=lanes,
    )


async def update_inbound_match_state(
    db: AsyncSession, *, match_id: int, organization_id: str, state: str
) -> InboundMatchResponse:
    item = await db.get(CrmInboundMatch, match_id)
    if not item or item.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Inbound match not found")
    item.state = state
    item.updated_at = _utcnow()
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _match_response(item)
