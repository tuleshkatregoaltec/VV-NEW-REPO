from datetime import date, datetime, timedelta, timezone

from app.crm.import_models import CrmPropertyContactClaim
from app.crm.inbound_models import CrmInboundEnquiry
from app.crm.inbound_service import (
    _bedroom_fit,
    _belongs_in_inbox,
    _best_header,
    _budget_fit,
    _deterministic_criteria,
    _file_rows,
    _lead_priority,
    _location_fit,
    _normalize_intent,
    _ownership_enrichment,
    _preview_file,
    _property_fit,
    _qualification_complete,
    _redact,
    _violates_strict_fields,
)


def _owner_claim(
    *,
    property_key: str,
    status: str,
    phone: str | None = None,
    lease_end: date | None = None,
) -> CrmPropertyContactClaim:
    now = datetime.now(timezone.utc)
    return CrmPropertyContactClaim(
        organization_id="org",
        import_id=1,
        list_id=1,
        source_sheet="Owners",
        source_row_number=1,
        row_fingerprint=f"row-{property_key}",
        owner_key="owner-1",
        property_key=property_key,
        contact_name="Maya Example",
        phone_primary=phone,
        ownership_status=status,
        confidence_score=98,
        match_reason="Registry evidence",
        lease_end=lease_end,
        created_at=now,
        updated_at=now,
    )


def _inbound_enquiry(intent: str) -> CrmInboundEnquiry:
    now = datetime.now(timezone.utc)
    return CrmInboundEnquiry(
        organization_id="org",
        contact_id=1,
        created_by_user_id="user",
        record_kind="opportunity" if intent != "unknown" else "unqualified_contact",
        intent=intent,
        status="new",
        source="Campaign",
        enquiry_date=now,
        created_at=now,
        updated_at=now,
    )


def test_deterministic_extraction_understands_common_campaign_message():
    criteria = _deterministic_criteria(
        {},
        "Looking to buy a 2 bedroom apartment in JBR with a budget up to 3m",
    )

    assert criteria["locations"] == ["JBR"]
    assert criteria["bedrooms_min"] == 2
    assert criteria["bedrooms_max"] == 2
    assert criteria["budget_max_aed"] == 3_000_000
    assert _normalize_intent("", "Looking to buy a 2 bedroom in JBR") == "buy"


def test_ambiguous_message_does_not_force_intent():
    assert (
        _normalize_intent(
            "",
            "The form did not ask whether the person wants to buy, sell, rent, or let",
        )
        is None
    )


def test_redaction_removes_contact_identity_before_ai_extraction():
    redacted = _redact(
        "Call Jane Example on +971 50 123 4567 or jane@example.com, Emirates ID 784123456789012",
        ["Jane Example"],
    )

    assert "Jane Example" not in redacted
    assert "jane@example.com" not in redacted
    assert "501234567" not in redacted.replace(" ", "")
    assert "784123456789012" not in redacted
    assert "[REDACTED]" in redacted
    assert "[EMAIL]" in redacted
    assert "[PHONE]" in redacted
    assert "[ID]" in redacted


def test_header_detection_skips_export_title_and_blank_preamble():
    rows = [
        ("Meta campaign export", None, None),
        (None, None, None),
        ("Lead Name", "Mobile Number", "Requirements"),
        ("Maya", "+971501234567", "2 bed JBR"),
    ]

    index, _, mapping = _best_header(rows)

    assert index == 2
    assert mapping == {"full_name": 0, "phone": 1, "notes": 2}


def test_csv_mapping_preserves_source_row_and_header_audit():
    rows, audit = _file_rows(
        b"Campaign leads,,\n\nLead Name,Mobile,Looking For,Requirements\nMaya,0501234567,Buyer,2 bed JBR\n",
        "summer-campaign.csv",
    )

    assert len(rows) == 1
    assert rows[0][1] == 4
    assert rows[0][2]["full_name"] == "Maya"
    assert rows[0][2]["intent"] == "Buyer"
    assert audit["sheets"][0]["header_row"] == 3


def test_match_scoring_distinguishes_exact_flexible_and_outside():
    criteria = {
        "locations": ["JBR"],
        "bedrooms_min": 2,
        "budget_min_aed": 2_500_000,
        "budget_max_aed": 3_000_000,
    }

    assert _location_fit(criteria, "Jumeirah Beach Residence (JBR)")[0] == 20
    assert _bedroom_fit(criteria, "2 Bed")[0] == 10
    assert _budget_fit(criteria, 2_900_000)[0] == 15
    assert _budget_fit(criteria, 3_150_000)[0] == 9
    assert _budget_fit(criteria, 4_000_000)[0] == 0


def test_generic_residential_owner_types_do_not_block_apartment_inventory():
    for imported_type in ("Unit", "Residential", "Residential Flats", "Flat"):
        assert _property_fit({"property_type": imported_type}, "Apartment") == 10


def test_missing_requirements_never_award_match_points():
    assert _location_fit({}, "JBR")[0] == 0
    assert _budget_fit({}, 3_000_000)[0] == 0
    assert _bedroom_fit({}, "2 Bed")[0] == 0


def test_matching_requires_agent_qualified_minimum_brief():
    now = datetime.now(timezone.utc)
    enquiry = CrmInboundEnquiry(
        organization_id="org",
        contact_id=1,
        created_by_user_id="user",
        record_kind="opportunity",
        intent="buy",
        status="qualified",
        source="Manual",
        enquiry_date=now,
        criteria={"locations": ["JBR"], "budget_max_aed": 3_000_000},
        created_at=now,
        updated_at=now,
    )

    assert _qualification_complete(enquiry)
    enquiry.status = "contacted"
    assert not _qualification_complete(enquiry)


