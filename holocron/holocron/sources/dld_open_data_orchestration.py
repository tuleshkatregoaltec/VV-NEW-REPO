from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from dagster import Failure
from pydantic import BaseModel, ConfigDict, Field

from holocron.contracts import RawRelease
from holocron.platform.checkpoints import read_checkpoint_model, write_checkpoint
from holocron.platform.execution import utc_now
from holocron.platform.raw_files import string_value

DLD_OPEN_DATA_CHUNK_DEFAULTS = {
    "page_size": 10000,
    "max_pages": 1,
    "slice_days": 366,
}
DLD_OPEN_DATA_INCREMENTAL_DEFAULTS = {
    "mode": "incremental",
    "page_size": 10000,
    "slice_days": 14,
}
DLD_OPEN_DATA_RENTS_FULL_DEFAULTS = {
    **DLD_OPEN_DATA_CHUNK_DEFAULTS,
    "start_date": "2017-01-01",
    "filters": {"P_DATE_TYPE": "1"},
}
DLD_OPEN_DATA_RENTS_INCREMENTAL_DEFAULTS = {
    "mode": "incremental",
    "page_size": 10000,
    "slice_days": 1,
    "lookback_days": 14,
    "checkpointed_incremental": True,
    "incremental_overlap_days": 7,
    "filters": {"P_DATE_TYPE": "3"},
    "row_date_field": "REGISTRATION_DATE",
    "request_to_date_offset_days": 1,
    "replace_date_column": "registration_date",
}


