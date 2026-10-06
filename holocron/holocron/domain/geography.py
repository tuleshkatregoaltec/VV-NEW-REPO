from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, Mapping

NORMALIZATION_VERSION = 10

LocationType = Literal["CITY", "COMMUNITY", "SUBCOMMUNITY", "TOWER"]

_FULL_NAME_ALIASES = {
    "al quoz industrial area 1": "al quoz industrial 1",
    "al quoz industrial area 2": "al quoz industrial 2",
    "al quoz industrial area 3": "al quoz industrial 3",
    "al quoz industrial area 4": "al quoz industrial 4",
    "al qusais industrial area 1": "al qusais industrial 1",
    "al qusais industrial area 2": "al qusais industrial 2",
    "al qusais industrial area 3": "al qusais industrial 3",
    "al qusais industrial area 4": "al qusais industrial 4",
    "al qusais industrial area 5": "al qusais industrial 5",
    "barsha heights tecom": "barsha heights",
    "address marina": "dubai marina mall hotel",
    "tecom site c barsha heights": "barsha heights",
    "difc": "difc",
    "dubai international financial centre": "difc",
    "dubai international financial center": "difc",
    "dubai investment park": "dubai investment park",
    "dubai investment park 1 dip 1": "dubai investment park 1",
    "dubai investment park 2 dip 2": "dubai investment park 2",
    "dip": "dubai investment park",
    "dubai production city": "dubai production city",
    "impz": "dubai production city",
    "international media production zone": "dubai production city",
    "dubai silicon oasis": "dubai silicon oasis",
    "dso": "dubai silicon oasis",
    "jbr": "jumeirah beach residence",
    "jumeirah beach residence": "jumeirah beach residence",
    "jlt": "jumeirah lake towers",
    "jumeirah lake towers": "jumeirah lake towers",
    "jumeirah lakes towers": "jumeirah lake towers",
    "jumeirah lake tower": "jumeirah lake towers",
    "jumeirah lakes tower": "jumeirah lake towers",
    "jvc": "jumeirah village circle",
    "jumeirah village circle": "jumeirah village circle",
    "jvt": "jumeirah village triangle",
    "jumeirah village triangle": "jumeirah village triangle",
    "madinat dubai almelaheyah": "maritime city",
    "muhaisnah 1": "al muhaisnah 1",
    "muhaisnah 2": "al muhaisnah 2",
    "muhaisnah 3": "al muhaisnah 3",
    "muhaisnah 4": "al muhaisnah 4",
    "rigga al buteen": "riggat al buteen",
    "warsan 1": "al warsan 1",
    "warsan 2": "al warsan 2",
    "warsan 3": "al warsan 3",
    "warsan 4": "al warsan 4",
    "al warqaa a": "al warqaa",
    "al warqaa a 1": "al warqaa 1",
    "al warqaa a 2": "al warqaa 2",
    "al warqaa a 3": "al warqaa 3",
    "al warqaa a 4": "al warqaa 4",
    "al warqaa a 5": "al warqaa 5",
    "tecom": "barsha heights",
    "za abeel 1": "zabeel 1",
    "zaabeel 1": "zabeel 1",
    "zaabeel 2": "zabeel 2",
    "dubai creek harbour the lagoons": "dubai creek harbour",
    "dubai south dubai world central": "dubai south",
    "dubai maritime city": "maritime city",
    "festival city": "dubai festival city",
    "falcon city": "falcon city of wonders",
    "fawad azizi residence": "farhad azizi residence",
    "regina": "regina tower",
    "the greens": "greens",
}
_TOKEN_REPLACEMENTS = {
    "apartments": "apartment",
    "barshaa": "barsha",
    "blvd": "boulevard",
    "center": "centre",
    "colccion": "coleccion",
    "fifth": "5",
    "first": "1",
    "fourth": "4",
    "gates": "gate",
    "jabal": "jebel",
    "jadaf": "jaddaf",
    "khabeesi": "khabaisi",
    "jumairah": "jumeirah",
    "jumeriah": "jumeirah",
    "jbr": "jumeirah beach residence",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "goze": "quoz",
    "hamar": "hammar",
    "mamzer": "mamzar",
    "mirdiff": "mirdif",
    "muhaisanah": "muhaisnah",
    "murqabat": "muraqqabat",
    "nad": "nadd",
    "offices": "office",
    "blocks": "block",
    "buildings": "building",
    "clusters": "cluster",
    "districts": "district",
    "dhafrah": "dhafra",
    "phases": "phase",
    "quays": "quay",
    "rega": "rigga",
    "residences": "residence",
    "communities": "community",
    "second": "2",
    "shiba": "sheba",
    "sixth": "6",
    "sidr": "sidir",
    "thanayah": "thanyah",
    "third": "3",
    "towers": "tower",
    "townhouses": "townhouse",
    "suq": "souk",
    "um": "umm",
    "xi": "11",
    "xii": "12",
    "warqa": "warqaa",
    "villas": "villa",
}
_GENERIC_LEAF = re.compile(
    r"^(?:tower|building|block|phase|cluster|district)\s*[a-z0-9-]+$",
    re.IGNORECASE,
)
_STRUCTURAL_TOWER_TOKENS = frozenset({"apartment", "block", "building", "tower"})
_TOWER_MATCH_STOP_TOKENS = frozenset(
    {
        "and",
        "apartment",
        "at",
        "block",
        "building",
        "by",
        "hotel",
        "residence",
        "residency",
        "resort",
        "spa",
        "the",
        "tower",
    }
)
_LANDED_MATCH_STOP_TOKENS = _TOWER_MATCH_STOP_TOKENS | frozenset(
    {
        "community",
        "development",
        "phase",
        "townhouse",
        "villa",
    }
)
_BROAD_LOCATION_TOKENS = frozenset(
    {"dubai", "downtown", "jumeirah", "marina", "residence", "tower"}
)
_VERTICAL_ASSET_TOKENS = frozenset(
    {"apartment", "building", "hotel", "office", "residence", "tower"}
)
_CONTEXT_EQUIVALENTS = {
    "alhebiah6": frozenset({"mudon"}),
    "aljaddaf": frozenset({"culturevillage"}),
    "albarshasouth3": frozenset({"arjan"}),
    "alsafouh2": frozenset({"dubaimediacity"}),
    "althanyah4": frozenset({"meadows", "thesprings"}),
    "althanyah1": frozenset({"barshaheights"}),
    "alyelayiss1": frozenset({"reem"}),
    "alyufrah1": frozenset({"thevalley"}),
    "arabianranches1": frozenset({"arabianranches"}),
    "emiratesliving": frozenset({"meadows", "thesprings"}),
}
_PARENTHETICAL = re.compile(r"\(([^()]*)\)")


