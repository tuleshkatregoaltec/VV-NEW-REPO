from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dagster import Failure
from pydantic import BaseModel, ConfigDict

from holocron.contracts import RawRelease
from holocron.platform.checkpoints import read_checkpoint_model, write_checkpoint
from holocron.platform.execution import utc_now

REELLY_ARCHIVE_OPERATION = "archive_chunk"
REELLY_ARCHIVE_CHUNK_DEFAULTS = {
    "pages_per_run": 5,
    "download_documents": False,
    "download_all_project_docs": True,
    "try_matrix_availability": False,
}
REELLY_CATALOG_DELTA_DEFAULTS = {
    "mode": "catalog_delta",
    "pages_per_run": 200,
    "download_documents": False,
    "download_all_project_docs": False,
    "try_matrix_availability": False,
    "fetch_documents_for_delta": True,
    "bootstrap_details": False,
    "detail_audit_limit": 50,
}
REELLY_AVAILABILITY_DELTA_DEFAULTS = {
    "mode": "availability_delta",
    "download_documents": False,
    "try_matrix_availability": True,
}
REELLY_PROJECT_MEDIA_DEFAULTS = {
    "target_prefix": "media/reelly_supply/project_media",
    "inventory_prefix": "raw/source=reelly_supply/project_media_asset_manifests",
    "inventory_file_name": "reelly_supply_project_media_assets.jsonl",
    "include_project_documents": False,
    "include_project_detail_media": True,
    "structured_target_keys": True,
    "max_concurrent_downloads": 8,
    "asset_type_allowlist": (
        "cover_image",
        "developer_logo",
        "building_image",
        "interior_image",
        "facility_image",
        "master_plan",
        "floorplan",
        "unit_image",
        "project_image",
    ),
}


_ARCHIVE_MODE = "archive"


class _ArchiveCheckpoint(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    completed: bool = False
    next_page: int | None = None


def resolve_archive_config(
    *,
    source_config: Mapping[str, Any],
    object_storage_client: Any,
) -> dict[str, Any]:
    resolved_config = dict(source_config)
    if str(resolved_config.get("mode") or _ARCHIVE_MODE) != _ARCHIVE_MODE:
        resolved_config.pop("reset_checkpoint", None)
        return resolved_config
    reset_checkpoint = bool(resolved_config.pop("reset_checkpoint", False))
    checkpoint = read_checkpoint_model(
        object_storage_client,
        source="reelly_supply",
        operation=REELLY_ARCHIVE_OPERATION,
        model=_ArchiveCheckpoint,
    )
    if checkpoint and checkpoint.completed and not reset_checkpoint:
        raise Failure(
            description=(
                "Reelly supply archive checkpoint is already completed. "
                "Pass reset_checkpoint=true to run another archive pass."
            ),
            metadata={
                "source": "reelly_supply",
                "operation": REELLY_ARCHIVE_OPERATION,
            },
        )

    has_explicit_cursor = (
        "page_cursor" in resolved_config and resolved_config["page_cursor"] is not None
    )
    if (
        checkpoint
        and not reset_checkpoint
        and not has_explicit_cursor
        and checkpoint.next_page is not None
    ):
        resolved_config["page_cursor"] = checkpoint.next_page
    return resolved_config


def write_archive_checkpoint(
    *,
    raw_release: RawRelease,
    manifest_key: str,
    object_storage_client: Any,
) -> None:
    metadata = dict(raw_release.metadata)
    write_checkpoint(
        object_storage_client,
        source=raw_release.source,
        operation=REELLY_ARCHIVE_OPERATION,
        payload={
            "next_page": metadata.get("next_page"),
            "completed": bool(metadata.get("batch_completed_result_set")),
            "last_run_id": raw_release.run_id,
            "last_manifest_s3_key": manifest_key,
            "page_total": metadata.get("page_total"),
            "updated_at": utc_now().isoformat(),
        },
    )
