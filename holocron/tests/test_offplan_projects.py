from __future__ import annotations

import pytest

from holocron.domain.offplan_projects import (
    OffplanProjectOverride,
    OffplanProjectResolver,
    OffplanSignature,
    ReellyProject,
    decision_from_offplan_override,
    transaction_consensus_decision,
    transaction_name_compatible,
)


def _project(
    project_id: str,
    name: str,
    area: str = "Business Bay",
) -> ReellyProject:
    return ReellyProject(
        project_id=project_id,
        project_key=f"reelly:{project_id}",
        project_name=name,
        area_name=area,
    )


def _signature(
    *,
    building: str,
    project: str = "",
    area: str = "Business Bay",
    rows: int = 10,
) -> OffplanSignature:
    return OffplanSignature(
        source_system="dxbi_sales",
        source_key="source-key",
        area_name=area,
        master_project_name="",
        project_name=project,
        building_name=building,
        property_type="Apartment",
        row_count=rows,
        source_build_id="source-build",
    )


def test_exact_offplan_name_is_approved_without_area_dependency() -> None:
    resolver = OffplanProjectResolver([_project("1", "Binghatti Hillviews", "Dubai Science Park")])

    decision = resolver.resolve(
        _signature(building="Binghatti Hillviews", area="Al Barsha South 2")
    )

    assert decision.reelly_project_id == "1"
    assert decision.status == "auto_approved"
    assert decision.match_method == "exact_name"


def test_numbered_project_identity_conflict_is_not_synthetically_matched() -> None:
    resolver = OffplanProjectResolver([_project("2", "District One Phase 2")])

    decision = resolver.resolve(_signature(building="District One Phase 3"))

    assert decision.reelly_project_id is None
    assert decision.status in {"suggested", "unmapped"}


def test_component_tower_can_link_to_context_supported_parent_project() -> None:
    resolver = OffplanProjectResolver([_project("3", "Sobha One", "Sobha Hartland")])

    decision = resolver.resolve(_signature(building="Sobha One Tower B", area="Sobha Hartland"))

    assert decision.reelly_project_id == "3"
    assert decision.relation == "component_of"
    assert decision.status == "auto_approved"
    assert decision.match_method == "component_name"


def test_duplicate_catalogue_name_is_retained_as_ambiguous() -> None:
    resolver = OffplanProjectResolver(
        [_project("4", "The Community"), _project("5", "The Community")]
    )

    decision = resolver.resolve(_signature(building="The Community"))

    assert decision.reelly_project_id is None
    assert decision.status == "ambiguous"
    assert decision.candidate_count == 2


def test_context_supported_catalogue_subtitle_is_approved() -> None:
    resolver = OffplanProjectResolver(
        [_project("7", "Golf Views Seven City", "Jumeirah Lake Towers (JLT)")]
    )

    decision = resolver.resolve(_signature(building="Seven City", area="Jumeirah Lake Towers"))

    assert decision.reelly_project_id == "7"
    assert decision.match_method == "catalogue_name_expansion"


def test_context_and_developer_support_single_word_project_alias() -> None:
    project = ReellyProject(
        project_id="10",
        project_key="reelly:10",
        project_name="Breez",
        area_name="Dubai Maritime City",
        developer_name="Danube",
    )

    decision = OffplanProjectResolver([project]).resolve(
        _signature(building="Breez By Danube", area="Dubai Maritime City")
    )

    assert decision.reelly_project_id == "10"
    assert decision.match_method == "component_name"


def test_area_context_disambiguates_single_word_phase_from_wrong_brand() -> None:
    resolver = OffplanProjectResolver(
        [
            _project("11", "Damac Lagoons Marbella", "Damac Lagoons"),
            _project("12", "Samana Marbella", "Dubai Studio City"),
        ]
    )

    decision = resolver.resolve(_signature(building="Marbella (All Phases)", area="Damac Lagoons"))

    assert decision.reelly_project_id == "11"
    assert decision.match_method == "catalogue_name_expansion"


def test_unique_catalogue_area_umbrella_captures_absent_phase() -> None:
    resolver = OffplanProjectResolver(
        [
            _project("13", "Damac Lagoons", "Damac Lagoons"),
            _project("14", "Samana Portofino", "Dubai Production City"),
        ]
    )

    decision = resolver.resolve(_signature(building="Portofino (All Phases)", area="Damac Lagoons"))

    assert decision.reelly_project_id == "13"
    assert decision.relation == "component_of"
    assert decision.match_method == "catalogue_area_umbrella"


def test_registry_project_context_links_named_component_to_catalogue_phase() -> None:
    resolver = OffplanProjectResolver([_project("15", "Damac Islands Phase 1 And 2", "Dubailand")])

    decision = resolver.resolve(
        _signature(
            building="Bora Bora (All Phases)",
            project="Damac Islands",
            area="Al Yelayiss 1",
        )
    )

    assert decision.reelly_project_id == "15"
    assert decision.relation == "component_of"
    assert decision.match_method == "catalogue_name_expansion"


def test_transaction_consensus_promotes_only_sufficiently_covered_source() -> None:
    project = _project("6", "Catalogued Project")
    current = OffplanProjectResolver([project]).resolve(_signature(building="Registry Alias"))

    approved = transaction_consensus_decision(
        current=current,
        project=project,
        matched_sales=3,
        all_matched_sales=3,
        total_source_events=10,
    )
    rejected = transaction_consensus_decision(
        current=current,
        project=project,
        matched_sales=1,
        all_matched_sales=1,
        total_source_events=10,
    )

    assert approved.reelly_project_id == "6"
    assert approved.match_method == "dld_transaction_consensus"
    assert rejected == current


def test_transaction_consensus_requires_name_compatibility() -> None:
    signature = _signature(building="Dubai World Central")

    assert not transaction_name_compatible(signature, _project("8", "Greenspoint"))
    assert transaction_name_compatible(signature, _project("9", "Dubai World Residences"))


def test_manual_override_rejects_stale_catalogue_target() -> None:
    override = OffplanProjectOverride(
        reelly_project_id="missing",
        decision="approve",
        relation="equivalent",
        review_note="reviewed",
        reviewed_by="tester",
    )

    with pytest.raises(ValueError, match="does not exist"):
        decision_from_offplan_override(override, {})