def test_qualified_but_untouched_opportunity_remains_in_operational_inbox():
    enquiry = _inbound_enquiry("buy")
    enquiry.status = "qualified"
    enquiry.first_response_due_at = datetime.now(timezone.utc) - timedelta(hours=1)

    assert _belongs_in_inbox(enquiry)

    enquiry.first_contact_at = datetime.now(timezone.utc)
    assert not _belongs_in_inbox(enquiry)

    enquiry.next_follow_up = date.today()
    assert _belongs_in_inbox(enquiry)

    enquiry.status = "won"
    assert not _belongs_in_inbox(enquiry)
    enquiry.status = "qualified"
    enquiry.intent = "unknown"
    assert not _qualification_complete(enquiry)


def test_import_preview_masks_contacts_and_does_not_persist_anything():
    preview = _preview_file(
        b"Lead Name,Mobile,Email,Requirements\nMaya,0501234567,maya@example.com,2 bed JBR\n",
        "real-leads.csv",
    )

    assert preview.total_rows == 1
    assert preview.sheets[0].field_map["phone"] == "Mobile"
    assert preview.sheets[0].sample_rows[0]["phone"] == "Present"
    assert preview.sheets[0].sample_rows[0]["email"] == "Present"


def test_hard_criteria_exclude_matches_while_flexible_fields_only_reduce_score():
    assert _violates_strict_fields(
        ["locations"],
        location_points=0,
        budget_points=15,
        bedroom_points=10,
        property_points=10,
    )
    assert not _violates_strict_fields(
        [],
        location_points=0,
        budget_points=0,
        bedroom_points=0,
        property_points=0,
    )


def test_exact_contact_owner_match_prioritizes_buyer_and_seller_leads():
    enrichment = _ownership_enrichment(
        [
            (
                _owner_claim(
                    property_key="tower-a|101",
                    status="verified_current_owner",
                    phone="971501234567",
                ),
                "phone",
            ),
            (
                _owner_claim(
                    property_key="tower-b|202",
                    status="former_owner",
                    phone="971501234567",
                ),
                "phone",
            ),
        ]
    )

    assert enrichment.verification == "contact_exact"
    assert enrichment.current_owner
    assert enrichment.former_owner
    assert enrichment.multiple_property_owner
    assert enrichment.known_property_count == 2
    assert _lead_priority(_inbound_enquiry("buy"), enrichment).band == "high"
    assert _lead_priority(_inbound_enquiry("sell"), enrichment).band == "high"


def test_rental_owner_signal_is_reported_and_prioritized():
    enrichment = _ownership_enrichment(
        [
            (
                _owner_claim(
                    property_key="tower-a|101",
                    status="probable_current_owner",
                    phone="971501234567",
                    lease_end=date(2026, 10, 1),
                ),
                "phone",
            )
        ]
    )

    assert enrichment.rental_owner
    assert enrichment.rental_property_count == 1
    # Ownership raises the follow-up order, but an unqualified contact is not
    # labelled high priority until the person's intent is known.
    assert _lead_priority(_inbound_enquiry("unknown"), enrichment).band == "medium"


def test_name_only_owner_match_remains_verification_required():
    enrichment = _ownership_enrichment(
        [
            (
                _owner_claim(
                    property_key="tower-a|101",
                    status="former_owner",
                ),
                "name",
            )
        ]
    )

    assert enrichment.verification == "name_only"
    assert enrichment.former_owner
    assert _lead_priority(_inbound_enquiry("sell"), enrichment).band == "medium"
    assert _lead_priority(_inbound_enquiry("unknown"), enrichment).band == "medium"


def test_unmatched_contact_keeps_standard_priority():
    enrichment = _ownership_enrichment([])

    priority = _lead_priority(_inbound_enquiry("buy"), enrichment)

    assert not enrichment.matched
    assert priority.band == "standard"


def test_priority_blends_ticket_size_with_verified_ownership():
    enrichment = _ownership_enrichment(
        [
            (
                _owner_claim(
                    property_key="tower-a|101",
                    status="verified_current_owner",
                    phone="971501234567",
                ),
                "phone",
            ),
            (
                _owner_claim(
                    property_key="tower-b|202",
                    status="former_owner",
                    phone="971501234567",
                ),
                "phone",
            ),
        ]
    )
    smaller = _inbound_enquiry("buy")
    smaller.criteria = {"budget_max_aed": 2_000_000}
    larger = _inbound_enquiry("buy")
    larger.criteria = {"budget_max_aed": 12_000_000}

    smaller_priority = _lead_priority(smaller, enrichment)
    larger_priority = _lead_priority(larger, enrichment)

    assert larger_priority.score > smaller_priority.score
    assert larger_priority.opportunity_value_aed == 12_000_000
    assert larger_priority.band == "high"


def test_name_only_match_is_never_presented_as_high_priority():
    enrichment = _ownership_enrichment(
        [(_owner_claim(property_key="tower-a|101", status="verified_current_owner"), "name")]
    )
    enquiry = _inbound_enquiry("buy")
    enquiry.criteria = {"budget_max_aed": 50_000_000}

    priority = _lead_priority(enquiry, enrichment)

    assert priority.band == "medium"
    assert "verify identity" in " ".join(priority.reasons).lower()