class _OpenDataCheckpoint(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    mode: str = ""
    completed: bool = False
    next_window_index: int = 0
    next_skip: int = 0
    start_date: str | None = None
    end_date: str | None = None
    explicit_date_window: bool | None = None
    uses_date_windows: bool | None = None
    effective_start_date: str | None = None
    effective_end_date: str | None = None
    slice_days: Any = None
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: str = ""


def resolve_open_data_config(
    *,
    source_name: str,
    source_config: Mapping[str, Any],
    object_storage_client: Any,
) -> dict[str, Any]:
    resolved_config = dict(source_config)
    mode = str(resolved_config.get("mode") or "incremental")
    reset_checkpoint = bool(resolved_config.pop("reset_checkpoint", False))
    if mode == "incremental":
        if bool(resolved_config.get("checkpointed_incremental")):
            return _resolve_checkpointed_incremental_config(
                source_name=source_name,
                source_config=resolved_config,
                object_storage_client=object_storage_client,
            )
        return resolved_config

    has_explicit_cursor = "window_cursor" in source_config or "skip_cursor" in source_config
    checkpoint = read_checkpoint_model(
        object_storage_client,
        source=source_name,
        operation=open_data_checkpoint_operation(mode),
        model=_OpenDataCheckpoint,
    )
    if (
        checkpoint
        and not reset_checkpoint
        and _open_data_checkpoint_matches(
            checkpoint=checkpoint,
            source_config=resolved_config,
            mode=mode,
        )
    ):
        if checkpoint.completed:
            raise Failure(
                description=(
                    f"{source_name} {mode} checkpoint is already completed. "
                    "Pass reset_checkpoint=true to run it again."
                ),
                metadata={"source": source_name, "operation": mode},
            )
        if not has_explicit_cursor:
            resume_overrides = _checkpoint_resume_overrides(
                checkpoint=checkpoint,
                source_config=source_config,
            )
            if resume_overrides is None:
                return resolved_config
            resolved_config.update(resume_overrides)
            resolved_config["window_cursor"] = checkpoint.next_window_index
            resolved_config["skip_cursor"] = checkpoint.next_skip
    return resolved_config


def _resolve_checkpointed_incremental_config(
    *,
    source_name: str,
    source_config: Mapping[str, Any],
    object_storage_client: Any,
) -> dict[str, Any]:
    resolved_config = dict(source_config)
    today = utc_now().date()
    end_date = _config_date(source_config, "end_date") or today
    if _has_config_value(source_config, "start_date"):
        resolved_config["end_date"] = end_date.isoformat()
        return resolved_config

    checkpoint = read_checkpoint_model(
        object_storage_client,
        source=source_name,
        operation=open_data_checkpoint_operation("incremental"),
        model=_OpenDataCheckpoint,
    )
    overlap_days = max(_config_int(source_config, "incremental_overlap_days", default=0), 0)
    if (
        checkpoint
        and checkpoint.completed
        and checkpoint.effective_end_date
        and _open_data_checkpoint_matches(
            checkpoint=checkpoint,
            source_config=source_config,
            mode="incremental",
        )
    ):
        start_date = date.fromisoformat(checkpoint.effective_end_date) - timedelta(
            days=overlap_days
        )
    else:
        lookback_days = max(_config_int(source_config, "lookback_days", default=3), 0)
        start_date = end_date - timedelta(days=lookback_days)
    if start_date > end_date:
        start_date = end_date
    resolved_config["start_date"] = start_date.isoformat()
    resolved_config["end_date"] = end_date.isoformat()
    resolved_config["checkpoint_explicit_date_window"] = False
    return resolved_config


def write_open_data_checkpoint(
    *,
    raw_release: RawRelease,
    manifest_key: str,
    object_storage_client: Any,
) -> None:
    metadata = dict(raw_release.metadata)
    mode = str(metadata.get("stage") or "")
    config = metadata.get("config")
    if not isinstance(config, Mapping):
        config = {}
    if mode == "incremental" and not bool(config.get("checkpointed_incremental")):
        return
    if mode not in {"snapshot", "backfill", "incremental"}:
        return
    write_checkpoint(
        object_storage_client,
        source=raw_release.source,
        operation=open_data_checkpoint_operation(mode),
        payload={
            "mode": mode,
            "completed": bool(metadata.get("completed_result_set")),
            "next_window_index": metadata.get("next_window_index"),
            "next_skip": metadata.get("next_skip"),
            "window_count": metadata.get("window_count"),
            "page_count": metadata.get("page_count"),
            "row_count": metadata.get("row_count"),
            "start_date": config.get("start_date"),
            "end_date": config.get("end_date"),
            "explicit_date_window": _explicit_date_window_metadata(
                metadata=metadata,
                config=config,
            ),
            "uses_date_windows": metadata.get("uses_date_windows"),
            "effective_start_date": metadata.get("effective_start_date"),
            "effective_end_date": metadata.get("effective_end_date"),
            "slice_days": config.get("slice_days"),
            "filters": dict(config.get("filters") or {}),
            "sort": config.get("sort") or "",
            "last_run_id": raw_release.run_id,
            "last_manifest_s3_key": manifest_key,
            "updated_at": utc_now().isoformat(),
        },
    )


def open_data_checkpoint_operation(mode: str) -> str:
    if mode == "incremental":
        return "incremental_success"
    return f"{mode}_chunk"


def _open_data_checkpoint_matches(
    *,
    checkpoint: _OpenDataCheckpoint,
    source_config: Mapping[str, Any],
    mode: str,
) -> bool:
    if checkpoint.mode != mode:
        return False
    if mode in {"snapshot", "backfill"}:
        source_has_explicit_date_window = _has_explicit_date_window(source_config)
        if not source_has_explicit_date_window and checkpoint.explicit_date_window is True:
            return False
        for date_key in ("start_date", "end_date"):
            checkpoint_value = getattr(checkpoint, date_key)
            if _has_config_value(source_config, date_key) and str(checkpoint_value or "") != str(
                source_config.get(date_key) or ""
            ):
                return False
        if str(checkpoint.slice_days or "") != str(source_config.get("slice_days") or ""):
            return False
    return checkpoint.filters == dict(source_config.get("filters") or {}) and str(
        checkpoint.sort or ""
    ) == str(source_config.get("sort") or "")


def _checkpoint_resume_overrides(
    *,
    checkpoint: _OpenDataCheckpoint,
    source_config: Mapping[str, Any],
) -> dict[str, Any] | None:
    overrides: dict[str, Any] = {
        "checkpoint_explicit_date_window": _has_explicit_date_window(source_config)
    }
    uses_date_windows = checkpoint.uses_date_windows
    if uses_date_windows is False:
        return overrides

    for date_key, effective_key in (
        ("start_date", "effective_start_date"),
        ("end_date", "effective_end_date"),
    ):
        if _has_config_value(source_config, date_key):
            continue
        effective_value = string_value(getattr(checkpoint, effective_key))
        if effective_value:
            overrides[date_key] = effective_value
        elif uses_date_windows is True:
            return None
    return overrides


def _explicit_date_window_metadata(
    *,
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
) -> bool:
    explicit_date_window = metadata.get("explicit_date_window")
    if isinstance(explicit_date_window, bool):
        return explicit_date_window
    return _has_explicit_date_window(config)


def _has_config_value(config: Mapping[str, Any], key: str) -> bool:
    return config.get(key) not in {None, ""}


def _has_explicit_date_window(config: Mapping[str, Any]) -> bool:
    return any(_has_config_value(config, key) for key in ("start_date", "end_date"))


def _config_date(config: Mapping[str, Any], key: str) -> date | None:
    value = config.get(key)
    if value in {None, ""}:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _config_int(config: Mapping[str, Any], key: str, *, default: int) -> int:
    value = config.get(key)
    if value in {None, ""}:
        return default
    return int(value)
