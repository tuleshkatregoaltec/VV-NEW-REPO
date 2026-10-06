from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from dagster import MaterializeResult, asset

from holocron.domain.geography import (
    NORMALIZATION_VERSION,
    GeographyResolver,
    LinkOverride,
    LocationNode,
    SourceSignature,
    decision_from_override,
    normalize_location_name,
)
from holocron.domain.offplan_projects import (
    OFFPLAN_MATCH_VERSION,
    OffplanProjectDecision,
    OffplanProjectOverride,
    OffplanProjectResolver,
    OffplanSignature,
    ReellyProject,
    decision_from_offplan_override,
    transaction_consensus_decision,
    transaction_name_compatible,
)
from holocron.platform.clickhouse import ClickHouseClient
from holocron.platform.clickhouse_schema import ensure_schema
from holocron.platform.resources import ClickHouseResource

_GEOGRAPHY_GROUP = "geography"
_DUBAI_BOUNDS = (24.5, 26.0, 54.5, 56.5)
_CURATED_TOWER_ALIASES = (
    ("pf:3037", "Botanica Tower 1", "PF omits the registry's sole-tower suffix"),
    ("pf:3333", "Frankfurt Sports Tower I", "PF omits the registry's Roman suffix"),
    ("pf:17170", "Green Lakes S1", "Cluster S tower 1"),
    ("pf:17171", "Green Lakes S2", "Cluster S tower 2"),
    ("pf:17172", "Green Lakes S3", "Cluster S tower 3"),
    ("pf:8397", "Axis Silver", "PF names the sole tower Axis Silver 1"),
    ("pf:3064", "Marina Heights 1", "PF omits the registry's sole-tower suffix"),
    ("pf:3178", "Royal Oceanic 1", "PF omits the registry's sole-tower suffix"),
    ("pf:3785", "Lakepoint N2", "JLT Cluster N Lake Point registry code"),
    ("pf:4571", "Links West T1", "The Links west tower registry code"),
    ("pf:4570", "Links East T2", "The Links east tower registry code"),
    ("pf:9530", "Building 1 (CW)", "Ready City Walk residential building 1"),
    ("pf:16050", "Act One Act Two Tower 1", "Act One tower in the paired project"),
    ("pf:4161", "Newbridge Hill 1", "PF separates New Bridge and pluralises Hills"),
    ("pf:4162", "Newbridge Hill 2", "PF separates New Bridge and pluralises Hills"),
    ("pf:4163", "Newbridge Hill 3", "PF separates New Bridge and pluralises Hills"),
    ("pf:4208", "Altajer", "DLD compact spelling for Tajer Residences"),
    ("pf:1378", "Platinum 1", "PF spells the tower number as One"),
    ("pf:2754", "Lofts T East", "The Lofts east tower registry shorthand"),
    ("pf:2755", "Lofts T West", "The Lofts west tower registry shorthand"),
    ("pf:2756", "Lofts T Cent", "The Lofts central tower registry shorthand"),
    ("pf:9655", "Una Apartments B", "DLD identifies building B within the sole PF UNA pin"),
)

_NODE_COLUMNS = (
    "canonical_location_id",
    "source_location_id",
    "parent_canonical_location_id",
    "snapshot_id",
    "scraped_at",
    "location_type",
    "level",
    "name",
    "normalized_name",
    "path_name",
    "path_ids_json",
    "latitude",
    "longitude",
    "coordinate_status",
    "published",
)
_CLOSURE_COLUMNS = (
    "ancestor_location_id",
    "descendant_location_id",
    "depth",
    "snapshot_id",
)
_SIGNATURE_COLUMNS = (
    "source_system",
    "source_key",
    "source_grain",
    "property_type",
    "market_status",
    "source_entity_class",
    "raw_area_name",
    "raw_master_project_name",
    "raw_project_name",
    "raw_building_name",
    "normalized_area_name",
    "normalized_master_project",
    "normalized_project_name",
    "normalized_building_name",
    "row_count",
    "represented_value_aed",
    "first_observed",
    "last_observed",
    "normalization_version",
    "build_id",
)
_ALIAS_COLUMNS = (
    "canonical_location_id",
    "alias_name",
    "normalized_alias",
    "source_system",
    "evidence_json",
    "status",
    "reviewed_by",
    "reviewed_at",
    "active",
)
_CANDIDATE_COLUMNS = (
    "source_system",
    "source_key",
    "candidate_rank",
    "canonical_location_id",
    "target_name",
    "score",
    "context_supported",
    "identity_compatible",
    "match_method",
    "source_variant",
    "target_variant",
    "build_id",
)
_LINK_COLUMNS = (
    "source_system",
    "source_key",
    "canonical_location_id",
    "target_grain",
    "relation",
    "status",
    "match_method",
    "confidence",
    "candidate_count",
    "evidence_json",
    "normalization_version",
    "pf_snapshot_id",
    "build_id",
)
_OFFPLAN_LINK_COLUMNS = (
    "source_system",
    "source_key",
    "reelly_project_id",
    "relation",
    "status",
    "match_method",
    "confidence",
    "candidate_count",
    "evidence_json",
    "normalization_version",
    "catalog_build_id",
    "source_build_id",
)
_OFFPLAN_CANDIDATE_COLUMNS = (
    "source_system",
    "source_key",
    "candidate_rank",
    "reelly_project_id",
    "project_name",
    "area_name",
    "score",
    "context_supported",
    "identity_compatible",
    "match_method",
    "relation",
    "source_field",
    "source_variant",
    "target_variant",
    "catalog_build_id",
    "source_build_id",
)