def _normalized_words(value: str) -> list[str]:
    ascii_value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(character)
    ).lower()
    ascii_value = re.sub(r"([a-z]{3,})(\d+)", r"\1 \2", ascii_value)
    words = re.findall(r"[a-z0-9]+", ascii_value)
    expanded: list[str] = []
    for word in words:
        if tower_number := re.fullmatch(r"t(\d+)", word):
            expanded.extend(("tower", tower_number.group(1)))
            continue
        expanded.extend(re.findall(r"[a-z0-9]+", _TOKEN_REPLACEMENTS.get(word, word)))
    words = expanded
    phrase = " ".join(words)
    phrase = _FULL_NAME_ALIASES.get(phrase, phrase)
    return re.findall(r"[a-z0-9]+", phrase)


def normalize_location_name(value: str) -> str:
    """Return a conservative key without erasing numbered entity identity."""
    return "".join(_normalized_words(value))


def structural_tower_key(value: str) -> str:
    """Fold optional tower/building words while retaining brand and unit identity."""
    return "".join(
        word for word in _normalized_words(value) if word not in _STRUCTURAL_TOWER_TOKENS
    )


def tower_name_variants(value: str) -> tuple[str, ...]:
    """Return full and parenthetical aliases without inventing entity identity."""
    raw = (value or "").strip()
    if not raw:
        return ()
    variants = [raw]
    outside = _PARENTHETICAL.sub(" ", raw).strip(" -")
    if outside and outside != raw:
        variants.append(outside)
    variants.extend(match.strip() for match in _PARENTHETICAL.findall(raw) if match.strip())
    return tuple(dict.fromkeys(variants))


def tower_match_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        word for word in _normalized_words(value) if word not in _TOWER_MATCH_STOP_TOKENS
    )


def landed_match_tokens(value: str) -> tuple[str, ...]:
    """Return identity-bearing tokens for a villa/townhouse community or phase."""
    return tuple(
        word for word in _normalized_words(value) if word not in _LANDED_MATCH_STOP_TOKENS
    )


def tower_identity_tokens(value: str) -> frozenset[str]:
    """Return number/block tokens whose disagreement makes a fuzzy match unsafe."""
    identity: set[str] = set()
    for word in _normalized_words(value):
        if re.fullmatch(r"(?:[a-z]+\d+[a-z]*|\d+[a-z]*|[a-z])", word):
            identity.add(word)
        elif re.fullmatch(r"(?:ii|iii|iv|vi|vii|viii|ix|xi|xii)", word):
            identity.add(word)
    return frozenset(identity)


def is_generic_leaf_name(value: str) -> bool:
    normalized_words = " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))
    return bool(_GENERIC_LEAF.fullmatch(normalized_words))


@dataclass(frozen=True)
class LocationNode:
    canonical_location_id: str
    source_location_id: str
    parent_canonical_location_id: str | None
    location_type: LocationType
    name: str
    normalized_name: str
    path_ids: tuple[str, ...]


