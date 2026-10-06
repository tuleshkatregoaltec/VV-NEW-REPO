from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Iterable, Literal, Mapping

from holocron.domain.geography import (
    NORMALIZATION_VERSION,
    normalize_location_name,
    tower_identity_tokens,
    tower_match_tokens,
    tower_name_variants,
)

OFFPLAN_MATCH_VERSION = NORMALIZATION_VERSION

_PROJECT_STOP_TOKENS = frozenset(
    {
        "all",
        "apartment",
        "at",
        "block",
        "building",
        "by",
        "development",
        "hotel",
        "phase",
        "project",
        "residence",
        "residency",
        "resort",
        "the",
        "tower",
        "villa",
    }
)
_WEAK_PROJECT_TOKENS = frozenset(
    {
        "city",
        "community",
        "dubai",
        "garden",
        "heights",
        "hills",
        "island",
        "park",
        "place",
        "residence",
        "tower",
        "view",
        "views",
    }
)
_MAX_TOKEN_PROJECT_FREQUENCY = 60
_ALL_PHASES = re.compile(r"\b(?:all\s+phases?|all\s+buildings?)\b", re.IGNORECASE)
_TRAILING_COMPONENT = re.compile(
    r"(?:[-,:|]\s*)?\b(?:tower|building|block|phase)\s+[a-z0-9-]+\s*$",
    re.IGNORECASE,
)


def project_match_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in tower_match_tokens(value) if token not in _PROJECT_STOP_TOKENS)


def project_name_variants(value: str, *, include_parent: bool = False) -> tuple[str, ...]:
    raw = (value or "").strip()
    if not raw:
        return ()
    variants = list(tower_name_variants(raw))
    phase_stripped = _ALL_PHASES.sub(" ", raw).strip(" -,:|")
    if phase_stripped and phase_stripped != raw:
        variants.append(phase_stripped)
    if include_parent:
        parent = _TRAILING_COMPONENT.sub("", phase_stripped).strip(" -,:|")
        if parent and parent != phase_stripped and len(project_match_tokens(parent)) >= 2:
            variants.append(parent)
    return tuple(dict.fromkeys(variants))


@dataclass(frozen=True)
class ReellyProject:
    project_id: str
    project_key: str
    project_name: str
    area_name: str
    developer_name: str = ""
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class OffplanSignature:
    source_system: str
    source_key: str
    area_name: str
    master_project_name: str
    project_name: str
    building_name: str
    property_type: str
    row_count: int
    source_build_id: str


@dataclass(frozen=True)
class OffplanProjectCandidate:
    project: ReellyProject
    score: int
    method: str
    relation: str
    context_supported: bool
    identity_compatible: bool
    source_field: str
    source_variant: str
    target_variant: str

    def evidence(self) -> dict[str, object]:
        return {
            "reelly_project_id": self.project.project_id,
            "project_name": self.project.project_name,
            "area_name": self.project.area_name,
            "score": self.score,
            "method": self.method,
            "relation": self.relation,
            "context_supported": self.context_supported,
            "identity_compatible": self.identity_compatible,
            "source_field": self.source_field,
            "source_variant": self.source_variant,
            "target_variant": self.target_variant,
        }