@asset(
    name="geo_location_nodes",
    group_name=_GEOGRAPHY_GROUP,
    deps=["pf_locations_bronze"],
    description="Canonical, typed PF Dubai location nodes with invalid coordinates quarantined.",
)
def geo_location_nodes_asset(
    context,
    clickhouse: ClickHouseResource,
) -> MaterializeResult:
    client = clickhouse.client()
    counts = materialize_geo_location_nodes(clickhouse=client)
    context.log.info("geo_location_nodes materialised: %s", counts)
    return MaterializeResult(metadata={"stage": "geography", **counts})


@asset(
    name="geo_location_closure",
    group_name=_GEOGRAPHY_GROUP,
    deps=["geo_location_nodes"],
    description="Ancestor/descendant closure for the canonical PF hierarchy.",
)
def geo_location_closure_asset(
    context,
    clickhouse: ClickHouseResource,
) -> MaterializeResult:
    client = clickhouse.client()
    row_count = materialize_geo_location_closure(clickhouse=client)
    context.log.info("geo_location_closure materialised: %d rows", row_count)
    return MaterializeResult(
        metadata={"stage": "geography", "table": "geo_location_closure", "row_count": row_count}
    )


@asset(
    name="geo_source_signatures",
    group_name=_GEOGRAPHY_GROUP,
    deps=["geo_location_nodes", "dld_od_transactions_bronze", "dxbi_transactions_bronze"],
    description="Distinct DLD and DXBI geography tuples with row/value impact metrics.",
)
def geo_source_signatures_asset(
    context,
    clickhouse: ClickHouseResource,
) -> MaterializeResult:
    client = clickhouse.client()
    counts = materialize_geo_source_signatures(clickhouse=client)
    context.log.info("geo_source_signatures materialised: %s", counts)
    return MaterializeResult(metadata={"stage": "geography", **counts})


@asset(
    name="geo_entity_links",
    group_name=_GEOGRAPHY_GROUP,
    deps=["geo_location_nodes", "geo_location_closure", "geo_source_signatures"],
    description="Conservative deterministic links from source signatures to canonical PF nodes.",
)
def geo_entity_links_asset(
    context,
    clickhouse: ClickHouseResource,
) -> MaterializeResult:
    client = clickhouse.client()
    counts = materialize_geo_entity_links(clickhouse=client)
    context.log.info("geo_entity_links materialised: %s", counts)
    return MaterializeResult(metadata={"stage": "geography", **counts})


@asset(
    name="offplan_reelly_project_links",
    group_name=_GEOGRAPHY_GROUP,
    deps=["geo_source_signatures", "reelly_supply_bronze"],
    description=(
        "Auditable links from every off-plan DLD/DXBI signature to the Dubai Reelly "
        "project catalogue, retaining unresolved and review candidates."
    ),
)
def offplan_reelly_project_links_asset(
    context,
    clickhouse: ClickHouseResource,
) -> MaterializeResult:
    client = clickhouse.client()
    counts = materialize_offplan_reelly_project_links(clickhouse=client)
    context.log.info("offplan_reelly_project_links materialised: %s", counts)
    return MaterializeResult(metadata={"stage": "geography", **counts})


def materialize_geo_location_nodes(
    *, clickhouse: ClickHouseClient, ensure_tables: bool = True
) -> dict[str, Any]:
    if ensure_tables:
        ensure_schema(clickhouse=clickhouse)
    result = clickhouse.query(
        """
        SELECT
            location_id,
            parent_location_id,
            run_id,
            scraped_at,
            location_type,
            level,
            name,
            path_name,
            path_ids_json,
            lat,
            lng,
            published
        FROM pf_locations_bronze
        WHERE is_dubai = 1
        ORDER BY location_id
        """
    )
    rows: list[tuple[Any, ...]] = []
    invalid_coordinates = 0
    snapshot_ids: set[str] = set()
    for row in result.result_rows:
        (
            location_id,
            parent_location_id,
            snapshot_id,
            scraped_at,
            location_type,
            level,
            name,
            path_name,
            path_ids_json,
            latitude,
            longitude,
            published,
        ) = row
        snapshot_ids.add(str(snapshot_id))
        coordinate_status = "valid"
        if not _valid_dubai_coordinate(latitude, longitude):
            latitude = longitude = None
            coordinate_status = "missing" if row[9] is None or row[10] is None else "outside_dubai"
            invalid_coordinates += 1
        rows.append(
            (
                f"pf:{location_id}",
                str(location_id),
                f"pf:{parent_location_id}" if parent_location_id else None,
                str(snapshot_id),
                _parse_datetime(scraped_at),
                str(location_type),
                int(level),
                str(name),
                normalize_location_name(str(name)),
                str(path_name),
                str(path_ids_json),
                latitude,
                longitude,
                coordinate_status,
                int(published),
            )
        )
    if len(snapshot_ids) != 1:
        raise ValueError(f"Expected exactly one PF snapshot, found {sorted(snapshot_ids)}")
    clickhouse.replace_table_rows(
        table="geo_location_nodes",
        rows=rows,
        column_names=_NODE_COLUMNS,
        staging_suffix="pf_current",
    )
    return {
        "table": "geo_location_nodes",
        "row_count": len(rows),
        "pf_snapshot_id": next(iter(snapshot_ids)),
        "invalid_coordinate_count": invalid_coordinates,
    }


