import json

import pytest

from holocron.assets.geography import _crosswalk_build_id, _transaction_consensus_aliases
from holocron.domain.geography import (
    GeographyResolver,
    LinkOverride,
    LocationNode,
    SourceSignature,
    decision_from_override,
    is_generic_leaf_name,
    landed_match_tokens,
    normalize_location_name,
    structural_tower_key,
    tower_identity_tokens,
    tower_match_tokens,
    tower_name_variants,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("JLT", "jumeirahlaketowers"),
        ("Jumeirah Lakes Towers", "jumeirahlaketowers"),
        ("Jumeriah Lake Towers", "jumeirahlaketowers"),
        ("Dubai International Financial Centre", "difc"),
        ("Tamani Arts Offices", "tamaniartsoffice"),
        ("The Address - Tower 1", "theaddresstower1"),
        ("Al Barshaa South Fourth", "albarshasouth4"),
        ("Jabal Ali First", "jebelali1"),
        ("Al Thanayah Fifth", "althanyah5"),
        ("Al Murqabat", "almuraqqabat"),
        ("Al Suq Al Kabeer", "alsoukalkabeer"),
        ("Muhaisanah Fourth", "almuhaisnah4"),
        ("Al Warqa First", "alwarqaa1"),
        ("Al Goze Industrial Second", "alquozindustrial2"),
        ("Al Qusais Industrial Area 5", "alqusaisindustrial5"),
        ("Dubai Investment Park 1 (DIP 1)", "dubaiinvestmentpark1"),
        ("Nad Al Hamar", "naddalhammar"),
        ("Al Rega", "alrigga"),
        ("Warsan Fourth", "alwarsan4"),
        ("Al Warqa'a 1", "alwarqaa1"),
        ("Trade Center Second", "tradecentre2"),
        ("Um Hurair Second", "ummhurair2"),
        ("Al Khabeesi", "alkhabaisi"),
        ("Rega Al Buteen", "riggatalbuteen"),
        ("Madinat Dubai Almelaheyah", "maritimecity"),
        ("Tecom Site C (Barsha Heights)", "barshaheights"),
        ("Za'Abeel 1", "zabeel1"),
        ("Dubai Maritime City", "maritimecity"),
        ("Festival City", "dubaifestivalcity"),
        ("Bluewaters Buildings 1", "bluewatersbuilding1"),
        ("Lakeside Towers A", "lakesidetowera"),
        ("Address Marina", "dubaimarinamallhotel"),
        ("Al Dhafrah 3", "aldhafra3"),
        ("Regina", "reginatower"),
    ],
)
def test_normalization_preserves_identity_while_folding_known_cosmetic_variants(
    raw: str, expected: str
) -> None:
    assert normalize_location_name(raw) == expected
    assert normalize_location_name(normalize_location_name(raw)) == expected


def test_normalization_does_not_merge_numbered_buildings() -> None:
    assert normalize_location_name("Building 1") != normalize_location_name("Building 2")
    assert normalize_location_name("Tower A") != normalize_location_name("Tower B")


def test_structural_tower_key_keeps_brand_and_number_identity() -> None:
    assert structural_tower_key("Lakeside Tower C") == structural_tower_key("Lakeside C")
    assert structural_tower_key("Building 1") != structural_tower_key("Building 2")


def test_ranked_name_helpers_preserve_identity_and_parenthetical_aliases() -> None:
    assert tower_name_variants("Prive (A)") == ("Prive (A)", "Prive", "A")
    assert tower_match_tokens("SLS Dubai Hotel & Residences") == ("sls", "dubai")
    assert tower_identity_tokens("Elite Sports Residence 10 - Block A") == {"10", "a"}
    assert landed_match_tokens("Reem - Mira Community Phase 4") == (
        "reem",
        "mira",
        "4",
    )


def test_tower_notation_and_known_source_spelling_variants_normalize_safely() -> None:
    assert normalize_location_name("Downtown Views II Tower 1") == normalize_location_name(
        "Downtown Views 2 Tower1"
    )
    assert normalize_location_name("Address Opera T2") == normalize_location_name(
        "Address Opera Tower 2"
    )
    assert normalize_location_name("Marina Quays West") == normalize_location_name(
        "Marina Quay West"
    )
    assert normalize_location_name("Fawad Azizi Residence") == normalize_location_name(
        "Farhad Azizi Residence"
    )