@dataclass(frozen=True)
class SourceSignature:
    source_system: str
    source_key: str
    source_grain: str
    area_name: str
    master_project_name: str
    project_name: str
    building_name: str
    property_type: str = ""
    market_status: str = ""
    source_entity_class: str = ""

    @property
    def normalized_context(self) -> set[str]:
        context = {
            key
            for value in (self.area_name, self.master_project_name, self.project_name)
            if (key := normalize_location_name(value))
        }
        for key in tuple(context):
            context.update(_CONTEXT_EQUIVALENTS.get(key, ()))
        return context

    @property
    def is_physical_tower_candidate(self) -> bool:
        if self.source_entity_class:
            return self.source_entity_class == "physical_tower"
        return self.source_grain != "landed_phase"

    @property
    def is_landed_phase(self) -> bool:
        return self.source_entity_class == "landed_phase" or self.source_grain == "landed_phase"


@dataclass(frozen=True)
class CrosswalkDecision:
    canonical_location_id: str | None
    target_grain: str
    relation: str
    status: str
    match_method: str
    confidence: str
    candidate_count: int
    evidence: dict[str, object]

    def evidence_json(self) -> str:
        return json.dumps(self.evidence, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class LinkOverride:
    canonical_location_id: str | None
    decision: Literal["approve", "reject"]
    relation: str
    review_note: str
    reviewed_by: str


def decision_from_override(
    override: LinkOverride,
    nodes_by_id: Mapping[str, LocationNode],
) -> CrosswalkDecision:
    """Convert a reviewed override into a link decision, failing on stale targets."""
    if override.decision == "reject":
        if override.canonical_location_id is not None:
            raise ValueError("Rejected geography override cannot have a canonical target")
        return CrosswalkDecision(
            canonical_location_id=None,
            target_grain="",
            relation="",
            status="manual_rejected",
            match_method="manual_override",
            confidence="reviewed",
            candidate_count=0,
            evidence={
                "review_note": override.review_note,
                "reviewed_by": override.reviewed_by,
            },
        )

    if override.canonical_location_id is None:
        raise ValueError("Approved geography override requires a canonical target")
    target = nodes_by_id.get(override.canonical_location_id)
    if target is None:
        raise ValueError(
            f"Geography override target does not exist: {override.canonical_location_id}"
        )
    return CrosswalkDecision(
        canonical_location_id=target.canonical_location_id,
        target_grain=target.location_type.lower(),
        relation=override.relation or "equivalent",
        status="manual_approved",
        match_method="manual_override",
        confidence="reviewed",
        candidate_count=1,
        evidence={
            "review_note": override.review_note,
            "reviewed_by": override.reviewed_by,
            "target_name": target.name,
        },
    )


@dataclass(frozen=True)
class _RankedTowerMatch:
    candidate: LocationNode
    score: int
    method: str
    context_supported: bool
    source_variant: str
    target_variant: str
    source_priority: int
    identity_strength: int

    def evidence(self) -> dict[str, object]:
        return {
            "canonical_location_id": self.candidate.canonical_location_id,
            "target_name": self.candidate.name,
            "score": self.score,
            "method": self.method,
            "context_supported": self.context_supported,
            "identity_compatible": True,
            "source_variant": self.source_variant,
            "target_variant": self.target_variant,
            "source_priority": self.source_priority,
            "identity_strength": self.identity_strength,
        }


class GeographyResolver:
    """Resolve hierarchy-supported source labels to canonical PF locations."""

    def __init__(
        self,
        nodes: list[LocationNode],
        tower_aliases: Mapping[str, tuple[str, ...]] | None = None,
        authoritative_tower_aliases: Mapping[
            tuple[str, str], tuple[str, ...]
        ]
        | None = None,
    ) -> None:
        self._nodes_by_id = {node.canonical_location_id: node for node in nodes}
        self._ancestor_names_by_id = {
            node.canonical_location_id: {
                ancestor.normalized_name
                for source_id in node.path_ids
                if (
                    ancestor := self._nodes_by_id.get(
                        source_id if source_id.startswith("pf:") else f"pf:{source_id}"
                    )
                )
                is not None
                and ancestor.canonical_location_id != node.canonical_location_id
            }
            for node in nodes
        }
        self._by_type_and_name: dict[tuple[str, str], list[LocationNode]] = {}
        for node in nodes:
            self._by_type_and_name.setdefault(
                (node.location_type, node.normalized_name), []
            ).append(node)
        self._towers_by_structural_key: dict[str, list[LocationNode]] = {}
        self._tower_variants: dict[str, tuple[str, ...]] = {}
        self._tower_token_index: dict[str, set[str]] = {}
        self._rank_cache: dict[
            tuple[str, tuple[str, ...]],
            tuple[list[_RankedTowerMatch], _RankedTowerMatch | None],
        ] = {}
        self._authoritative_tower_aliases = authoritative_tower_aliases or {}
        self._landed_variants: dict[str, tuple[str, ...]] = {}
        self._landed_token_index: dict[str, set[str]] = {}
        self._landed_rank_cache: dict[
            tuple[str, tuple[str, ...]],
            tuple[list[_RankedTowerMatch], _RankedTowerMatch | None],
        ] = {}
        tower_aliases = tower_aliases or {}
        for node in nodes:
            if node.location_type in {"COMMUNITY", "SUBCOMMUNITY", "TOWER"}:
                variants = tower_name_variants(node.name)
                self._landed_variants[node.canonical_location_id] = variants
                for variant in variants:
                    for token in set(landed_match_tokens(variant)):
                        self._landed_token_index.setdefault(token, set()).add(
                            node.canonical_location_id
                        )
            if node.location_type != "TOWER":
                continue
            key = structural_tower_key(node.name)
            if key:
                self._towers_by_structural_key.setdefault(key, []).append(node)
            variants = tuple(
                dict.fromkeys(
                    variant
                    for value in (node.name, *tower_aliases.get(node.canonical_location_id, ()))
                    for variant in tower_name_variants(value)
                )
            )
            self._tower_variants[node.canonical_location_id] = variants
            for variant in variants:
                for token in set(tower_match_tokens(variant)):
                    self._tower_token_index.setdefault(token, set()).add(
                        node.canonical_location_id
                    )

    def resolve(self, signature: SourceSignature) -> CrosswalkDecision:
        context = signature.normalized_context
        unresolved: list[dict[str, object]] = []
        ranked_evidence: list[dict[str, object]] = []

        if signature.is_physical_tower_candidate and signature.building_name:
            authoritative_ids = self._authoritative_tower_aliases.get(
                (signature.source_system, normalize_location_name(signature.building_name)),
                (),
            )
            authoritative_candidates = [
                self._nodes_by_id[candidate_id]
                for candidate_id in authoritative_ids
                if candidate_id in self._nodes_by_id
                and self._nodes_by_id[candidate_id].location_type == "TOWER"
            ]
            if len(authoritative_candidates) == 1:
                return self._approved(
                    candidate=authoritative_candidates[0],
                    source_field="building",
                    candidate_count=1,
                    parent_supported=self._has_ancestor_context(
                        authoritative_candidates[0], context
                    ),
                    raw_value=signature.building_name,
                    match_method="authoritative_tower_alias",
                    extra_evidence={
                        "alias_provenance": "reviewed_or_dld_transaction_consensus"
                    },
                )

            exact_decision, exact_unresolved = self._resolve_exact_tower(
                raw_value=signature.building_name,
                context=context,
            )
            if exact_decision is not None:
                return exact_decision
            if exact_unresolved is not None:
                unresolved.append(exact_unresolved)

            stripped_context_values = tuple(
                stripped.strip(" -")
                for value in (
                    signature.area_name,
                    signature.project_name,
                    signature.master_project_name,
                )
                if value
                and (
                    stripped := re.sub(
                        re.escape(value),
                        " ",
                        signature.building_name,
                        flags=re.IGNORECASE,
                    )
                ).strip(" -")
                and stripped.strip(" -") != signature.building_name
            )
            ranked, approved = self._rank_tower_candidates(
                raw_value=signature.building_name,
                context=context,
                supplemental_values=(
                    *stripped_context_values,
                    *(
                        f"{value} {signature.building_name}"
                        for value in (signature.project_name, signature.master_project_name)
                        if value
                    ),
                ),
            )
            ranked_evidence = [candidate.evidence() for candidate in ranked[:5]]
            if approved is not None:
                return self._approved(
                    candidate=approved.candidate,
                    source_field="building",
                    candidate_count=len(ranked),
                    parent_supported=approved.context_supported,
                    raw_value=signature.building_name,
                    match_method=f"ranked_{approved.method}",
                    extra_evidence={
                        "score": approved.score,
                        "ranked_candidates": ranked_evidence,
                    },
                )

        if signature.is_landed_phase and signature.building_name:
            stripped_context_values = tuple(
                stripped.strip(" -")
                for value in (
                    signature.area_name,
                    signature.project_name,
                    signature.master_project_name,
                )
                if value
                and (
                    stripped := re.sub(
                        re.escape(value),
                        " ",
                        signature.building_name,
                        flags=re.IGNORECASE,
                    )
                ).strip(" -")
                and stripped.strip(" -") != signature.building_name
            )
            landed_ranked, landed_approved = self._rank_landed_candidates(
                raw_value=signature.building_name,
                context=context,
                supplemental_values=stripped_context_values,
            )
            ranked_evidence = [candidate.evidence() for candidate in landed_ranked[:5]]
            if landed_approved is not None:
                return self._approved(
                    candidate=landed_approved.candidate,
                    source_field="building_aggregate",
                    candidate_count=len(landed_ranked),
                    parent_supported=landed_approved.context_supported,
                    raw_value=signature.building_name,
                    match_method=f"ranked_landed_{landed_approved.method}",
                    target_grain=(
                        "landed_phase"
                        if landed_approved.candidate.location_type == "TOWER"
                        else None
                    ),
                    extra_evidence={
                        "score": landed_approved.score,
                        "ranked_candidates": ranked_evidence,
                        "source_entity_class": "landed_phase",
                    },
                )

        project_target_types = (
            ("SUBCOMMUNITY",)
            if signature.source_entity_class == "offplan_project"
            else ("SUBCOMMUNITY", "COMMUNITY")
            if signature.is_landed_phase
            else ("TOWER", "SUBCOMMUNITY")
        )
        levels = (
            ("project", signature.project_name, project_target_types),
            (
                "master_project",
                signature.master_project_name,
                ("SUBCOMMUNITY", "COMMUNITY"),
            ),
            (
                "building_aggregate",
                signature.building_name,
                ("SUBCOMMUNITY", "COMMUNITY"),
            ),
            ("area", signature.area_name, ("COMMUNITY", "SUBCOMMUNITY")),
        )
        for source_field, raw_value, target_types in levels:
            normalized = normalize_location_name(raw_value)
            if not normalized:
                continue
            candidates = self._candidates(normalized, target_types)
            if not candidates:
                continue
            supported = [
                candidate
                for candidate in candidates
                if self._has_ancestor_context(candidate, context - {normalized})
            ]
            if len(supported) == 1:
                return self._approved(
                    candidate=supported[0],
                    source_field=source_field,
                    candidate_count=len(candidates),
                    parent_supported=True,
                    raw_value=raw_value,
                    extra_evidence={"ranked_candidates": ranked_evidence},
                )
            if len(candidates) == 1 and (
                candidates[0].location_type == "COMMUNITY" or source_field == "area"
                or (
                    signature.is_landed_phase
                    and source_field in {"project", "building_aggregate"}
                    and candidates[0].location_type == "SUBCOMMUNITY"
                    and not is_generic_leaf_name(raw_value)
                )
            ):
                return self._approved(
                    candidate=candidates[0],
                    source_field=source_field,
                    candidate_count=1,
                    parent_supported=False,
                    raw_value=raw_value,
                    extra_evidence={"ranked_candidates": ranked_evidence},
                )
            unresolved.append(
                {
                    "source_field": source_field,
                    "source_value": raw_value,
                    "candidate_ids": [candidate.canonical_location_id for candidate in candidates],
                    "parent_supported_ids": [
                        candidate.canonical_location_id for candidate in supported
                    ],
                }
            )

        candidate_ids = {
            candidate_id
            for item in unresolved
            for candidate_id in item.get("candidate_ids", [])
            if isinstance(candidate_id, str)
        }
        if ranked_evidence:
            candidate_ids.update(
                str(item["canonical_location_id"])
                for item in ranked_evidence
                if item.get("canonical_location_id")
            )
        if candidate_ids:
            return CrosswalkDecision(
                canonical_location_id=None,
                target_grain="",
                relation="",
                status="ambiguous" if len(candidate_ids) > 1 else "suggested",
                match_method=(
                    "ranked_landed_requires_review"
                    if ranked_evidence and signature.is_landed_phase
                    else "ranked_tower_requires_review"
                    if ranked_evidence
                    else "exact_name_requires_review"
                ),
                confidence="review",
                candidate_count=len(candidate_ids),
                evidence={
                    "unresolved_candidates": unresolved,
                    "ranked_candidates": ranked_evidence,
                },
            )

        return CrosswalkDecision(
            canonical_location_id=None,
            target_grain="",
            relation="",
            status="unmapped",
            match_method="none",
            confidence="none",
            candidate_count=0,
            evidence={"reason": "no deterministic Property Finder candidate"},
        )

    def _resolve_exact_tower(
        self,
        *,
        raw_value: str,
        context: set[str],
    ) -> tuple[CrosswalkDecision | None, dict[str, object] | None]:
        normalized = normalize_location_name(raw_value)
        candidates = self._candidates(normalized, ("TOWER",))
        supported = [
            candidate
            for candidate in candidates
            if self._has_ancestor_context(candidate, context - {normalized})
        ]
        if len(supported) == 1:
            return (
                self._approved(
                    candidate=supported[0],
                    source_field="building",
                    candidate_count=len(candidates),
                    parent_supported=True,
                    raw_value=raw_value,
                ),
                None,
            )
        if len(candidates) == 1 and not is_generic_leaf_name(raw_value):
            return (
                self._approved(
                    candidate=candidates[0],
                    source_field="building",
                    candidate_count=1,
                    parent_supported=False,
                    raw_value=raw_value,
                ),
                None,
            )

        structural_key = structural_tower_key(raw_value)
        structural_candidates = self._towers_by_structural_key.get(structural_key, [])
        structural_supported = [
            candidate
            for candidate in structural_candidates
            if self._has_ancestor_context(candidate, context - {normalized})
        ]
        structural_candidate = (
            structural_supported[0]
            if len(structural_supported) == 1
            else structural_candidates[0]
            if len(structural_candidates) == 1
            and len(structural_key) >= 6
            and not is_generic_leaf_name(raw_value)
            else None
        )
        if structural_candidate is not None:
            return (
                self._approved(
                    candidate=structural_candidate,
                    source_field="building",
                    candidate_count=len(structural_candidates),
                    parent_supported=len(structural_supported) == 1,
                    raw_value=raw_value,
                    match_method=(
                        "structural_name_parent_context"
                        if len(structural_supported) == 1
                        else "structural_unique_tower"
                    ),
                ),
                None,
            )
        exact_candidates = candidates or structural_candidates
        if not exact_candidates:
            return None, None
        return None, {
            "source_field": "building",
            "source_value": raw_value,
            "candidate_ids": [
                candidate.canonical_location_id for candidate in exact_candidates
            ],
            "parent_supported_ids": [
                candidate.canonical_location_id
                for candidate in (supported or structural_supported)
            ],
        }

    def _rank_tower_candidates(
        self,
        *,
        raw_value: str,
        context: set[str],
        supplemental_values: tuple[str, ...] = (),
    ) -> tuple[list[_RankedTowerMatch], _RankedTowerMatch | None]:
        cache_key = ("|".join((raw_value, *supplemental_values)), tuple(sorted(context)))
        if cache_key in self._rank_cache:
            return self._rank_cache[cache_key]
        source_variants = tuple(
            dict.fromkeys(
                variant
                for value in (raw_value, *supplemental_values)
                for variant in tower_name_variants(value)
            )
        )
        source_tokens = {
            token for variant in source_variants for token in tower_match_tokens(variant)
        }
        source_identity = {
            token for variant in source_variants for token in tower_identity_tokens(variant)
        }
        lookup_tokens = source_tokens - _BROAD_LOCATION_TOKENS - source_identity
        if not source_tokens or not lookup_tokens:
            self._rank_cache[cache_key] = ([], None)
            return self._rank_cache[cache_key]
        lookup_tokens = set(
            sorted(
                lookup_tokens,
                key=lambda token: (
                    len(self._tower_token_index.get(token, set())),
                    token,
                ),
            )[:2]
        )
        candidate_ids = {
            candidate_id
            for token in lookup_tokens
            for candidate_id in self._tower_token_index.get(token, set())
        }
        context_candidate_ids = {
            candidate_id
            for candidate_id in candidate_ids
            if self._has_ancestor_context(self._nodes_by_id[candidate_id], context)
        }
        if context_candidate_ids:
            candidate_ids = context_candidate_ids
        ranked: list[_RankedTowerMatch] = []
        for candidate_id in candidate_ids:
            candidate = self._nodes_by_id[candidate_id]
            best: _RankedTowerMatch | None = None
            for source_priority, source_variant in enumerate(source_variants):
                for target_variant in self._tower_variants[candidate_id]:
                    scored = self._score_tower_pair(
                        source_variant=source_variant,
                        target_variant=target_variant,
                    )
                    if scored is None:
                        continue
                    score, method = scored
                    match = _RankedTowerMatch(
                        candidate=candidate,
                        score=score,
                        method=(
                            f"alias_{method}" if target_variant != candidate.name else method
                        ),
                        context_supported=self._has_ancestor_context(candidate, context),
                        source_variant=source_variant,
                        target_variant=target_variant,
                        source_priority=source_priority,
                        identity_strength=len(tower_identity_tokens(source_variant)),
                    )
                    if best is None or (
                        match.score,
                        -match.source_priority,
                        match.identity_strength,
                    ) > (
                        best.score,
                        -best.source_priority,
                        best.identity_strength,
                    ):
                        best = match
            if best is not None and best.score >= 70:
                ranked.append(best)

        context_ranked = [candidate for candidate in ranked if candidate.context_supported]
        if context_ranked:
            ranked = context_ranked
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.source_priority,
                -item.identity_strength,
                item.candidate.canonical_location_id,
            )
        )
        if not ranked:
            self._rank_cache[cache_key] = ([], None)
            return self._rank_cache[cache_key]
        top = ranked[0]
        second_score = ranked[1].score if len(ranked) > 1 else 0
        margin = top.score - second_score
        exact_equivalent = top.method.endswith("token_equivalent")
        exact_equivalent_count = sum(
            candidate.score == 100 and candidate.method.endswith("token_equivalent")
            for candidate in ranked
        )
        source_complete_count = sum(candidate.score == 98 for candidate in ranked)
        top_priority_is_unique = all(
            candidate.source_priority > top.source_priority
            for candidate in ranked[1:]
            if candidate.score == top.score
        )
        preferred_primary_variant = top_priority_is_unique and (
            exact_equivalent or top.identity_strength > 0
        )
        safe_context_match = (
            top.context_supported
            and top.score >= 96
            and (
                (exact_equivalent and exact_equivalent_count == 1)
                or (top.score == 98 and source_complete_count == 1)
                or preferred_primary_variant
                or len(ranked) == 1
                or margin >= 8
            )
        )
        safe_global_exact = (
            not top.context_supported
            and exact_equivalent
            and exact_equivalent_count == 1
            and top.score == 100
            and len("".join(tower_match_tokens(top.source_variant))) >= 5
        )
        self._rank_cache[cache_key] = (
            ranked,
            top if safe_context_match or safe_global_exact else None,
        )
        return self._rank_cache[cache_key]

    def _rank_landed_candidates(
        self,
        *,
        raw_value: str,
        context: set[str],
        supplemental_values: tuple[str, ...] = (),
    ) -> tuple[list[_RankedTowerMatch], _RankedTowerMatch | None]:
        """Rank PF communities/phases for a landed property without tower semantics."""
        cache_key = ("|".join((raw_value, *supplemental_values)), tuple(sorted(context)))
        if cache_key in self._landed_rank_cache:
            return self._landed_rank_cache[cache_key]
        source_variants = tuple(
            dict.fromkeys(
                variant
                for value in (raw_value, *supplemental_values)
                for variant in tower_name_variants(value)
            )
        )
        source_tokens = {
            token for variant in source_variants for token in landed_match_tokens(variant)
        }
        source_identity = {
            token for variant in source_variants for token in tower_identity_tokens(variant)
        }
        lookup_tokens = source_tokens - _BROAD_LOCATION_TOKENS - source_identity
        if not source_tokens or not lookup_tokens:
            self._landed_rank_cache[cache_key] = ([], None)
            return self._landed_rank_cache[cache_key]
        lookup_tokens = set(
            sorted(
                lookup_tokens,
                key=lambda token: (
                    len(self._landed_token_index.get(token, set())),
                    token,
                ),
            )[:2]
        )
        candidate_ids = {
            candidate_id
            for token in lookup_tokens
            for candidate_id in self._landed_token_index.get(token, set())
        }
        context_candidate_ids = {
            candidate_id
            for candidate_id in candidate_ids
            if self._has_ancestor_context(self._nodes_by_id[candidate_id], context)
        }
        if context_candidate_ids:
            candidate_ids = context_candidate_ids

        ranked: list[_RankedTowerMatch] = []
        for candidate_id in candidate_ids:
            candidate = self._nodes_by_id[candidate_id]
            if candidate.location_type == "TOWER" and (
                set(_normalized_words(candidate.name)) & _VERTICAL_ASSET_TOKENS
            ):
                continue
            best: _RankedTowerMatch | None = None
            for source_priority, source_variant in enumerate(source_variants):
                for target_variant in self._landed_variants[candidate_id]:
                    scored = self._score_landed_pair(
                        source_variant=source_variant,
                        target_variant=target_variant,
                    )
                    if scored is None:
                        continue
                    score, method = scored
                    match = _RankedTowerMatch(
                        candidate=candidate,
                        score=score,
                        method=method,
                        context_supported=self._has_ancestor_context(candidate, context),
                        source_variant=source_variant,
                        target_variant=target_variant,
                        source_priority=source_priority,
                        identity_strength=len(tower_identity_tokens(source_variant)),
                    )
                    if best is None or (
                        match.score,
                        -match.source_priority,
                        match.identity_strength,
                    ) > (
                        best.score,
                        -best.source_priority,
                        best.identity_strength,
                    ):
                        best = match
            if best is not None and best.score >= 70:
                ranked.append(best)

        context_ranked = [candidate for candidate in ranked if candidate.context_supported]
        if context_ranked:
            ranked = context_ranked
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.source_priority,
                -item.identity_strength,
                item.candidate.canonical_location_id,
            )
        )
        if not ranked:
            self._landed_rank_cache[cache_key] = ([], None)
            return self._landed_rank_cache[cache_key]

        top = ranked[0]
        second_score = ranked[1].score if len(ranked) > 1 else 0
        equivalent_count = sum(
            candidate.score == 100 and candidate.method == "token_equivalent"
            for candidate in ranked
        )
        complete_count = sum(candidate.score == 98 for candidate in ranked)
        safe_context_match = (
            top.context_supported
            and top.score >= 96
            and (
                (top.score == 100 and equivalent_count == 1)
                or (top.score == 98 and complete_count == 1)
                or len(ranked) == 1
                or top.score - second_score >= 8
            )
        )
        safe_global_exact = (
            not top.context_supported
            and top.candidate.location_type in {"COMMUNITY", "SUBCOMMUNITY"}
            and top.score == 100
            and equivalent_count == 1
            and not is_generic_leaf_name(raw_value)
            and len("".join(landed_match_tokens(top.source_variant))) >= 5
        )
        self._landed_rank_cache[cache_key] = (
            ranked,
            top if safe_context_match or safe_global_exact else None,
        )
        return self._landed_rank_cache[cache_key]

    @staticmethod
    def _score_tower_pair(
        *,
        source_variant: str,
        target_variant: str,
    ) -> tuple[int, str] | None:
        source_tokens = tower_match_tokens(source_variant)
        target_tokens = tower_match_tokens(target_variant)
        if not source_tokens or not target_tokens:
            return None
        source_identity = tower_identity_tokens(source_variant)
        target_identity = tower_identity_tokens(target_variant)
        if source_identity != target_identity and (source_identity or target_identity):
            return None
        source_set = set(source_tokens)
        target_set = set(target_tokens)
        common = source_set & target_set
        if not common or not (common - _BROAD_LOCATION_TOKENS):
            return None
        if source_set == target_set:
            return 100, "token_equivalent"
        if source_set <= target_set:
            return 98, "token_containment"
        if target_set < source_set:
            return 96, "token_containment"
        token_f1 = (2 * len(common)) / (len(source_set) + len(target_set))
        sequence_score = SequenceMatcher(
            None,
            "".join(source_tokens),
            "".join(target_tokens),
        ).ratio()
        return round(60 * token_f1 + 40 * sequence_score), "token_similarity"

    @staticmethod
    def _score_landed_pair(
        *,
        source_variant: str,
        target_variant: str,
    ) -> tuple[int, str] | None:
        source_tokens = landed_match_tokens(source_variant)
        target_tokens = landed_match_tokens(target_variant)
        if not source_tokens or not target_tokens:
            return None
        source_identity = tower_identity_tokens(source_variant)
        target_identity = tower_identity_tokens(target_variant)
        if source_identity != target_identity and (source_identity or target_identity):
            return None
        source_set = set(source_tokens)
        target_set = set(target_tokens)
        common = source_set & target_set
        if not common or not (common - _BROAD_LOCATION_TOKENS):
            return None
        if source_set == target_set:
            return 100, "token_equivalent"
        if source_set <= target_set:
            return 98, "token_containment"
        if target_set < source_set:
            coverage = len(target_set) / len(source_set)
            return min(98, 94 + round(5 * coverage)), "token_containment"
        token_f1 = (2 * len(common)) / (len(source_set) + len(target_set))
        sequence_score = SequenceMatcher(
            None,
            "".join(source_tokens),
            "".join(target_tokens),
        ).ratio()
        return round(60 * token_f1 + 40 * sequence_score), "token_similarity"

    def _candidates(
        self, normalized_name: str, target_types: tuple[str, ...]
    ) -> list[LocationNode]:
        return [
            candidate
            for target_type in target_types
            for candidate in self._by_type_and_name.get((target_type, normalized_name), [])
        ]

    def _has_ancestor_context(self, candidate: LocationNode, context: set[str]) -> bool:
        if not context:
            return False
        return bool(self._ancestor_names_by_id.get(candidate.canonical_location_id, set()) & context)

    @staticmethod
    def _approved(
        *,
        candidate: LocationNode,
        source_field: str,
        candidate_count: int,
        parent_supported: bool,
        raw_value: str,
        match_method: str | None = None,
        target_grain: str | None = None,
        extra_evidence: Mapping[str, object] | None = None,
    ) -> CrosswalkDecision:
        relation = "equivalent"
        if source_field == "building_aggregate":
            relation = "ancestor_only"
        elif source_field == "area" and candidate.location_type == "SUBCOMMUNITY":
            relation = "marketed_as"
        return CrosswalkDecision(
            canonical_location_id=candidate.canonical_location_id,
            target_grain=target_grain or candidate.location_type.lower(),
            relation=relation,
            status="auto_approved",
            match_method=match_method
            or (
                "exact_name_parent_context"
                if parent_supported
                else "exact_unique_area"
                if source_field == "area"
                else "exact_unique_tower"
                if source_field == "building" and candidate.location_type == "TOWER"
                else "exact_unique_community"
            ),
            confidence="high",
            candidate_count=candidate_count,
            evidence={
                "source_field": source_field,
                "source_value": raw_value,
                "target_name": candidate.name,
                "parent_context": parent_supported,
                "generic_leaf": is_generic_leaf_name(raw_value),
                **(extra_evidence or {}),
            },
        )