def materialize_geo_location_closure(*, clickhouse: ClickHouseClient) -> int:
    result = clickhouse.query(
        "SELECT canonical_location_id, path_ids_json, snapshot_id FROM geo_location_nodes"
    )
    rows: list[tuple[str, str, int, str]] = []
    for descendant_id, path_ids_json, snapshot_id in result.result_rows:
        path_ids = json.loads(path_ids_json)
        if not isinstance(path_ids, list) or not path_ids:
            raise ValueError(f"Invalid PF path for {descendant_id}: {path_ids_json}")
        canonical_path = [f"pf:{source_id}" for source_id in path_ids]
        if canonical_path[-1] != descendant_id:
            raise ValueError(f"PF path does not terminate at {descendant_id}: {canonical_path}")
        for index, ancestor_id in enumerate(canonical_path):
            rows.append((ancestor_id, descendant_id, len(canonical_path) - index - 1, snapshot_id))
    clickhouse.replace_table_rows(
        table="geo_location_closure",
        rows=rows,
        column_names=_CLOSURE_COLUMNS,
        staging_suffix="pf_current",
    )
    return len(rows)


def materialize_geo_source_signatures(*, clickhouse: ClickHouseClient) -> dict[str, Any]:
    alias_count = materialize_geo_tower_aliases(clickhouse=clickhouse)
    snapshot_id = _single_value(clickhouse, "SELECT any(snapshot_id) FROM geo_location_nodes")
    aggregated_rows: dict[str, list[tuple[Any, ...]]] = {}
    for source_system, sql in _signature_queries().items():
        aggregated_rows[source_system] = sorted(
            clickhouse.query(sql).result_rows,
            key=lambda row: tuple(str(value) for value in row),
        )
    build_id = _crosswalk_build_id(
        snapshot_id=snapshot_id,
        aggregated_rows=aggregated_rows,
    )
    rows: list[tuple[Any, ...]] = []
    counts: dict[str, int] = {}
    for source_system, source_rows in aggregated_rows.items():
        counts[source_system] = len(source_rows)
        for row in source_rows:
            (
                source_identity,
                source_grain,
                property_type,
                market_status,
                source_entity_class,
                area_name,
                master_project_name,
                project_name,
                building_name,
                row_count,
                represented_value,
                first_observed,
                last_observed,
            ) = row
            source_key = hashlib.sha256(f"{source_system}|{source_identity}".encode()).hexdigest()
            rows.append(
                (
                    source_system,
                    source_key,
                    source_grain,
                    property_type,
                    market_status,
                    source_entity_class,
                    area_name,
                    master_project_name,
                    project_name,
                    building_name,
                    normalize_location_name(area_name),
                    normalize_location_name(master_project_name),
                    normalize_location_name(project_name),
                    normalize_location_name(building_name),
                    int(row_count),
                    int(represented_value),
                    first_observed,
                    last_observed,
                    NORMALIZATION_VERSION,
                    build_id,
                )
            )
    clickhouse.replace_table_rows(
        table="geo_source_signatures",
        rows=rows,
        column_names=_SIGNATURE_COLUMNS,
        staging_suffix="current",
    )
    return {
        "table": "geo_source_signatures",
        "row_count": len(rows),
        "build_id": build_id,
        "tower_alias_count": alias_count,
        **{f"{source}_signature_count": count for source, count in counts.items()},
    }


def materialize_geo_entity_links(*, clickhouse: ClickHouseClient) -> dict[str, Any]:
    nodes = _load_nodes(clickhouse)
    nodes_by_id = {node.canonical_location_id: node for node in nodes}
    tower_aliases = _load_tower_aliases(clickhouse)
    authoritative_tower_aliases = _load_authoritative_tower_aliases(clickhouse)
    alias_count = sum(len(values) for values in tower_aliases.values())
    resolver = GeographyResolver(
        nodes,
        tower_aliases=tower_aliases,
        authoritative_tower_aliases=authoritative_tower_aliases,
    )
    overrides = _load_overrides(clickhouse)
    result = clickhouse.query(
        """
        SELECT
            source_system,
            source_key,
            source_grain,
            property_type,
            market_status,
            source_entity_class,
            raw_area_name,
            raw_master_project_name,
            raw_project_name,
            raw_building_name,
            build_id
        FROM geo_source_signatures
        ORDER BY source_system, source_key
        """
    )
    snapshot_id = _single_value(clickhouse, "SELECT any(snapshot_id) FROM geo_location_nodes")
    rows: list[tuple[Any, ...]] = []
    status_counts: dict[str, int] = {}
    seen_source_keys: set[tuple[str, str]] = set()
    for row in result.result_rows:
        signature = SourceSignature(
            source_system=row[0],
            source_key=row[1],
            source_grain=row[2],
            property_type=row[3],
            market_status=row[4],
            source_entity_class=row[5],
            area_name=row[6],
            master_project_name=row[7],
            project_name=row[8],
            building_name=row[9],
        )
        source_identity = (signature.source_system, signature.source_key)
        seen_source_keys.add(source_identity)
        override = overrides.get(source_identity)
        decision = (
            decision_from_override(override, nodes_by_id)
            if override is not None
            else resolver.resolve(signature)
        )
        status_counts[decision.status] = status_counts.get(decision.status, 0) + 1
        rows.append(
            (
                signature.source_system,
                signature.source_key,
                decision.canonical_location_id,
                decision.target_grain,
                decision.relation,
                decision.status,
                decision.match_method,
                decision.confidence,
                decision.candidate_count,
                decision.evidence_json(),
                NORMALIZATION_VERSION,
                snapshot_id,
                row[10],
            )
        )
    candidate_rows = _candidate_rows(rows)
    clickhouse.replace_table_rows(
        table="geo_entity_links",
        rows=rows,
        column_names=_LINK_COLUMNS,
        staging_suffix="current",
    )
    clickhouse.replace_table_rows(
        table="geo_entity_link_candidates",
        rows=candidate_rows,
        column_names=_CANDIDATE_COLUMNS,
        staging_suffix="current",
    )
    return {
        "table": "geo_entity_links",
        "row_count": len(rows),
        "active_override_count": len(overrides),
        "stale_override_count": len(set(overrides) - seen_source_keys),
        "tower_alias_count": alias_count,
        "candidate_count": len(candidate_rows),
        **{f"{status}_count": count for status, count in status_counts.items()},
    }