@pytest.mark.parametrize("name", ["Tower A", "Building 12", "Block 3", "Phase 2"])
def test_generic_leaf_names_require_parent_context(name: str) -> None:
    assert is_generic_leaf_name(name)


def test_exact_tower_with_matching_parent_is_auto_approved() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(building="Tower A", project="Alpha Project", area="Business Bay")
    )

    assert decision.status == "auto_approved"
    assert decision.canonical_location_id == "pf:tower-a-alpha"
    assert decision.match_method == "exact_name_parent_context"
    assert decision.evidence["generic_leaf"] is True


def test_duplicate_tower_without_parent_context_remains_ambiguous() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(_signature(building="Tower A"))

    assert decision.status == "ambiguous"
    assert decision.canonical_location_id is None
    assert decision.candidate_count == 2


def test_unique_specific_tower_without_parent_context_is_auto_approved() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(_signature(building="Unique Tower"))

    assert decision.status == "auto_approved"
    assert decision.canonical_location_id == "pf:unique-tower"
    assert decision.match_method == "exact_unique_tower"


def test_unique_tower_with_optional_structural_word_is_auto_approved() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(_signature(building="Unique"))

    assert decision.status == "auto_approved"
    assert decision.canonical_location_id == "pf:unique-tower"
    assert decision.match_method == "structural_unique_tower"


def test_ready_apartment_ranked_tower_match_precedes_community_fallback() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="SLS Dubai",
            area="Business Bay",
            property_type="Apartment",
            market_status="Ready",
            source_entity_class="physical_tower",
        )
    )

    assert decision.status == "auto_approved"
    assert decision.canonical_location_id == "pf:sls-dubai"
    assert decision.target_grain == "tower"
    assert decision.match_method == "ranked_token_equivalent"


def test_project_name_disambiguates_a_generic_numbered_building() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Building 6",
            project="Alpha Project",
            area="Business Bay",
            property_type="Apartment",
            market_status="Ready",
            source_entity_class="physical_tower",
        )
    )

    assert decision.canonical_location_id == "pf:alpha-project-6"
    assert decision.target_grain == "tower"
    assert decision.match_method == "ranked_token_equivalent"


def test_marketed_area_context_resolves_a_cadastral_area_name() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="D1",
            area="Al Jaddaf",
            property_type="Apartment",
            market_status="Ready",
            source_entity_class="physical_tower",
        )
    )

    assert decision.canonical_location_id == "pf:d1-tower"
    assert decision.match_method == "structural_name_parent_context"


def test_cadastral_area_and_complete_brand_name_resolve_a_market_tower() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Genesis",
            area="Al Barsha South 3",
            property_type="Apartment",
            market_status="Ready",
            source_entity_class="physical_tower",
        )
    )

    assert decision.canonical_location_id == "pf:genesis-by-meraki"
    assert decision.match_method == "ranked_token_containment"


def test_primary_name_wins_when_parenthetical_alias_points_at_a_duplicate_node() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Executive Towers M (West Heights 1)",
            area="Business Bay",
            property_type="Apartment",
            market_status="Ready",
            source_entity_class="physical_tower",
        )
    )

    assert decision.canonical_location_id == "pf:executive-tower-m", json.dumps(
        decision.evidence, indent=2
    )
    assert decision.match_method == "ranked_token_equivalent"


def test_offplan_apartment_is_not_attributed_to_a_physical_tower() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="SLS Dubai",
            area="Business Bay",
            property_type="Apartment",
            market_status="Offplan",
            source_entity_class="offplan_project",
            source_grain="project",
        )
    )

    assert decision.canonical_location_id == "pf:business-bay"
    assert decision.target_grain == "community"


def test_authoritative_transaction_alias_beats_a_conflicting_name_candidate() -> None:
    resolver = GeographyResolver(
        _nodes(),
        authoritative_tower_aliases={
            ("test", normalize_location_name("Registry Address")): ("pf:unique-tower",)
        },
    )

    decision = resolver.resolve(
        _signature(
            building="Registry Address",
            area="Business Bay",
            property_type="Apartment",
            market_status="Ready",
            source_entity_class="physical_tower",
        )
    )

    assert decision.canonical_location_id == "pf:unique-tower"
    assert decision.match_method == "authoritative_tower_alias"


