from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dagster import Failure
from pydantic import BaseModel, ConfigDict

from holocron.contracts import RawRelease
from holocron.platform.checkpoints import read_checkpoint_model, write_checkpoint
from holocron.platform.execution import utc_now
from holocron.pydantic_helpers import CsvTuple
from holocron.sources.pf_listings.source import PF_LISTINGS_SOURCE_NAME

PF_LISTINGS_PLAN_OPERATION = "plan_snapshot"
PF_LISTINGS_SEARCH_OPERATION = "search_chunk"
PF_LISTINGS_DETAIL_OPERATION = "detail_chunk"
PF_LISTINGS_MANUAL_SNAPSHOT_DEFAULTS = {
    "mode": "snapshot",
    "max_planned_queries": 12000,
    "max_search_pages_per_run": 50000,
    "max_details_per_run": 100000,
    "fetch_details": True,
    "split_by_location": True,
}
PF_LISTINGS_PLAN_DEFAULTS = {
    "mode": "plan",
    "max_planned_queries": 25000,
    "max_plan_queries_per_run": 500,
    "max_results_per_query": 750,
    "max_partition_depth": 10,
    "split_by_location": True,
}
PF_LISTINGS_SEARCH_CHUNK_DEFAULTS = {
    "mode": "search",
    "max_search_pages_per_run": 500,
    "fetch_details": False,
}
PF_LISTINGS_DETAIL_CHUNK_DEFAULTS = {
    "mode": "details",
    "max_details_per_run": 1000,
    "fetch_details": True,
}
PF_LISTINGS_LATEST_DELTA_DEFAULTS = {
    "mode": "latest_delta",
    "max_pages_per_query": 5,
    "max_search_pages_per_run": 40,
    "fetch_details": True,
    "max_details_per_run": 250,
    "latest_delta_stop_after_seen_pages": 2,
    "latest_delta_bootstrap_details": False,
    "latest_delta_detail_audit_limit": 0,
}


class _CheckpointModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _PfPlanCheckpoint(_CheckpointModel):
    completed: bool = False
    last_manifest_s3_key: str = ""
    plan_manifest_s3_keys: CsvTuple = ()

    @property
    def manifest_keys(self) -> list[str]:
        keys = [key for key in self.plan_manifest_s3_keys if key]
        fallback = self.last_manifest_s3_key.strip()
        if not keys and fallback:
            keys.append(fallback)
        return keys


class _PfSearchCheckpoint(_CheckpointModel):
    completed: bool = False
    next_query_index: int = 0
    next_page: int = 1
    plan_manifest_s3_key: str = ""
    plan_manifest_s3_keys: CsvTuple = ()

    def matches_plan(self, plan_manifest_keys: list[str]) -> bool:
        if "plan_manifest_s3_keys" in self.model_fields_set:
            return list(self.plan_manifest_s3_keys) == plan_manifest_keys
        return self.plan_manifest_s3_key == plan_manifest_keys[-1]


class _PfDetailCheckpoint(_CheckpointModel):
    next_manifest_index: int = 0
    next_row_index: int = 0


def resolve_listings_config(
    *,
    source_config: Mapping[str, Any],
    object_storage_client: Any,
) -> dict[str, Any]:
    resolved_config = dict(source_config)
    reset_checkpoint = bool(resolved_config.pop("reset_checkpoint", False))
    mode = str(resolved_config.get("mode") or "snapshot")

    if mode == "plan":
        checkpoint = read_checkpoint_model(
            object_storage_client,
            source=PF_LISTINGS_SOURCE_NAME,
            operation=PF_LISTINGS_PLAN_OPERATION,
            model=_PfPlanCheckpoint,
        )
        if checkpoint and checkpoint.completed and not reset_checkpoint:
            raise Failure(
                description=(
                    "Property Finder plan checkpoint is already completed. "
                    "Run search chunks, or pass reset_checkpoint=true to create a new plan."
                ),
                metadata={
                    "source": PF_LISTINGS_SOURCE_NAME,
                    "operation": PF_LISTINGS_PLAN_OPERATION,
                },
            )
        if checkpoint and not reset_checkpoint:
            resolved_config["plan_state_manifest_s3_key"] = checkpoint.last_manifest_s3_key
            resolved_config["plan_manifest_s3_keys"] = checkpoint.manifest_keys
        return resolved_config

    if mode == "search":
        plan_manifest_keys = _coerce_manifest_keys(resolved_config.get("plan_manifest_s3_keys", ()))
        plan_manifest_key = str(resolved_config.get("plan_manifest_s3_key") or "").strip()
        if plan_manifest_key:
            plan_manifest_keys.append(plan_manifest_key)
        if not plan_manifest_keys:
            plan_checkpoint = read_checkpoint_model(
                object_storage_client,
                source=PF_LISTINGS_SOURCE_NAME,
                operation=PF_LISTINGS_PLAN_OPERATION,
                model=_PfPlanCheckpoint,
            )
            if not plan_checkpoint or not plan_checkpoint.completed:
                raise Failure(
                    description=(
                        "Property Finder search chunks require a completed planning checkpoint. "
                        "Run pf_listings_plan_snapshot until it completes, or pass plan manifests."
                    ),
                    metadata={
                        "source": PF_LISTINGS_SOURCE_NAME,
                        "operation": PF_LISTINGS_SEARCH_OPERATION,
                    },
                )
            plan_manifest_keys.extend(plan_checkpoint.manifest_keys)
        plan_manifest_keys = list(dict.fromkeys(plan_manifest_keys))
        if not plan_manifest_keys:
            raise Failure(
                description=(
                    "Property Finder search chunks require completed planning manifests. "
                    "Run pf_listings_plan_snapshot first or pass plan_manifest_s3_keys."
                ),
                metadata={
                    "source": PF_LISTINGS_SOURCE_NAME,
                    "operation": PF_LISTINGS_SEARCH_OPERATION,
                },
            )
        resolved_config["plan_manifest_s3_keys"] = plan_manifest_keys
        resolved_config["plan_manifest_s3_key"] = plan_manifest_keys[-1]

        has_explicit_cursor = (
            "search_query_cursor" in source_config or "search_page_cursor" in source_config
        )
        checkpoint = read_checkpoint_model(
            object_storage_client,
            source=PF_LISTINGS_SOURCE_NAME,
            operation=PF_LISTINGS_SEARCH_OPERATION,
            model=_PfSearchCheckpoint,
        )
        if (
            checkpoint
            and not reset_checkpoint
            and _search_checkpoint_matches_plan(checkpoint, plan_manifest_keys=plan_manifest_keys)
        ):
            if checkpoint.completed:
                raise Failure(
                    description=(
                        "Property Finder search checkpoint is already completed for the "
                        "current plan. Pass reset_checkpoint=true or run a new plan."
                    ),
                    metadata={
                        "source": PF_LISTINGS_SOURCE_NAME,
                        "operation": PF_LISTINGS_SEARCH_OPERATION,
                        "plan_manifest_s3_key": plan_manifest_keys[-1],
                    },
                )
            if not has_explicit_cursor:
                resolved_config["search_query_cursor"] = checkpoint.next_query_index
                resolved_config["search_page_cursor"] = checkpoint.next_page
        return resolved_config

    if mode == "details":
        has_explicit_cursor = (
            "detail_manifest_cursor" in source_config or "detail_row_cursor" in source_config
        )
        checkpoint = read_checkpoint_model(
            object_storage_client,
            source=PF_LISTINGS_SOURCE_NAME,
            operation=PF_LISTINGS_DETAIL_OPERATION,
            model=_PfDetailCheckpoint,
        )
        if checkpoint and not reset_checkpoint and not has_explicit_cursor:
            resolved_config["detail_manifest_cursor"] = checkpoint.next_manifest_index
            resolved_config["detail_row_cursor"] = checkpoint.next_row_index
        return resolved_config

    return resolved_config