def materialize_offplan_reelly_project_links(
    *, clickhouse: ClickHouseClient, ensure_tables: bool = True
) -> dict[str, Any]:
    """Classify every off-plan source signature against the Dubai Reelly catalogue."""
    if ensure_tables:
        ensure_schema(clickhouse=clickhouse)
    projects = _load_reelly_projects(clickhouse)
    projects_by_id = {project.project_id: project for project in projects}
    catalog_build_id = _reelly_catalog_build_id(projects)
    resolver = OffplanProjectResolver(projects)
    overrides = _load_offplan_project_overrides(clickhouse)
    signatures = _load_offplan_signatures(clickhouse)
    signature_by_identity = {
        (signature.source_system, signature.source_key): signature for signature in signatures
    }

    decisions: dict[tuple[str, str], OffplanProjectDecision] = {}
    for signature in signatures:
        source_identity = (signature.source_system, signature.source_key)
        override = overrides.get(source_identity)
        decisions[source_identity] = (
            decision_from_offplan_override(override, projects_by_id)
            if override is not None
            else resolver.resolve(signature)
        )

    consensus = _offplan_transaction_consensus(
        clickhouse=clickhouse,
        signatures=signatures,
        decisions=decisions,
    )
    for source_identity, candidate in consensus.items():
        target_id, matched_sales, all_matched_sales = candidate
        signature = signature_by_identity[source_identity]
        decisions[source_identity] = transaction_consensus_decision(
            current=decisions[source_identity],
            project=projects_by_id[target_id],
            matched_sales=matched_sales,
            all_matched_sales=all_matched_sales,
            total_source_events=signature.row_count,
            name_compatible=transaction_name_compatible(signature, projects_by_id[target_id]),
        )

    rows: list[tuple[Any, ...]] = []
    status_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}
    for source_identity in sorted(decisions):
        decision = decisions[source_identity]
        signature = signature_by_identity[source_identity]
        status_counts[decision.status] = status_counts.get(decision.status, 0) + 1
        event_counts[decision.status] = event_counts.get(decision.status, 0) + signature.row_count
        rows.append(
            (
                signature.source_system,
                signature.source_key,
                decision.reelly_project_id,
                decision.relation,
                decision.status,
                decision.match_method,
                decision.confidence,
                decision.candidate_count,
                decision.evidence_json(),
                OFFPLAN_MATCH_VERSION,
                catalog_build_id,
                signature.source_build_id,
            )
        )

    candidate_rows = _offplan_candidate_rows(rows)
    clickhouse.replace_table_rows(
        table="offplan_reelly_project_links",
        rows=rows,
        column_names=_OFFPLAN_LINK_COLUMNS,
        staging_suffix="current",
    )
    clickhouse.replace_table_rows(
        table="offplan_reelly_project_link_candidates",
        rows=candidate_rows,
        column_names=_OFFPLAN_CANDIDATE_COLUMNS,
        staging_suffix="current",
    )
    active_sources = {(signature.source_system, signature.source_key) for signature in signatures}
    return {
        "table": "offplan_reelly_project_links",
        "row_count": len(rows),
        "represented_event_count": sum(signature.row_count for signature in signatures),
        "catalog_project_count": len(projects),
        "catalog_build_id": catalog_build_id,
        "candidate_count": len(candidate_rows),
        "transaction_consensus_count": sum(
            decision.match_method == "dld_transaction_consensus" for decision in decisions.values()
        ),
        "active_override_count": len(overrides),
        "stale_override_count": len(set(overrides) - active_sources),
        **{f"{status}_count": count for status, count in status_counts.items()},
        **{f"{status}_event_count": count for status, count in event_counts.items()},
    }


def _load_reelly_projects(clickhouse: ClickHouseClient) -> list[ReellyProject]:
    result = clickhouse.query(
        """
        SELECT
            project_id,
            project_key,
            project_name,
            area_name,
            developer_name,
            latitude,
            longitude
        FROM silver_reelly_projects FINAL
        WHERE lowerUTF8(trim(region)) = 'dubai'
          AND project_id != ''
          AND project_name != ''
          AND latitude BETWEEN 24 AND 26
          AND longitude BETWEEN 54 AND 57
        ORDER BY project_id
        """
    )
    projects = [
        ReellyProject(
            project_id=str(row[0]),
            project_key=str(row[1]),
            project_name=str(row[2]),
            area_name=str(row[3]),
            developer_name=str(row[4]),
            latitude=float(row[5]) if row[5] is not None else None,
            longitude=float(row[6]) if row[6] is not None else None,
        )
        for row in result.result_rows
    ]
    if not projects:
        raise ValueError("Reelly Dubai catalogue is empty; refusing to replace off-plan links")
    return projects