def test_unique_landed_subcommunity_is_safe_without_cadastral_parent_context() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Alpha Project",
            source_grain="landed_phase",
            property_type="Villa",
            market_status="Ready",
            source_entity_class="landed_phase",
        )
    )

    assert decision.canonical_location_id == "pf:alpha-project"
    assert decision.target_grain == "subcommunity"
    assert decision.match_method == "ranked_landed_token_equivalent"


def test_landed_phase_can_use_a_pf_tower_typed_pin_without_tower_semantics() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="The Springs 2",
            area="Al Thanyah 4",
            source_grain="landed_phase",
            property_type="Villa",
            market_status="Ready",
            source_entity_class="landed_phase",
        )
    )

    assert decision.canonical_location_id == "pf:springs-2"
    assert decision.target_grain == "landed_phase"
    assert decision.match_method == "ranked_landed_token_equivalent"


def test_landed_phase_does_not_use_a_pf_tower_typed_pin_without_context() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="The Springs 2",
            source_grain="landed_phase",
            property_type="Villa",
            market_status="Ready",
            source_entity_class="landed_phase",
        )
    )

    assert decision.canonical_location_id is None
    assert decision.status == "suggested"


def test_landed_phase_uses_project_as_context_without_polluting_name_lookup() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Al Reem 1",
            project="Arabian Ranches 1",
            area="Wadi Al Safa 6",
            source_grain="landed_phase",
            property_type="Villa",
            market_status="Ready",
            source_entity_class="landed_phase",
        )
    )

    assert decision.canonical_location_id == "pf:al-reem-1"
    assert decision.target_grain == "landed_phase"


def test_landed_phase_prefers_the_more_specific_mira_oasis_phase() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Reem - Mira Oasis Community Phase 1",
            area="Al Yelayiss 1",
            source_grain="landed_phase",
            property_type="Villa",
            market_status="Ready",
            source_entity_class="landed_phase",
        )
    )

    assert decision.canonical_location_id == "pf:mira-oasis-1"
    assert decision.target_grain == "subcommunity"


def test_ranked_tower_match_rejects_conflicting_block_identity() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Elite Sports Residence 10 - Block A",
            area="Business Bay",
            property_type="Apartment",
            market_status="Ready",
            source_entity_class="physical_tower",
        )
    )

    assert decision.canonical_location_id == "pf:business-bay"
    assert decision.target_grain == "community"


def test_unique_community_can_be_used_as_an_ancestor_only_fallback() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(_signature(building="Business Bay", source_grain="building"))

    assert decision.status == "auto_approved"
    assert decision.canonical_location_id == "pf:business-bay"
    assert decision.target_grain == "community"
    assert decision.relation == "ancestor_only"


def test_landed_phase_is_never_auto_linked_to_a_tower() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(
        _signature(
            building="Unique Tower",
            area="Business Bay",
            source_grain="landed_phase",
        )
    )

    assert decision.canonical_location_id == "pf:business-bay"
    assert decision.target_grain == "community"


def test_unique_cadastral_area_can_map_to_a_pf_subcommunity() -> None:
    resolver = GeographyResolver(_nodes())

    decision = resolver.resolve(_signature(area="Al Nahda Second", source_grain="area"))

    assert decision.status == "auto_approved"
    assert decision.canonical_location_id == "pf:al-nahda-2"
    assert decision.match_method == "exact_unique_area"
    assert decision.relation == "marketed_as"


def test_reviewed_override_can_approve_an_otherwise_ambiguous_target() -> None:
    nodes = _nodes()

    decision = decision_from_override(
        LinkOverride(
            canonical_location_id="pf:tower-a-alpha",
            decision="approve",
            relation="equivalent",
            review_note="Title and parent path verified",
            reviewed_by="reviewer@example.com",
        ),
        {node.canonical_location_id: node for node in nodes},
    )

    assert decision.status == "manual_approved"
    assert decision.canonical_location_id == "pf:tower-a-alpha"
    assert decision.confidence == "reviewed"


def test_reviewed_rejection_preserves_an_unmapped_signature() -> None:
    decision = decision_from_override(
        LinkOverride(
            canonical_location_id=None,
            decision="reject",
            relation="",
            review_note="No equivalent node in the current snapshot",
            reviewed_by="reviewer@example.com",
        ),
        {},
    )

    assert decision.status == "manual_rejected"
    assert decision.canonical_location_id is None