@dataclass(frozen=True)
class OffplanProjectDecision:
    reelly_project_id: str | None
    relation: str
    status: str
    match_method: str
    confidence: str
    candidate_count: int
    evidence: dict[str, object]

    def evidence_json(self) -> str:
        return json.dumps(self.evidence, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class OffplanProjectOverride:
    reelly_project_id: str | None
    decision: Literal["approve", "reject"]
    relation: str
    review_note: str
    reviewed_by: str


def decision_from_offplan_override(
    override: OffplanProjectOverride,
    projects_by_id: Mapping[str, ReellyProject],
) -> OffplanProjectDecision:
    if override.decision == "reject":
        if override.reelly_project_id is not None:
            raise ValueError("Rejected off-plan override cannot have a Reelly target")
        return OffplanProjectDecision(
            reelly_project_id=None,
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
    if override.reelly_project_id is None:
        raise ValueError("Approved off-plan override requires a Reelly target")
    target = projects_by_id.get(override.reelly_project_id)
    if target is None:
        raise ValueError(f"Off-plan override target does not exist: {override.reelly_project_id}")
    return OffplanProjectDecision(
        reelly_project_id=target.project_id,
        relation=override.relation or "equivalent",
        status="manual_approved",
        match_method="manual_override",
        confidence="reviewed",
        candidate_count=1,
        evidence={
            "project_name": target.project_name,
            "review_note": override.review_note,
            "reviewed_by": override.reviewed_by,
        },
    )


class OffplanProjectResolver:
    """Resolve registry off-plan labels to the finite Reelly Dubai catalogue."""

    def __init__(self, projects: Iterable[ReellyProject]) -> None:
        self._projects = tuple(projects)
        self._by_id = {project.project_id: project for project in self._projects}
        if len(self._by_id) != len(self._projects):
            raise ValueError("Reelly project ids must be unique")
        self._target_variants = {
            project.project_id: project_name_variants(project.project_name)
            for project in self._projects
        }
        self._exact_index: dict[str, set[str]] = {}
        self._token_index: dict[str, set[str]] = {}
        self._area_umbrella_index: dict[str, set[str]] = {}
        for project in self._projects:
            project_name_key = normalize_location_name(project.project_name)
            project_area_key = normalize_location_name(project.area_name)
            if project_name_key and project_name_key == project_area_key:
                self._area_umbrella_index.setdefault(project_area_key, set()).add(
                    project.project_id
                )
            for variant in self._target_variants[project.project_id]:
                normalized = normalize_location_name(variant)
                if normalized:
                    self._exact_index.setdefault(normalized, set()).add(project.project_id)
                for token in set(project_match_tokens(variant)) - _WEAK_PROJECT_TOKENS:
                    self._token_index.setdefault(token, set()).add(project.project_id)
        self._token_index = {
            token: project_ids
            for token, project_ids in self._token_index.items()
            if len(project_ids) <= _MAX_TOKEN_PROJECT_FREQUENCY
        }
        self._decision_cache: dict[tuple[str, str, str, str], OffplanProjectDecision] = {}

    def resolve(self, signature: OffplanSignature) -> OffplanProjectDecision:
        cache_key = (
            signature.area_name,
            signature.master_project_name,
            signature.project_name,
            signature.building_name,
        )
        cached = self._decision_cache.get(cache_key)
        if cached is not None:
            return cached
        decision = self._resolve_uncached(signature)
        self._decision_cache[cache_key] = decision
        return decision

    def _resolve_uncached(self, signature: OffplanSignature) -> OffplanProjectDecision:
        candidates = self._rank(signature)
        if not candidates:
            umbrella = self._area_umbrella_decision(signature, specific_candidates=[])
            if umbrella is not None:
                return umbrella
            return OffplanProjectDecision(
                reelly_project_id=None,
                relation="",
                status="unmapped",
                match_method="catalogue_absent_or_no_name_candidate",
                confidence="none",
                candidate_count=0,
                evidence={
                    "reason": "no compatible Reelly Dubai catalogue candidate",
                    "catalogue_scope": "Dubai projects with valid identifiers",
                },
            )

        top = candidates[0]
        runner_up = candidates[1].score if len(candidates) > 1 else 0
        margin = top.score - runner_up
        tied_targets = {
            candidate.project.project_id for candidate in candidates if candidate.score == top.score
        }
        auto_approved = (
            len(tied_targets) == 1
            and top.identity_compatible
            and (
                top.method == "exact_name"
                or top.method == "structural_name"
                or (top.method == "token_equivalent" and top.score >= 96 and margin >= 5)
                or (
                    top.method == "component_name"
                    and top.score >= 93
                    and margin >= 8
                    and (
                        top.context_supported or len(project_match_tokens(top.target_variant)) >= 3
                    )
                )
                or (
                    top.method == "catalogue_name_expansion"
                    and (top.context_supported or top.source_field in {"project", "master_project"})
                    and top.score >= 94
                    and margin >= 8
                )
                or (
                    top.method == "contextual_fuzzy"
                    and top.context_supported
                    and top.score >= 95
                    and margin >= 8
                )
            )
        )
        evidence = {
            "top_score": top.score,
            "score_margin": margin,
            "ranked_candidates": [candidate.evidence() for candidate in candidates[:5]],
        }
        if auto_approved:
            return OffplanProjectDecision(
                reelly_project_id=top.project.project_id,
                relation=top.relation,
                status="auto_approved",
                match_method=top.method,
                confidence="exact" if top.score == 100 else "high",
                candidate_count=len(candidates),
                evidence=evidence,
            )

        umbrella = self._area_umbrella_decision(
            signature,
            specific_candidates=evidence["ranked_candidates"],
        )
        if umbrella is not None:
            return umbrella

        close_candidates = [
            candidate for candidate in candidates if top.score - candidate.score < 8
        ]
        return OffplanProjectDecision(
            reelly_project_id=None,
            relation="",
            status="ambiguous" if len(close_candidates) > 1 else "suggested",
            match_method="catalogue_candidate_requires_review",
            confidence="review",
            candidate_count=len(candidates),
            evidence=evidence,
        )

    def _area_umbrella_decision(
        self,
        signature: OffplanSignature,
        *,
        specific_candidates: list[dict[str, object]],
    ) -> OffplanProjectDecision | None:
        umbrella_ids = self._area_umbrella_index.get(
            normalize_location_name(signature.area_name), set()
        )
        if len(umbrella_ids) != 1 or not (signature.project_name or signature.building_name):
            return None
        umbrella = self._by_id[next(iter(umbrella_ids))]
        return OffplanProjectDecision(
            reelly_project_id=umbrella.project_id,
            relation="component_of",
            status="auto_approved",
            match_method="catalogue_area_umbrella",
            confidence="coarse",
            candidate_count=1,
            evidence={
                "area_name": signature.area_name,
                "catalogue_project_name": umbrella.project_name,
                "reason": "unique Reelly project and area share the registry area name",
                "specific_candidates": specific_candidates,
            },
        )

    def _rank(self, signature: OffplanSignature) -> list[OffplanProjectCandidate]:
        source_values = tuple(
            (field, variant)
            for field, value in (
                ("project", signature.project_name),
                ("building", signature.building_name),
                ("master_project", signature.master_project_name),
            )
            for variant in project_name_variants(value, include_parent=True)
        )
        best_by_project: dict[str, OffplanProjectCandidate] = {}
        for source_field, source_variant in source_values:
            source_normalized = normalize_location_name(source_variant)
            source_tokens = frozenset(project_match_tokens(source_variant))
            if not source_normalized or not source_tokens:
                continue
            project_ids = set(self._exact_index.get(source_normalized, ()))
            indexed_tokens = [
                token
                for token in source_tokens - _WEAK_PROJECT_TOKENS
                if token in self._token_index
            ]
            token_hits: dict[str, int] = {}
            for token in indexed_tokens:
                token_projects = self._token_index[token]
                if len(indexed_tokens) == 1 and (len(token) < 5 or len(token_projects) > 8):
                    continue
                for project_id in token_projects:
                    token_hits[project_id] = token_hits.get(project_id, 0) + 1
            minimum_hits = 2 if len(indexed_tokens) >= 2 else 1
            project_ids.update(
                project_id
                for project_id, hit_count in token_hits.items()
                if hit_count >= minimum_hits
            )
            for project_id in project_ids:
                project = self._by_id[project_id]
                for target_variant in self._target_variants[project_id]:
                    candidate = self._score(
                        signature=signature,
                        project=project,
                        source_field=source_field,
                        source_variant=source_variant,
                        target_variant=target_variant,
                    )
                    if candidate is None:
                        continue
                    current = best_by_project.get(project_id)
                    if current is None or self._sort_key(candidate) < self._sort_key(current):
                        best_by_project[project_id] = candidate
        return sorted(best_by_project.values(), key=self._sort_key)[:10]

    @staticmethod
    def _sort_key(candidate: OffplanProjectCandidate) -> tuple[object, ...]:
        field_priority = {"building": 0, "project": 1, "master_project": 2}
        return (
            -candidate.score,
            -int(candidate.context_supported),
            field_priority.get(candidate.source_field, 9),
            candidate.project.project_id,
        )

    @staticmethod
    def _score(
        *,
        signature: OffplanSignature,
        project: ReellyProject,
        source_field: str,
        source_variant: str,
        target_variant: str,
    ) -> OffplanProjectCandidate | None:
        source_normalized = normalize_location_name(source_variant)
        target_normalized = normalize_location_name(target_variant)
        original_source = {
            "project": signature.project_name,
            "building": signature.building_name,
            "master_project": signature.master_project_name,
        }.get(source_field, "")
        source_tokens = frozenset(project_match_tokens(source_variant))
        target_tokens = frozenset(project_match_tokens(target_variant))
        if not source_tokens or not target_tokens:
            return None
        source_identity = tower_identity_tokens(source_variant)
        target_identity = tower_identity_tokens(target_variant)
        common_identity = source_identity & target_identity
        identity_compatible = not (source_identity and target_identity and not common_identity)
        original_identity = tower_identity_tokens(original_source)
        if (
            normalize_location_name(original_source) != source_normalized
            and original_identity
            and target_identity
            and not (original_identity & target_identity)
        ):
            identity_compatible = False
        if not identity_compatible:
            return None

        context_supported = _area_context_supported(signature.area_name, project.area_name)
        developer_tokens = {
            token
            for token in project_match_tokens(project.developer_name)
            if token not in _WEAK_PROJECT_TOKENS and len(token) >= 4
        }
        developer_supported = bool(developer_tokens & set(source_tokens))
        relation = "equivalent"
        parent_variant = (
            bool(original_source)
            and normalize_location_name(original_source) != source_normalized
            and target_normalized == source_normalized
        )
        if parent_variant:
            score, method, relation = 95, "component_name", "component_of"
        elif source_normalized == target_normalized:
            score, method = 100, "exact_name"
        elif _structural_project_key(source_variant) == _structural_project_key(target_variant):
            score, method = 98, "structural_name"
        elif source_tokens == target_tokens:
            score, method = 96, "token_equivalent"
        elif target_tokens < source_tokens and (
            len(target_tokens) >= 2
            or (
                len(target_tokens) == 1
                and len(next(iter(target_tokens))) >= 5
                and context_supported
                and developer_supported
            )
        ):
            extras = len(source_tokens - target_tokens)
            score, method, relation = max(88, 95 - extras), "component_name", "component_of"
        elif source_tokens < target_tokens and (
            len(source_tokens) >= 2
            or (
                len(source_tokens) == 1
                and context_supported
                and (target_tokens - source_tokens)
                <= frozenset(project_match_tokens(signature.area_name))
            )
        ):
            extras = len(target_tokens - source_tokens)
            score, method = max(88, 96 - extras), "catalogue_name_expansion"
            if source_field != "building" and signature.building_name:
                relation = "component_of"
        else:
            token_overlap = len(source_tokens & target_tokens) / len(source_tokens | target_tokens)
            containment = len(source_tokens & target_tokens) / min(
                len(source_tokens), len(target_tokens)
            )
            if token_overlap < 0.25 or containment < 0.50:
                return None
            sequence = SequenceMatcher(None, source_normalized, target_normalized).ratio()
            score = round(100 * (0.45 * token_overlap + 0.35 * containment + 0.20 * sequence))
            if context_supported:
                score = min(99, score + 4)
            method = "contextual_fuzzy" if context_supported else "fuzzy_name"
        if score < 72:
            return None
        return OffplanProjectCandidate(
            project=project,
            score=score,
            method=method,
            relation=relation,
            context_supported=context_supported,
            identity_compatible=identity_compatible,
            source_field=source_field,
            source_variant=source_variant,
            target_variant=target_variant,
        )


def transaction_consensus_decision(
    *,
    current: OffplanProjectDecision,
    project: ReellyProject,
    matched_sales: int,
    all_matched_sales: int,
    total_source_events: int,
    name_compatible: bool = True,
) -> OffplanProjectDecision:
    """Promote an independently corroborated DLD target without hiding conflicts."""
    if current.status in {"auto_approved", "manual_approved"}:
        return current
    dominance = matched_sales / max(1, all_matched_sales)
    coverage = matched_sales / max(1, total_source_events)
    approved = (
        name_compatible
        and dominance >= 0.99
        and ((matched_sales >= 2 and coverage >= 0.15) or coverage >= 0.50)
    )
    if not approved:
        return current
    return replace(
        current,
        reelly_project_id=project.project_id,
        relation="equivalent",
        status="auto_approved",
        match_method="dld_transaction_consensus",
        confidence="high",
        candidate_count=1,
        evidence={
            "all_matched_sales": all_matched_sales,
            "catalogue_project_name": project.project_name,
            "matched_sales": matched_sales,
            "matched_share": round(dominance, 6),
            "source_coverage": round(coverage, 6),
            "total_source_events": total_source_events,
        },
    )


def transaction_name_compatible(
    signature: OffplanSignature,
    project: ReellyProject,
) -> bool:
    """Require a distinctive shared name token before consensus approval."""
    source_tokens = {
        token
        for value in (
            signature.project_name,
            signature.building_name,
            signature.master_project_name,
        )
        for token in project_match_tokens(value)
        if token not in _WEAK_PROJECT_TOKENS and len(token) >= 4
    }
    target_tokens = {
        token
        for token in project_match_tokens(project.project_name)
        if token not in _WEAK_PROJECT_TOKENS and len(token) >= 4
    }
    return bool(source_tokens & target_tokens)


def _structural_project_key(value: str) -> str:
    return "".join(project_match_tokens(value))


def _area_context_supported(source_area: str, target_area: str) -> bool:
    for source_variant in tower_name_variants(source_area):
        source = normalize_location_name(source_variant)
        source_tokens = set(tower_match_tokens(source_variant)) - _WEAK_PROJECT_TOKENS
        for target_variant in tower_name_variants(target_area):
            target = normalize_location_name(target_variant)
            target_tokens = set(tower_match_tokens(target_variant)) - _WEAK_PROJECT_TOKENS
            if source and source == target:
                return True
            if source_tokens and target_tokens and source_tokens == target_tokens:
                return True
    return False