def _load_offplan_signatures(clickhouse: ClickHouseClient) -> list[OffplanSignature]:
    result = clickhouse.query(
        """
        SELECT
            source_system,
            source_key,
            raw_area_name,
            raw_master_project_name,
            raw_project_name,
            raw_building_name,
            property_type,
            row_count,
            build_id
        FROM geo_source_signatures
        WHERE market_status = 'Offplan'
          AND source_system IN ('dld_transactions', 'dxbi_sales')
        ORDER BY source_system, source_key
        """
    )
    return [
        OffplanSignature(
            source_system=str(row[0]),
            source_key=str(row[1]),
            area_name=str(row[2]),
            master_project_name=str(row[3]),
            project_name=str(row[4]),
            building_name=str(row[5]),
            property_type=str(row[6]),
            row_count=int(row[7]),
            source_build_id=str(row[8]),
        )
        for row in result.result_rows
    ]


def _load_offplan_project_overrides(
    clickhouse: ClickHouseClient,
) -> dict[tuple[str, str], OffplanProjectOverride]:
    result = clickhouse.query(
        """
        SELECT
            source_system,
            source_key,
            reelly_project_id,
            decision,
            relation,
            review_note,
            reviewed_by
        FROM offplan_reelly_project_link_overrides FINAL
        WHERE active = 1
        """
    )
    return {
        (str(row[0]), str(row[1])): OffplanProjectOverride(
            reelly_project_id=str(row[2]) if row[2] is not None else None,
            decision=row[3],
            relation=str(row[4]),
            review_note=str(row[5]),
            reviewed_by=str(row[6]),
        )
        for row in result.result_rows
    }