def test_reviewed_override_fails_loudly_when_target_is_stale() -> None:
    with pytest.raises(ValueError, match="target does not exist"):
        decision_from_override(
            LinkOverride(
                canonical_location_id="pf:removed",
                decision="approve",
                relation="equivalent",
                review_note="Old decision",
                reviewed_by="reviewer@example.com",
            ),
            {},
        )


def test_crosswalk_build_id_is_stable_but_changes_with_source_evidence() -> None:
    rows = {
        "source_b": [("two", 2)],
        "source_a": [("one", 1)],
    }

    first = _crosswalk_build_id(snapshot_id="snapshot-1", aggregated_rows=rows)
    reordered = _crosswalk_build_id(
        snapshot_id="snapshot-1",
        aggregated_rows={"source_a": [("one", 1)], "source_b": [("two", 2)]},
    )
    changed = _crosswalk_build_id(
        snapshot_id="snapshot-1",
        aggregated_rows={"source_a": [("one", 9)], "source_b": [("two", 2)]},
    )

    assert first == reordered
    assert first != changed


def test_transaction_consensus_alias_requires_dominance_coverage_and_one_context() -> None:
    class Result:
        def __init__(self, rows):
            self.result_rows = rows

    class ClickHouse:
        def query(self, sql: str):
            if "uniqExact(e.sale_key)" in sql:
                return Result(
                    [
                        ("Verified Alias", "pf:tower-a-alpha", "Tower A", 99),
                        ("Verified Alias", "pf:tower-a-beta", "Tower A", 1),
                        ("Ambiguous Alias", "pf:tower-a-alpha", "Tower A", 30),
                        ("Ambiguous Alias", "pf:tower-a-beta", "Tower A", 20),
                        ("Multi Context", "pf:tower-a-alpha", "Tower A", 50),
                    ]
                )
            return Result(
                [
                    ("Verified Alias", 100, 1),
                    ("Ambiguous Alias", 60, 1),
                    ("Multi Context", 60, 2),
                ]
            )

    assert _transaction_consensus_aliases(ClickHouse()) == [
        ("pf:tower-a-alpha", "Verified Alias", "Tower A", 99, 100, 100)
    ]


def _signature(
    *,
    building: str = "",
    project: str = "",
    area: str = "",
    source_grain: str = "building",
    property_type: str = "",
    market_status: str = "",
    source_entity_class: str = "",
) -> SourceSignature:
    return SourceSignature(
        source_system="test",
        source_key="test-key",
        source_grain=source_grain,
        area_name=area,
        master_project_name="",
        project_name=project,
        building_name=building,
        property_type=property_type,
        market_status=market_status,
        source_entity_class=source_entity_class,
    )