def write_listings_checkpoint(
    *,
    raw_release: RawRelease,
    manifest_key: str,
    object_storage_client: Any,
) -> None:
    metadata = dict(raw_release.metadata)
    stage = metadata.get("stage")
    if stage == "plan":
        previous_plan_manifest_keys = metadata.get("previous_plan_manifest_s3_keys")
        plan_manifest_keys = [
            key
            for key in (
                previous_plan_manifest_keys if isinstance(previous_plan_manifest_keys, list) else []
            )
            if isinstance(key, str) and key
        ]
        plan_manifest_keys.append(manifest_key)
        write_checkpoint(
            object_storage_client,
            source=raw_release.source,
            operation=PF_LISTINGS_PLAN_OPERATION,
            payload={
                "completed": bool(metadata.get("plan_completed_result_set")),
                "last_run_id": raw_release.run_id,
                "last_manifest_s3_key": manifest_key,
                "plan_manifest_s3_keys": plan_manifest_keys,
                "planned_query_count": metadata.get("planned_query_count"),
                "terminal_query_count": metadata.get("terminal_query_count"),
                "location_partition_count": metadata.get("location_partition_count"),
                "queue_count": metadata.get("queue_count"),
                "plan_rows_in_run": metadata.get("plan_rows_in_run"),
                "updated_at": utc_now().isoformat(),
            },
        )
        return

    if stage == "search":
        write_checkpoint(
            object_storage_client,
            source=raw_release.source,
            operation=PF_LISTINGS_SEARCH_OPERATION,
            payload={
                "completed": bool(metadata.get("search_completed_result_set")),
                "next_query_index": metadata.get("next_query_index"),
                "next_page": metadata.get("next_page"),
                "plan_manifest_s3_key": metadata.get("plan_manifest_s3_key"),
                "plan_manifest_s3_keys": metadata.get("plan_manifest_s3_keys"),
                "last_run_id": raw_release.run_id,
                "last_manifest_s3_key": manifest_key,
                "search_page_count": metadata.get("search_page_count"),
                "property_row_count": metadata.get("property_row_count"),
                "search_error_count": metadata.get("search_error_count"),
                "updated_at": utc_now().isoformat(),
            },
        )
        return

    if stage == "details":
        write_checkpoint(
            object_storage_client,
            source=raw_release.source,
            operation=PF_LISTINGS_DETAIL_OPERATION,
            payload={
                "completed": bool(metadata.get("detail_completed_result_set")),
                "next_manifest_index": metadata.get("next_manifest_index"),
                "next_row_index": metadata.get("next_row_index"),
                "source_manifest_count": metadata.get("source_manifest_count"),
                "source_property_row_count": metadata.get("source_property_row_count"),
                "source_property_invalid_row_count": metadata.get(
                    "source_property_invalid_row_count"
                ),
                "last_run_id": raw_release.run_id,
                "last_manifest_s3_key": manifest_key,
                "detail_row_count": metadata.get("detail_row_count"),
                "updated_at": utc_now().isoformat(),
            },
        )


def _coerce_manifest_keys(value: Any) -> list[str]:
    if isinstance(value, str):
        return [key.strip() for key in value.split(",") if key.strip()]
    if isinstance(value, list | tuple):
        return [key.strip() for key in value if isinstance(key, str) and key.strip()]
    return []


def _search_checkpoint_matches_plan(
    checkpoint: _PfSearchCheckpoint,
    *,
    plan_manifest_keys: list[str],
) -> bool:
    return checkpoint.matches_plan(plan_manifest_keys)