def _reelly_catalog_build_id(projects: list[ReellyProject]) -> str:
    payload = [
        (
            project.project_id,
            project.project_key,
            project.project_name,
            project.area_name,
            project.developer_name,
            project.latitude,
            project.longitude,
        )
        for project in projects
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def _offplan_transaction_consensus(
    *,
    clickhouse: ClickHouseClient,
    signatures: list[OffplanSignature],
    decisions: dict[tuple[str, str], OffplanProjectDecision],
) -> dict[tuple[str, str], tuple[str, int, int]]:
    """Use exact date/value/area DLD pairs to corroborate DXBI catalogue identity."""
    dxbi_by_raw = {
        (
            signature.area_name,
            signature.project_name,
            signature.building_name,
            signature.property_type,
        ): (signature.source_system, signature.source_key)
        for signature in signatures
        if signature.source_system == "dxbi_sales"
    }
    dld_targets_by_raw: dict[tuple[str, str, str, str, str], set[str]] = {}
    for signature in signatures:
        if signature.source_system != "dld_transactions":
            continue
        decision = decisions[(signature.source_system, signature.source_key)]
        if decision.status not in {"auto_approved", "manual_approved"}:
            continue
        if decision.reelly_project_id is None:
            continue
        raw_key = (
            signature.area_name,
            signature.master_project_name,
            signature.project_name,
            signature.building_name,
            signature.property_type,
        )
        dld_targets_by_raw.setdefault(raw_key, set()).add(decision.reelly_project_id)

    pair_rows = clickhouse.query(
        """
        SELECT
            e.area_name,
            e.project_name,
            e.building_name,
            e.property_type,
            d.area_en,
            d.master_project_en,
            d.project_en,
            d.building_name_en,
            d.prop_type_en,
            uniqExact(e.sale_key) AS matched_sales
        FROM dxbi_sales_unit_events AS e FINAL
        INNER JOIN dld_od_transactions_bronze AS d
            ON toDate(d.instance_date) = e.transaction_date
           AND d.trans_value = toInt64(e.sale_amount_aed)
           AND abs(d.procedure_area * 10.7639 - e.size_sqft) < 2
        WHERE e.market_status = 'Offplan'
          AND d.is_offplan = 1
        GROUP BY
            e.area_name,
            e.project_name,
            e.building_name,
            e.property_type,
            d.area_en,
            d.master_project_en,
            d.project_en,
            d.building_name_en,
            d.prop_type_en
        SETTINGS allow_experimental_join_condition = 1
        """
    ).result_rows
    target_counts: dict[tuple[str, str], dict[str, int]] = {}
    for row in pair_rows:
        source_identity = dxbi_by_raw.get(tuple(str(value) for value in row[:4]))
        target_ids = dld_targets_by_raw.get(tuple(str(value) for value in row[4:9]), set())
        if source_identity is None or len(target_ids) != 1:
            continue
        target_id = next(iter(target_ids))
        counts = target_counts.setdefault(source_identity, {})
        counts[target_id] = counts.get(target_id, 0) + int(row[9])

    consensus: dict[tuple[str, str], tuple[str, int, int]] = {}
    for source_identity, counts in target_counts.items():
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        target_id, matched_sales = ranked[0]
        consensus[source_identity] = (
            target_id,
            matched_sales,
            sum(count for _, count in ranked),
        )
    return consensus


def _offplan_candidate_rows(
    link_rows: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for link in link_rows:
        evidence = json.loads(link[8])
        candidates = evidence.get("ranked_candidates", [])
        if not isinstance(candidates, list):
            continue
        for rank, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict) or not candidate.get("reelly_project_id"):
                continue
            rows.append(
                (
                    link[0],
                    link[1],
                    rank,
                    candidate["reelly_project_id"],
                    candidate.get("project_name", ""),
                    candidate.get("area_name", ""),
                    int(candidate.get("score", 0)),
                    int(bool(candidate.get("context_supported"))),
                    int(bool(candidate.get("identity_compatible"))),
                    candidate.get("method", ""),
                    candidate.get("relation", ""),
                    candidate.get("source_field", ""),
                    candidate.get("source_variant", ""),
                    candidate.get("target_variant", ""),
                    link[10],
                    link[11],
                )
            )
    return rows


def _load_overrides(
    clickhouse: ClickHouseClient,
) -> dict[tuple[str, str], LinkOverride]:
    result = clickhouse.query(
        """
        SELECT
            source_system,
            source_key,
            canonical_location_id,
            decision,
            relation,
            review_note,
            reviewed_by
        FROM geo_entity_link_overrides FINAL
        WHERE active = 1
        """
    )
    return {
        (row[0], row[1]): LinkOverride(
            canonical_location_id=row[2],
            decision=row[3],
            relation=row[4],
            review_note=row[5],
            reviewed_by=row[6],
        )
        for row in result.result_rows
    }


def materialize_geo_tower_aliases(*, clickhouse: ClickHouseClient) -> int:
    """Preserve approved aliases and learn only from already approved exact links."""
    preserved_rows = clickhouse.query(
        """
        SELECT
            canonical_location_id,
            alias_name,
            normalized_alias,
            source_system,
            evidence_json,
            status,
            reviewed_by,
            reviewed_at,
            active
        FROM geo_tower_aliases FINAL
        WHERE active = 1
          AND status IN (
            'generated_approved',
            'manual_approved'
          )
        """
    ).result_rows
    generated = clickhouse.query(
        """
        SELECT
            canonical_location_id,
            raw_building_name,
            source_system,
            any(evidence_json) AS evidence_json
        FROM geo_mapped_source_facts
        WHERE target_grain = 'tower'
          AND match_status IN ('auto_approved', 'manual_approved')
          AND raw_building_name != ''
          AND (
            startsWith(match_method, 'exact_')
            OR startsWith(match_method, 'structural_')
            OR match_method = 'manual_override'
          )
        GROUP BY canonical_location_id, raw_building_name, source_system
        """
    ).result_rows
    rows = [tuple(row) for row in preserved_rows]
    preserved_keys = {(row[0], row[2], row[3]) for row in rows}
    for canonical_location_id, alias_name, source_system, evidence_json in generated:
        normalized_alias = normalize_location_name(alias_name)
        key = (canonical_location_id, normalized_alias, source_system)
        if not normalized_alias or key in preserved_keys:
            continue
        rows.append(
            (
                canonical_location_id,
                alias_name,
                normalized_alias,
                source_system,
                evidence_json,
                "generated_approved",
                "",
                None,
                1,
            )
        )
        preserved_keys.add(key)
    for (
        canonical_location_id,
        alias_name,
        canonical_name,
        matched_sales,
        all_matched,
        total_events,
    ) in _transaction_consensus_aliases(clickhouse):
        normalized_alias = normalize_location_name(alias_name)
        key = (canonical_location_id, normalized_alias, "dld_transaction_consensus")
        if key in preserved_keys:
            continue
        rows.append(
            (
                canonical_location_id,
                alias_name,
                normalized_alias,
                "dld_transaction_consensus",
                json.dumps(
                    {
                        "all_matched_sales": all_matched,
                        "canonical_name": canonical_name,
                        "matched_sales": matched_sales,
                        "total_dxbi_events": total_events,
                    },
                    sort_keys=True,
                ),
                "generated_transaction_consensus",
                "system:dld-transaction-consensus",
                None,
                1,
            )
        )
        preserved_keys.add(key)
    current_node_ids = {
        str(row[0])
        for row in clickhouse.query(
            "SELECT canonical_location_id FROM geo_location_nodes"
        ).result_rows
    }
    missing_targets = sorted(
        canonical_location_id
        for canonical_location_id, _, _ in _CURATED_TOWER_ALIASES
        if canonical_location_id not in current_node_ids
    )
    if missing_targets:
        raise ValueError(f"Curated tower alias targets are stale: {missing_targets}")
    for canonical_location_id, alias_name, review_note in _CURATED_TOWER_ALIASES:
        normalized_alias = normalize_location_name(alias_name)
        key = (canonical_location_id, normalized_alias, "curated_dxbi")
        if key in preserved_keys:
            continue
        rows.append(
            (
                canonical_location_id,
                alias_name,
                normalized_alias,
                "curated_dxbi",
                json.dumps({"review_note": review_note}, sort_keys=True),
                "manual_approved",
                "system:curated-crosswalk",
                datetime(2026, 8, 31, tzinfo=UTC),
                1,
            )
        )
        preserved_keys.add(key)
    clickhouse.replace_table_rows(
        table="geo_tower_aliases",
        rows=rows,
        column_names=_ALIAS_COLUMNS,
        staging_suffix="current",
    )
    return len(rows)


def _load_tower_aliases(clickhouse: ClickHouseClient) -> dict[str, tuple[str, ...]]:
    result = clickhouse.query(
        """
        SELECT canonical_location_id, groupUniqArray(alias_name)
        FROM geo_tower_aliases FINAL
        WHERE active = 1
          AND status IN (
            'generated_approved',
            'generated_transaction_consensus',
            'manual_approved'
          )
        GROUP BY canonical_location_id
        """
    )
    return {str(row[0]): tuple(str(value) for value in row[1]) for row in result.result_rows}


def _load_authoritative_tower_aliases(
    clickhouse: ClickHouseClient,
) -> dict[tuple[str, str], tuple[str, ...]]:
    """Load DXBI aliases backed by review or 99% independent DLD consensus."""
    result = clickhouse.query(
        """
        SELECT
            normalized_alias,
            groupUniqArray(canonical_location_id) AS canonical_location_ids
        FROM geo_tower_aliases FINAL
        WHERE active = 1
          AND (
            status = 'generated_transaction_consensus'
            OR (status = 'manual_approved' AND source_system = 'curated_dxbi')
          )
        GROUP BY normalized_alias
        """
    )
    return {
        ("dxbi_sales", str(row[0])): tuple(str(value) for value in row[1])
        for row in result.result_rows
    }


def _transaction_consensus_aliases(
    clickhouse: ClickHouseClient,
) -> list[tuple[str, str, str, int, int, int]]:
    """Learn aliases only when independent DLD transactions identify one PF tower."""
    pair_rows = clickhouse.query(
        """
        SELECT
            e.building_name AS alias_name,
            dgm.canonical_location_id,
            any(dgm.canonical_location_name) AS canonical_name,
            uniqExact(e.sale_key) AS matched_sales
        FROM dxbi_sales_unit_events AS e FINAL
        INNER JOIN dld_od_transactions_bronze AS d
            ON toDate(d.instance_date) = e.transaction_date
           AND d.trans_value = toInt64(e.sale_amount_aed)
        INNER JOIN geo_mapped_source_facts AS dgm
            ON dgm.source_system = 'dld_transactions'
           AND dgm.raw_area_name = d.area_en
           AND dgm.raw_master_project_name = d.master_project_en
           AND dgm.raw_project_name = d.project_en
           AND dgm.raw_building_name = d.building_name_en
           AND dgm.property_type = d.prop_type_en
           AND dgm.market_status = if(d.is_offplan = 1, 'Offplan', 'Ready')
        WHERE e.property_type = 'Apartment'
          AND e.market_status = 'Ready'
          AND e.building_name != ''
          AND dgm.target_grain = 'tower'
          AND dgm.match_status IN ('auto_approved', 'manual_approved')
          AND abs(d.procedure_area * 10.7639 - e.size_sqft) < 2
        GROUP BY alias_name, dgm.canonical_location_id
        """
    ).result_rows
    event_rows = clickhouse.query(
        """
        SELECT
            building_name,
            count() AS total_events,
            uniqExact((area_name, project_name)) AS context_count
        FROM dxbi_sales_unit_events FINAL
        WHERE property_type = 'Apartment'
          AND market_status = 'Ready'
          AND building_name != ''
        GROUP BY building_name
        """
    ).result_rows
    event_totals = {
        str(alias_name): (int(total_events), int(context_count))
        for alias_name, total_events, context_count in event_rows
    }
    by_alias: dict[str, list[tuple[str, str, int]]] = {}
    for alias_name, canonical_location_id, canonical_name, matched_sales in pair_rows:
        by_alias.setdefault(str(alias_name), []).append(
            (str(canonical_location_id), str(canonical_name), int(matched_sales))
        )

    aliases: list[tuple[str, str, str, int, int, int]] = []
    for alias_name, candidates in by_alias.items():
        total_events, context_count = event_totals.get(alias_name, (0, 0))
        if not total_events or context_count != 1:
            continue
        ranked = sorted(candidates, key=lambda item: (-item[2], item[0]))
        canonical_location_id, canonical_name, matched_sales = ranked[0]
        all_matched = sum(candidate[2] for candidate in ranked)
        if (
            matched_sales < 20
            or matched_sales / all_matched < 0.99
            or matched_sales / total_events < 0.20
        ):
            continue
        aliases.append(
            (
                canonical_location_id,
                alias_name,
                canonical_name,
                matched_sales,
                all_matched,
                total_events,
            )
        )
    return aliases


def _candidate_rows(link_rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for link in link_rows:
        evidence = json.loads(link[9])
        candidates = evidence.get("ranked_candidates", [])
        if not isinstance(candidates, list):
            continue
        for rank, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict) or not candidate.get("canonical_location_id"):
                continue
            rows.append(
                (
                    link[0],
                    link[1],
                    rank,
                    candidate["canonical_location_id"],
                    candidate.get("target_name", ""),
                    int(candidate.get("score", 0)),
                    int(bool(candidate.get("context_supported"))),
                    int(bool(candidate.get("identity_compatible"))),
                    candidate.get("method", ""),
                    candidate.get("source_variant", ""),
                    candidate.get("target_variant", ""),
                    link[12],
                )
            )
    return rows


def _load_nodes(clickhouse: ClickHouseClient) -> list[LocationNode]:
    result = clickhouse.query(
        """
        SELECT
            canonical_location_id,
            source_location_id,
            parent_canonical_location_id,
            location_type,
            name,
            normalized_name,
            path_ids_json
        FROM geo_location_nodes
        """
    )
    return [
        LocationNode(
            canonical_location_id=row[0],
            source_location_id=row[1],
            parent_canonical_location_id=row[2],
            location_type=row[3],
            name=row[4],
            normalized_name=row[5],
            path_ids=tuple(json.loads(row[6])),
        )
        for row in result.result_rows
    ]


def _signature_queries() -> dict[str, str]:
    return {
        "dld_transactions": """
            SELECT
                concat(toString(area_id), '|', project_number, '|', area_en, '|',
                    master_project_en, '|', project_en, '|', building_name_en, '|',
                    property_type, '|', market_status, '|', source_entity_class, '|',
                    source_grain) AS source_identity,
                multiIf(source_entity_class = 'landed_phase', 'landed_phase',
                    source_entity_class = 'offplan_project', 'project',
                    building_name_en != '', 'building', project_en != '', 'project',
                    master_project_en != '', 'master_project', 'area') AS source_grain,
                property_type,
                market_status,
                source_entity_class,
                area_en,
                master_project_en,
                project_en,
                building_name_en,
                count() AS row_count,
                sum(trans_value) AS represented_value,
                min(toDate(instance_date)) AS first_observed,
                max(toDate(instance_date)) AS last_observed
            FROM (
                SELECT *,
                    prop_type_en AS property_type,
                    if(is_offplan = 1, 'Offplan', 'Ready') AS market_status,
                    multiIf(is_offplan = 1, 'offplan_project',
                        prop_type_en IN ('Villa', 'Townhouse'), 'landed_phase',
                        building_name_en != '', 'physical_tower',
                        project_en != '', 'project', 'area') AS source_entity_class
                FROM dld_od_transactions_bronze
            )
            GROUP BY area_id, project_number, area_en, master_project_en, project_en,
                building_name_en, property_type, market_status, source_entity_class, source_grain
        """,
        "dxbi_sales": """
            SELECT
                concat(area_name, '|', project_name, '|', building_name, '|', property_type,
                    '|', market_status, '|', source_entity_class, '|', source_grain)
                    AS source_identity,
                multiIf(source_entity_class = 'landed_phase', 'landed_phase',
                    source_entity_class = 'offplan_project', 'project',
                    building_name != '', 'building', project_name != '', 'project', 'area')
                    AS source_grain,
                property_type,
                market_status,
                source_entity_class,
                area_name,
                '' AS master_project_name,
                project_name,
                building_name,
                count() AS row_count,
                sum(toInt64(sale_amount_aed)) AS represented_value,
                min(transaction_date) AS first_observed,
                max(transaction_date) AS last_observed
            FROM (
                SELECT *,
                    multiIf(lowerUTF8(market_status) = 'offplan', 'offplan_project',
                        property_type IN ('Villa', 'Townhouse'), 'landed_phase',
                        building_name != '', 'physical_tower',
                        project_name != '', 'project', 'area') AS source_entity_class
                FROM dxbi_sales_unit_events FINAL
            )
            GROUP BY area_name, project_name, building_name, property_type, market_status,
                source_entity_class, source_grain
        """,
        "dxbi_rentals": """
            SELECT
                concat(area_name, '|', project_name, '|', building_name, '|', property_type,
                    '|', source_entity_class, '|', source_grain) AS source_identity,
                multiIf(source_entity_class = 'landed_phase', 'landed_phase',
                    building_name != '', 'building', project_name != '', 'project', 'area')
                    AS source_grain,
                property_type,
                '' AS market_status,
                source_entity_class,
                area_name,
                '' AS master_project_name,
                project_name,
                building_name,
                count() AS row_count,
                sum(toInt64(annual_rent_aed)) AS represented_value,
                min(lease_start) AS first_observed,
                max(lease_end) AS last_observed
            FROM (
                SELECT *,
                    multiIf(property_type IN ('Villa', 'Townhouse'), 'landed_phase',
                        building_name != '', 'physical_tower',
                        project_name != '', 'project', 'area') AS source_entity_class
                FROM dxbi_rental_events FINAL
            )
            GROUP BY area_name, project_name, building_name, property_type,
                source_entity_class, source_grain
        """,
    }


def _crosswalk_build_id(
    *,
    snapshot_id: str,
    aggregated_rows: dict[str, list[tuple[Any, ...]]],
) -> str:
    source_digest = hashlib.sha256()
    for source_system in sorted(aggregated_rows):
        source_digest.update(source_system.encode())
        for row in aggregated_rows[source_system]:
            source_digest.update(json.dumps(row, default=str, separators=(",", ":")).encode())
    digest = hashlib.sha256(
        f"{snapshot_id}|{NORMALIZATION_VERSION}|{source_digest.hexdigest()}".encode()
    ).hexdigest()[:16]
    return f"geo-{digest}"


def _single_value(clickhouse: ClickHouseClient, sql: str) -> str:
    value = clickhouse.query(sql).result_rows[0][0]
    if value in (None, ""):
        raise ValueError(f"Expected a non-empty scalar for geography query: {sql}")
    return str(value)


def _valid_dubai_coordinate(latitude: Any, longitude: Any) -> bool:
    if latitude is None or longitude is None:
        return False
    south, north, west, east = _DUBAI_BOUNDS
    return south <= float(latitude) <= north and west <= float(longitude) <= east


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(UTC)