def _nodes() -> list[LocationNode]:
    return [
        _node("dubai", "CITY", "Dubai", ("dubai",)),
        _node(
            "business-bay",
            "COMMUNITY",
            "Business Bay",
            ("dubai", "business-bay"),
            parent="dubai",
        ),
        _node(
            "dubai-marina",
            "COMMUNITY",
            "Dubai Marina",
            ("dubai", "dubai-marina"),
            parent="dubai",
        ),
        _node(
            "culture-village",
            "COMMUNITY",
            "Culture Village",
            ("dubai", "culture-village"),
            parent="dubai",
        ),
        _node(
            "arjan",
            "COMMUNITY",
            "Arjan",
            ("dubai", "arjan"),
            parent="dubai",
        ),
        _node(
            "the-springs",
            "COMMUNITY",
            "The Springs",
            ("dubai", "the-springs"),
            parent="dubai",
        ),
        _node(
            "springs-2",
            "TOWER",
            "The Springs 2",
            ("dubai", "the-springs", "springs-2"),
            parent="the-springs",
        ),
        _node(
            "arabian-ranches",
            "COMMUNITY",
            "Arabian Ranches",
            ("dubai", "arabian-ranches"),
            parent="dubai",
        ),
        _node(
            "al-reem",
            "SUBCOMMUNITY",
            "Al Reem",
            ("dubai", "arabian-ranches", "al-reem"),
            parent="arabian-ranches",
        ),
        _node(
            "al-reem-1",
            "TOWER",
            "Al Reem 1",
            ("dubai", "arabian-ranches", "al-reem", "al-reem-1"),
            parent="al-reem",
        ),
        _node(
            "reem",
            "COMMUNITY",
            "Reem",
            ("dubai", "reem"),
            parent="dubai",
        ),
        _node(
            "mira",
            "SUBCOMMUNITY",
            "Mira",
            ("dubai", "reem", "mira"),
            parent="reem",
        ),
        _node(
            "mira-1",
            "SUBCOMMUNITY",
            "Mira 1",
            ("dubai", "reem", "mira", "mira-1"),
            parent="mira",
        ),
        _node(
            "mira-oasis",
            "SUBCOMMUNITY",
            "Mira Oasis",
            ("dubai", "reem", "mira-oasis"),
            parent="reem",
        ),
        _node(
            "mira-oasis-1",
            "SUBCOMMUNITY",
            "Mira Oasis 1",
            ("dubai", "reem", "mira-oasis", "mira-oasis-1"),
            parent="mira-oasis",
        ),
        _node(
            "al-nahda",
            "COMMUNITY",
            "Al Nahda",
            ("dubai", "al-nahda"),
            parent="dubai",
        ),
        _node(
            "al-nahda-2",
            "SUBCOMMUNITY",
            "Al Nahda 2",
            ("dubai", "al-nahda", "al-nahda-2"),
            parent="al-nahda",
        ),
        _node(
            "alpha-project",
            "SUBCOMMUNITY",
            "Alpha Project",
            ("dubai", "business-bay", "alpha-project"),
            parent="business-bay",
        ),
        _node(
            "beta-project",
            "SUBCOMMUNITY",
            "Beta Project",
            ("dubai", "dubai-marina", "beta-project"),
            parent="dubai-marina",
        ),
        _node(
            "tower-a-alpha",
            "TOWER",
            "Tower A",
            ("dubai", "business-bay", "alpha-project", "tower-a-alpha"),
            parent="alpha-project",
        ),
        _node(
            "tower-a-beta",
            "TOWER",
            "Tower A",
            ("dubai", "dubai-marina", "beta-project", "tower-a-beta"),
            parent="beta-project",
        ),
        _node(
            "unique-tower",
            "TOWER",
            "Unique Tower",
            ("dubai", "business-bay", "alpha-project", "unique-tower"),
            parent="alpha-project",
        ),
        _node(
            "sls-dubai",
            "TOWER",
            "SLS Dubai Hotel & Residences",
            ("dubai", "business-bay", "sls-dubai"),
            parent="business-bay",
        ),
        _node(
            "sls-dubai-east",
            "TOWER",
            "SLS Dubai East Tower",
            ("dubai", "business-bay", "sls-dubai-east"),
            parent="business-bay",
        ),
        _node(
            "alpha-project-6",
            "TOWER",
            "Alpha Project 6",
            ("dubai", "business-bay", "alpha-project", "alpha-project-6"),
            parent="alpha-project",
        ),
        _node(
            "elite-sports-10-tower-1",
            "TOWER",
            "Elite Sports Residence 10 Tower 1",
            ("dubai", "business-bay", "elite-sports-10-tower-1"),
            parent="business-bay",
        ),
        _node(
            "d1-tower",
            "TOWER",
            "D1 Tower",
            ("dubai", "culture-village", "d1-tower"),
            parent="culture-village",
        ),
        _node(
            "building-d1",
            "TOWER",
            "Building D1",
            ("dubai", "dubai-marina", "building-d1"),
            parent="dubai-marina",
        ),
        _node(
            "executive-tower-m",
            "TOWER",
            "Executive Tower M",
            ("dubai", "business-bay", "executive-tower-m"),
            parent="business-bay",
        ),
        _node(
            "west-heights-1",
            "TOWER",
            "West Heights 1",
            ("dubai", "business-bay", "west-heights-1"),
            parent="business-bay",
        ),
        _node(
            "genesis-by-meraki",
            "TOWER",
            "Genesis by Meraki",
            ("dubai", "arjan", "genesis-by-meraki"),
            parent="arjan",
        ),
    ]


def _node(
    location_id: str,
    location_type: str,
    name: str,
    path_ids: tuple[str, ...],
    *,
    parent: str | None = None,
) -> LocationNode:
    return LocationNode(
        canonical_location_id=f"pf:{location_id}",
        source_location_id=location_id,
        parent_canonical_location_id=f"pf:{parent}" if parent else None,
        location_type=location_type,
        name=name,
        normalized_name=normalize_location_name(name),
        path_ids=path_ids,
    )
