from dagster import (
    AssetExecutionContext,
    AssetIn,
    AssetsDefinition,
    ConfigMapping,
    DefaultScheduleStatus,
    Field,
    JobDefinition,
    MaterializeResult,
    MetadataValue,
    Output,
    Permissive,
    ScheduleDefinition,
    StringSource,
    asset,
    define_asset_job,
)
from dagster._core.definitions.unresolved_asset_job_definition import UnresolvedAssetJobDefinition

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from holocron.contracts import RawRelease, SourceSpec
from holocron.assets.geography import (
    geo_entity_links_asset,
    geo_location_closure_asset,
    geo_location_nodes_asset,
    geo_source_signatures_asset,
    offplan_reelly_project_links_asset,
)
from holocron.platform.manifests import manifest_s3_key, raw_file_s3_key, raw_manifest_is_smoke
from holocron.platform.resources import ClickHouseResource, ObjectStorageResource
from holocron.sources.dld_open_data_orchestration import (
    DLD_OPEN_DATA_CHUNK_DEFAULTS,
    DLD_OPEN_DATA_INCREMENTAL_DEFAULTS,
    DLD_OPEN_DATA_RENTS_FULL_DEFAULTS,
    DLD_OPEN_DATA_RENTS_INCREMENTAL_DEFAULTS,
    resolve_open_data_config,
    write_open_data_checkpoint,
)
from holocron.sources.dld_pulse_historic.assets import (
    DldPulseHistoricBronzeConfig,
    load_dld_pulse_historic_bronze,
)
from holocron.sources.pf_listings.media_assets import (
    PropertyFinderListingMediaHydrationConfig,
    hydrate_pf_listing_media_assets,
)
from holocron.sources.pf_listings.orchestration import (
    PF_LISTINGS_DETAIL_CHUNK_DEFAULTS,
    PF_LISTINGS_LATEST_DELTA_DEFAULTS,
    PF_LISTINGS_MANUAL_SNAPSHOT_DEFAULTS,
    PF_LISTINGS_PLAN_DEFAULTS,
    PF_LISTINGS_SEARCH_CHUNK_DEFAULTS,
    resolve_listings_config,
    write_listings_checkpoint,
)
from holocron.sources.news_feeds.assets import (
    NewsPublishConfig,
    NewsThumbnailHydrationConfig,
    hydrate_news_thumbnail_assets,
    publish_news_to_platform,
)
from holocron.silver.assets import silver_rent_contracts_asset, silver_transactions_asset
from holocron.sources.reelly_supply.document_assets import (
    ReellyDocumentAssetHydrationConfig,
    hydrate_reelly_document_assets,
)
from holocron.sources.reelly_supply.orchestration import (
    REELLY_ARCHIVE_CHUNK_DEFAULTS,
    REELLY_AVAILABILITY_DELTA_DEFAULTS,
    REELLY_CATALOG_DELTA_DEFAULTS,
    REELLY_PROJECT_MEDIA_DEFAULTS,
    resolve_archive_config,
    write_archive_checkpoint,
)

_DUBAI_TIMEZONE = "Asia/Dubai"
AssetJobDefinition = JobDefinition | UnresolvedAssetJobDefinition
_NEWS_PROVIDER_GROUP = "news"
_PROPERTYFINDER_PROVIDER_GROUP = "propertyfinder"
_REELLY_PROVIDER_GROUP = "reelly"
_DLD_OPEN_DATA_JOB_SPECS = (
    (
        "transactions",
        "0 4 * * *",
        DLD_OPEN_DATA_INCREMENTAL_DEFAULTS,
        DLD_OPEN_DATA_CHUNK_DEFAULTS,
    ),
    (
        "rents",
        "10 4 * * *",
        DLD_OPEN_DATA_RENTS_INCREMENTAL_DEFAULTS,
        DLD_OPEN_DATA_RENTS_FULL_DEFAULTS,
    ),
    ("projects", "20 4 * * *", {"mode": "incremental"}, DLD_OPEN_DATA_CHUNK_DEFAULTS),
    ("valuations", "30 4 * * *", {"mode": "incremental"}, DLD_OPEN_DATA_CHUNK_DEFAULTS),
    ("buildings", "40 4 * * *", {"mode": "incremental"}, DLD_OPEN_DATA_CHUNK_DEFAULTS),
    ("developers", "50 4 * * *", {"mode": "incremental"}, DLD_OPEN_DATA_CHUNK_DEFAULTS),
    ("lands", "10 5 * * *", {"mode": "incremental"}, DLD_OPEN_DATA_CHUNK_DEFAULTS),
    ("units", "20 5 * * *", {"mode": "incremental"}, DLD_OPEN_DATA_CHUNK_DEFAULTS),
    ("brokers", "30 5 * * *", {"mode": "incremental"}, DLD_OPEN_DATA_CHUNK_DEFAULTS),
)
_DLD_OPEN_DATA_SCHEDULE_SPECS = {
    f"dld_od_{category}_daily_incremental": cron
    for category, cron, _, _ in _DLD_OPEN_DATA_JOB_SPECS
}


class _ClientResource(Protocol):
    def client(self) -> Any: ...


def _raw_asset_name(source: SourceSpec) -> str:
    return f"{source.name}_raw"


def _bronze_asset_name(source: SourceSpec) -> str:
    return f"{source.name}_bronze"


def _get_source_config(context: AssetExecutionContext) -> dict:
    config = context.op_execution_context.op_config
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise TypeError(f"Expected dict-like source config, got {type(config)!r}")
    return config


def _raw_release_file_path(*, scratch_path: Path, local_path: Path) -> str:
    try:
        return local_path.resolve().relative_to(scratch_path.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Raw file path is outside extractor scratch directory: {local_path}"
        ) from exc


def _pop_state_updates(metadata: dict[str, Any]) -> list[dict[str, str]]:
    raw_updates = metadata.pop("_state_updates", [])
    if not raw_updates:
        return []
    if not isinstance(raw_updates, list):
        raise TypeError("Raw release metadata _state_updates must be a list")

    updates: list[dict[str, str]] = []
    for update in raw_updates:
        if not isinstance(update, Mapping):
            raise TypeError("Raw release metadata _state_updates entries must be objects")
        key = str(update.get("key") or "").strip()
        path = str(update.get("path") or "").strip()
        if not key or not path:
            raise ValueError("Raw release state update entries require key and path")
        updates.append({"key": key, "path": path})
    return updates


def _write_state_updates(
    *,
    state_updates: list[dict[str, str]],
    scratch_path: Path,
    object_storage_client: Any,
) -> None:
    for update in state_updates:
        local_path = Path(update["path"])
        _raw_release_file_path(scratch_path=scratch_path, local_path=local_path)
        payload = json.loads(local_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"State update payload must be a JSON object: {local_path}")
        object_storage_client.put_json(key=update["key"], payload=payload)


def _run_raw_extractor(
    *,
    context: AssetExecutionContext,
    source: SourceSpec,
    object_storage: ObjectStorageResource,
) -> tuple[dict, dict]:
    source_config = _get_source_config(context)
    object_storage_client = object_storage.client()
    if source.name == "reelly_supply":
        source_config = resolve_archive_config(
            source_config=source_config,
            object_storage_client=object_storage_client,
        )
    if source.name == "pf_listings":
        source_config = resolve_listings_config(
            source_config=source_config,
            object_storage_client=object_storage_client,
        )
    if source.name.startswith("dld_od_"):
        source_config = resolve_open_data_config(
            source_name=source.name,
            source_config=source_config,
            object_storage_client=object_storage_client,
        )
    context.log.info(
        "materializing raw source=%s with config keys=%s", source.name, sorted(source_config)
    )

    temporary_directory_dir: str | None = None
    if source.name == "dld_pulse_historic":
        input_dir = Path(str(source_config.get("input_dir") or "pulse-data")).expanduser()
        if not input_dir.is_absolute():
            input_dir = Path.cwd() / input_dir
        temporary_directory_dir = str(input_dir.resolve().parent)

    with TemporaryDirectory(
        prefix=f"holocron-{source.name}-",
        dir=temporary_directory_dir,
    ) as scratch_dir:
        extractor_kwargs: dict[str, Any] = {"config": source_config}
        if source.name.startswith("dld_od_") or source.name in {
            "dld_pulse_historic",
            "reelly_supply",
            "dxbi_transactions",
            "news_feeds",
            "pf_locations",
            "pf_listings",
        }:
            extractor_kwargs["progress_log"] = context.log
        if source.name in {"pf_listings", "reelly_supply"}:
            extractor_kwargs["state_store"] = object_storage_client
        raw_release = source.extractor(scratch_dir, **extractor_kwargs)
        if not isinstance(raw_release, RawRelease):
            raise TypeError(
                f"Extractor for source={source.name} must return RawRelease, got {type(raw_release)!r}"
            )
        if raw_release.source != source.name:
            raise ValueError(
                f"Extractor source mismatch: expected {source.name}, got {raw_release.source}"
            )
        if not raw_release.files:
            raise ValueError(f"Extractor for source={source.name} returned no files")
        release_metadata = dict(raw_release.metadata)
        state_updates = _pop_state_updates(release_metadata)

        manifest_files: list[dict] = []
        total_rows = 0

        scratch_path = Path(scratch_dir)
        for raw_file in raw_release.files:
            local_path = Path(raw_file.path)
            file_path = _raw_release_file_path(scratch_path=scratch_path, local_path=local_path)
            file_key = raw_file_s3_key(
                source=raw_release.source,
                extract_date=raw_release.extract_date,
                run_id=raw_release.run_id,
                file_name=file_path,
            )
            object_storage_client.upload_file(
                path=local_path,
                key=file_key,
                content_type=raw_file.content_type,
            )

            if raw_file.row_count is not None:
                total_rows += raw_file.row_count

            manifest_files.append(
                {
                    "path": file_path,
                    "sha256": raw_file.sha256,
                    "size_bytes": raw_file.size_bytes,
                    "row_count": raw_file.row_count,
                    "content_type": raw_file.content_type,
                    "metadata": dict(raw_file.metadata),
                    "s3_key": file_key,
                }
            )

        manifest_key = manifest_s3_key(source=raw_release.source, run_id=raw_release.run_id)
        release_payload_base = {
            "source": raw_release.source,
            "run_id": raw_release.run_id,
            "extract_date": raw_release.extract_date,
            "created_at": raw_release.created_at,
            "manifest_version": raw_release.manifest_version,
            "schema_version": raw_release.schema_version,
            "files": manifest_files,
            "metadata": release_metadata,
            "manifest_s3_key": manifest_key,
        }
        manifest_payload = {k: v for k, v in release_payload_base.items() if k != "manifest_s3_key"}
        object_storage_client.put_json(key=manifest_key, payload=manifest_payload)
        if source.name == "reelly_supply" and release_metadata.get("mode", "archive") == "archive":
            write_archive_checkpoint(
                raw_release=raw_release,
                manifest_key=manifest_key,
                object_storage_client=object_storage_client,
            )
        if source.name == "pf_listings":
            write_listings_checkpoint(
                raw_release=raw_release,
                manifest_key=manifest_key,
                object_storage_client=object_storage_client,
            )
        if source.name.startswith("dld_od_"):
            write_open_data_checkpoint(
                raw_release=raw_release,
                manifest_key=manifest_key,
                object_storage_client=object_storage_client,
            )
        _write_state_updates(
            state_updates=state_updates,
            scratch_path=scratch_path,
            object_storage_client=object_storage_client,
        )

    release_payload = release_payload_base
    output_metadata = {
        "source": source.name,
        "provider": source.provider,
        "stage": "raw",
        "status": "materialized",
        "run_id": raw_release.run_id,
        "extract_date": raw_release.extract_date,
        "file_count": len(raw_release.files),
        "total_rows": total_rows,
        "manifest_s3_key": manifest_key,
        "files": MetadataValue.json(manifest_files),
    }
    return release_payload, output_metadata


def _run_bronze_loader(
    *,
    source: SourceSpec,
    raw_manifest: dict,
    object_storage: _ClientResource,
    clickhouse: _ClientResource,
) -> MaterializeResult:
    bronze_loader = source.bronze_loader
    if bronze_loader is None:
        raise ValueError(f"No bronze loader configured for source={source.name}")
    if raw_manifest_is_smoke(raw_manifest):
        raise ValueError(
            f"Smoke raw manifest cannot be loaded into normal bronze tables: source={source.name}"
        )

    result = bronze_loader(
        raw_manifest=raw_manifest,
        s3=object_storage.client(),
        clickhouse=clickhouse.client(),
    )
    return MaterializeResult(
        metadata={
            "source": source.name,
            "stage": "bronze",
            "status": "materialized",
            "run_id": result["run_id"],
            "table_count": result["table_count"],
            "total_rows": result["total_rows"],
            "table_row_counts": MetadataValue.json(result["table_row_counts"]),
        }
    )


def build_assets_for_source(source: SourceSpec) -> list[AssetsDefinition]:
    """Produce the raw -> bronze asset chain for one source.

    Raw extraction is taken from SourceSpec.extractor, and bronze loading is
    delegated to SourceSpec.bronze_loader when the source declares bronze tables.
    """
    raw_name = _raw_asset_name(source)
    bronze_name = _bronze_asset_name(source)

    @asset(name=raw_name, group_name=source.provider, config_schema=Permissive())
    def raw_asset(
        context: AssetExecutionContext,
        object_storage: ObjectStorageResource,
    ) -> Output[dict]:
        release_payload, output_metadata = _run_raw_extractor(
            context=context,
            source=source,
            object_storage=object_storage,
        )
        return Output(release_payload, metadata=output_metadata)

    assets = [raw_asset]
    if not source.bronze_tables:
        return assets
    if source.bronze_loader is None:
        raise ValueError(f"Source {source.name} declares bronze tables without a bronze loader")

    @asset(
        name=bronze_name,
        ins={"raw_manifest": AssetIn(key=raw_name)},
        group_name=source.provider,
    )
    def bronze_asset(
        context: AssetExecutionContext,
        raw_manifest: dict,
        clickhouse: ClickHouseResource,
        object_storage: ObjectStorageResource,
    ) -> MaterializeResult:
        if not isinstance(raw_manifest, dict):
            raise TypeError(f"Expected raw manifest payload dict, got {type(raw_manifest)!r}")
        return _run_bronze_loader(
            source=source,
            raw_manifest=raw_manifest,
            object_storage=object_storage,
            clickhouse=clickhouse,
        )

    return [raw_asset, bronze_asset]


def build_reelly_document_assets() -> list[AssetsDefinition]:
    @asset(
        name="reelly_supply_document_assets",
        group_name=_REELLY_PROVIDER_GROUP,
        deps=["reelly_supply_raw"],
        config_schema=Permissive(),
    )
    def reelly_supply_document_assets(
        context: AssetExecutionContext,
        object_storage: ObjectStorageResource,
    ) -> MaterializeResult:
        result = hydrate_reelly_document_assets(
            s3=object_storage.client(),
            config=_get_source_config(context),
            progress_log=context.log,
        )
        return MaterializeResult(
            metadata={
                "source": "reelly_supply",
                "stage": "document_assets",
                "status": "materialized",
                "run_id": result["run_id"],
                "discovered": result["discovered"],
                "skipped_existing": result["skipped_existing"],
                "attempted": result["attempted"],
                "downloaded": result["downloaded"],
                "already_exists": result["already_exists"],
                "errors": result["errors"],
                "total_bytes": result["total_bytes"],
                "max_concurrent_downloads": result["max_concurrent_downloads"],
                "inventory_manifest_key": result["inventory_manifest_key"],
                "status_counts": MetadataValue.json(result["status_counts"]),
            }
        )

    @asset(
        name="reelly_supply_project_media_assets",
        group_name=_REELLY_PROVIDER_GROUP,
        deps=["reelly_supply_raw"],
        config_schema=Permissive(),
    )
    def reelly_supply_project_media_assets(
        context: AssetExecutionContext,
        object_storage: ObjectStorageResource,
    ) -> MaterializeResult:
        result = hydrate_reelly_document_assets(
            s3=object_storage.client(),
            config={**REELLY_PROJECT_MEDIA_DEFAULTS, **_get_source_config(context)},
            progress_log=context.log,
        )
        return MaterializeResult(
            metadata={
                "source": "reelly_supply",
                "stage": "project_media_assets",
                "status": "materialized",
                "run_id": result["run_id"],
                "discovered": result["discovered"],
                "skipped_existing": result["skipped_existing"],
                "attempted": result["attempted"],
                "downloaded": result["downloaded"],
                "already_exists": result["already_exists"],
                "errors": result["errors"],
                "total_bytes": result["total_bytes"],
                "max_concurrent_downloads": result["max_concurrent_downloads"],
                "inventory_manifest_key": result["inventory_manifest_key"],
                "status_counts": MetadataValue.json(result["status_counts"]),
            }
        )

    return [reelly_supply_document_assets, reelly_supply_project_media_assets]


def build_pf_listing_media_assets() -> list[AssetsDefinition]:
    @asset(
        name="pf_listing_media_assets",
        group_name=_PROPERTYFINDER_PROVIDER_GROUP,
        deps=["pf_listings_raw"],
        config_schema=Permissive(),
    )
    def pf_listing_media_assets(
        context: AssetExecutionContext,
        object_storage: ObjectStorageResource,
    ) -> MaterializeResult:
        result = hydrate_pf_listing_media_assets(
            s3=object_storage.client(),
            config=_get_source_config(context),
            progress_log=context.log,
        )
        return MaterializeResult(
            metadata={
                "source": "pf_listings",
                "stage": "listing_media_assets",
                "status": "materialized",
                "run_id": result["run_id"],
                "discovered": result["discovered"],
                "skipped_existing": result["skipped_existing"],
                "attempted": result["attempted"],
                "downloaded": result["downloaded"],
                "already_exists": result["already_exists"],
                "errors": result["errors"],
                "total_bytes": result["total_bytes"],
                "max_concurrent_downloads": result["max_concurrent_downloads"],
                "inventory_manifest_key": result["inventory_manifest_key"],
                "status_counts": MetadataValue.json(result["status_counts"]),
            }
        )

    return [pf_listing_media_assets]


def build_news_feed_assets() -> list[AssetsDefinition]:
    @asset(
        name="news_thumbnail_assets",
        group_name=_NEWS_PROVIDER_GROUP,
        deps=["news_feeds_raw"],
        config_schema=Permissive(),
    )
    def news_thumbnail_assets(
        context: AssetExecutionContext,
        object_storage: ObjectStorageResource,
    ) -> MaterializeResult:
        result = hydrate_news_thumbnail_assets(
            s3=object_storage.client(),
            config=_get_source_config(context),
            progress_log=context.log,
        )
        return MaterializeResult(
            metadata={
                "source": "news_feeds",
                "stage": "thumbnail_assets",
                "status": "materialized",
                "run_id": result["run_id"],
                "discovered": result["discovered"],
                "skipped_existing": result["skipped_existing"],
                "attempted": result["attempted"],
                "downloaded": result["downloaded"],
                "already_exists": result["already_exists"],
                "errors": result["errors"],
                "total_bytes": result["total_bytes"],
                "source_manifest_count": result["source_manifest_count"],
                "source_row_count": result["source_row_count"],
                "max_concurrent_downloads": result["max_concurrent_downloads"],
                "inventory_manifest_key": result["inventory_manifest_key"],
                "status_counts": MetadataValue.json(result["status_counts"]),
            }
        )

    @asset(
        name="news_publish",
        group_name=_NEWS_PROVIDER_GROUP,
        deps=["news_thumbnail_assets"],
        config_schema=Permissive(),
    )
    def news_publish(
        context: AssetExecutionContext,
        object_storage: ObjectStorageResource,
    ) -> MaterializeResult:
        result = publish_news_to_platform(
            s3=object_storage.client(),
            config=_get_source_config(context),
            progress_log=context.log,
        )
        return MaterializeResult(
            metadata={
                "source": "news_feeds",
                "stage": "platform_publish",
                "status": "materialized",
                "source_manifest_count": result["source_manifest_count"],
                "source_row_count": result["source_row_count"],
                "selected": result["selected"],
                "skipped": result["skipped"],
                "published": result["published"],
                "created": result["created"],
                "updated": result["updated"],
                "failed": result["failed"],
                "dry_run": result["dry_run"],
                "writer_result": MetadataValue.json(result["writer_result"]),
            }
        )

    return [news_thumbnail_assets, news_publish]


def build_silver_assets() -> list[AssetsDefinition]:
    return [silver_transactions_asset, silver_rent_contracts_asset]


def build_geography_assets() -> list[AssetsDefinition]:
    return [
        geo_location_nodes_asset,
        geo_location_closure_asset,
        geo_source_signatures_asset,
        geo_entity_links_asset,
        offplan_reelly_project_links_asset,
    ]


def build_dld_pulse_historic_assets() -> list[AssetsDefinition]:
    @asset(
        name="dld_pulse_historic_bronze",
        group_name="dld",
        config_schema=Permissive(),
    )
    def dld_pulse_historic_bronze(
        context: AssetExecutionContext,
        clickhouse: ClickHouseResource,
        object_storage: ObjectStorageResource,
    ) -> MaterializeResult:
        asset_config = DldPulseHistoricBronzeConfig.model_validate(_get_source_config(context))
        result = load_dld_pulse_historic_bronze(
            s3=object_storage.client(),
            clickhouse=clickhouse.client(),
            config=asset_config,
            progress_log=context.log,
        )
        return MaterializeResult(
            metadata={
                "source": "dld_pulse_historic",
                "stage": "bronze",
                "status": "materialized",
                "manifest_s3_key": asset_config.manifest_key,
                "batch_size": asset_config.batch_size,
                "run_id": result["run_id"],
                "table_count": result["table_count"],
                "total_rows": result["total_rows"],
                "table_row_counts": MetadataValue.json(result["table_row_counts"]),
            }
        )

    return [dld_pulse_historic_bronze]


def _build_dld_open_data_jobs(
    sources: Mapping[str, SourceSpec],
    *,
    operation: str,
) -> list[AssetJobDefinition]:
    jobs: list[AssetJobDefinition] = []
    for category, _, incremental_defaults, full_defaults in _DLD_OPEN_DATA_JOB_SPECS:
        source_name = f"dld_od_{category}"
        source = sources[source_name]
        if operation == "daily_incremental":
            config: Mapping[str, Any] | ConfigMapping = _raw_asset_run_config(
                source,
                incremental_defaults,
            )
        elif operation == "manual_backfill":
            config = _backfill_config_mapping(source, defaults=full_defaults)
        elif operation == "manual_snapshot":
            config = _defaulted_raw_config_mapping(
                source,
                defaults={**full_defaults, "mode": "snapshot"},
            )
        else:
            raise ValueError(f"Unsupported DLD Open Data operation: {operation}")
        jobs.append(
            _build_source_asset_job(
                source=source,
                name=f"{source_name}_{operation}",
                raw_only=operation != "daily_incremental",
                config=config,
            )
        )
    return jobs


def build_operational_jobs(sources: Mapping[str, SourceSpec]) -> list[AssetJobDefinition]:
    return [
        *_build_dld_open_data_jobs(sources, operation="daily_incremental"),
        _build_source_asset_job(
            source=sources["dxbi_transactions"],
            name="dxbi_transactions_daily_incremental",
            raw_only=False,
            config=_raw_asset_run_config(sources["dxbi_transactions"], {"mode": "incremental"}),
        ),
        _build_source_asset_job(
            source=sources["dda_planning_layers"],
            name="dda_planning_layers_weekly_full_refresh",
            raw_only=False,
        ),
        *_build_dld_open_data_jobs(sources, operation="manual_backfill"),
        *_build_dld_open_data_jobs(sources, operation="manual_snapshot"),
        _build_source_asset_job(
            source=sources["dxbi_transactions"],
            name="dxbi_transactions_manual_backfill",
            raw_only=True,
            config=_backfill_config_mapping(sources["dxbi_transactions"]),
        ),
        _build_source_asset_job(
            source=sources["dda_planning_layers"],
            name="dda_planning_layers_manual_full_refresh",
            raw_only=False,
            config=_defaulted_raw_config_mapping(sources["dda_planning_layers"], defaults={}),
        ),
        _build_source_asset_job(
            source=sources["dld_pulse_historic"],
            name="dld_pulse_historic_archive",
            raw_only=True,
            config=_raw_asset_run_config(
                sources["dld_pulse_historic"],
                {"input_dir": "pulse-data"},
            ),
        ),
        define_asset_job(
            name="dld_pulse_historic_bronze_backfill",
            selection=["dld_pulse_historic_bronze"],
            config=_dld_pulse_historic_bronze_config_mapping(),
        ),
        _build_source_asset_job(
            source=sources["pf_locations"],
            name="pf_locations_manual_full_fetch",
            raw_only=False,
        ),
        _build_source_asset_job(
            source=sources["pf_listings"],
            name="pf_listings_manual_snapshot",
            raw_only=False,
            config=_defaulted_raw_config_mapping(
                sources["pf_listings"],
                defaults=PF_LISTINGS_MANUAL_SNAPSHOT_DEFAULTS,
            ),
        ),
        _build_source_asset_job(
            source=sources["pf_listings"],
            name="pf_listings_plan_snapshot",
            raw_only=True,
            config=_pf_listings_config_mapping(
                sources["pf_listings"],
                defaults=PF_LISTINGS_PLAN_DEFAULTS,
            ),
        ),
        _build_source_asset_job(
            source=sources["pf_listings"],
            name="pf_listings_search_chunk",
            raw_only=True,
            config=_pf_listings_config_mapping(
                sources["pf_listings"],
                defaults=PF_LISTINGS_SEARCH_CHUNK_DEFAULTS,
            ),
        ),
        _build_source_asset_job(
            source=sources["pf_listings"],
            name="pf_listings_detail_chunk",
            raw_only=True,
            config=_pf_listings_config_mapping(
                sources["pf_listings"],
                defaults=PF_LISTINGS_DETAIL_CHUNK_DEFAULTS,
            ),
        ),
        define_asset_job(
            name="pf_listings_daily_latest_delta",
            # Listing facts and textual details are retained, but image/video assets are not
            # hydrated as part of the routine inventory refresh.
            selection=["pf_listings_raw", "pf_listings_bronze"],
            config=_pf_listings_latest_delta_config_mapping(
                sources["pf_listings"],
                defaults=PF_LISTINGS_LATEST_DELTA_DEFAULTS,
            ),
        ),
        _build_source_asset_job(
            source=sources["reelly_supply"],
            name="reelly_supply_archive_chunk",
            raw_only=True,
            config=_reelly_archive_config_mapping(sources["reelly_supply"]),
        ),
        define_asset_job(
            name="reelly_supply_daily_catalog_delta",
            selection=[
                "reelly_supply_raw",
                "reelly_supply_bronze",
                "reelly_supply_document_assets",
                "reelly_supply_project_media_assets",
            ],
            config=_reelly_catalog_delta_config_mapping(
                sources["reelly_supply"],
            ),
        ),
        _build_source_asset_job(
            source=sources["reelly_supply"],
            name="reelly_supply_daily_availability_delta",
            raw_only=False,
            config=_defaulted_raw_config_mapping(
                sources["reelly_supply"],
                defaults=REELLY_AVAILABILITY_DELTA_DEFAULTS,
            ),
        ),
        define_asset_job(
            name="news_feeds_poll_and_hydrate",
            selection=["news_feeds_raw", "news_thumbnail_assets"],
            config=_news_poll_and_hydrate_config_mapping(sources["news_feeds"]),
        ),
        _build_source_asset_job(
            source=sources["news_feeds"],
            name="news_feeds_manual_poll",
            raw_only=True,
        ),
        define_asset_job(
            name="news_thumbnail_assets_backfill",
            selection=["news_thumbnail_assets"],
            config=_news_thumbnail_asset_config_mapping(
                defaults=NewsThumbnailHydrationConfig(
                    lookback_days=0,
                    max_assets_per_run=100000,
                    resolve_missing_from_article_pages=True,
                ),
            ),
        ),
        define_asset_job(
            name="news_publish_backfill",
            selection=["news_thumbnail_assets", "news_publish"],
            config=_news_publish_config_mapping(
                defaults=NewsPublishConfig(ensure_schema=True),
            ),
        ),
        define_asset_job(
            name="reelly_supply_document_assets_backfill",
            selection=["reelly_supply_document_assets"],
            config=_reelly_document_asset_config_mapping(
                asset_name="reelly_supply_document_assets",
                defaults=ReellyDocumentAssetHydrationConfig(),
            ),
        ),
        define_asset_job(
            name="reelly_supply_project_media_assets_backfill",
            selection=["reelly_supply_project_media_assets"],
            config=_reelly_document_asset_config_mapping(
                asset_name="reelly_supply_project_media_assets",
                defaults=ReellyDocumentAssetHydrationConfig.model_validate(
                    REELLY_PROJECT_MEDIA_DEFAULTS
                ),
            ),
        ),
        define_asset_job(
            name="pf_listing_media_assets_backfill",
            selection=["pf_listing_media_assets"],
            config=_pf_listing_media_asset_config_mapping(
                defaults=PropertyFinderListingMediaHydrationConfig(),
            ),
        ),
        define_asset_job(
            name="silver_transactions_refresh",
            selection=["silver_transactions"],
        ),
        define_asset_job(
            name="silver_rent_contracts_refresh",
            selection=["silver_rent_contracts"],
        ),
        define_asset_job(
            name="silver_refresh",
            selection=["silver_transactions", "silver_rent_contracts"],
        ),
        define_asset_job(
            name="geography_crosswalk_refresh",
            selection=[
                "geo_location_nodes",
                "geo_location_closure",
                "geo_source_signatures",
                "geo_entity_links",
                "offplan_reelly_project_links",
            ],
        ),
    ]


def build_operational_schedules(
    jobs_by_name: Mapping[str, AssetJobDefinition],
) -> list[ScheduleDefinition]:
    schedule_specs = {
        **_DLD_OPEN_DATA_SCHEDULE_SPECS,
        "dxbi_transactions_daily_incremental": "0 6 * * *",
        "reelly_supply_daily_catalog_delta": "0 2 * * *",
        "reelly_supply_daily_availability_delta": "30 2 * * *",
        "pf_listings_daily_latest_delta": "0 3 * * *",
        "dda_planning_layers_weekly_full_refresh": "0 6 * * 0",
        "news_feeds_poll_and_hydrate": "*/15 * * * *",
        # Transaction silver runs after its 04:00 bronze ingestion.
        "silver_transactions_refresh": "0 6 * * *",
        # Rent silver runs after its 04:10 bronze ingestion.
        "silver_rent_contracts_refresh": "10 6 * * *",
        # The combined silver refresh remains available for full warehouse refreshes.
        "silver_refresh": "0 6 * * *",
    }
    return [
        ScheduleDefinition(
            name=f"{job_name}_schedule",
            job=jobs_by_name[job_name],
            cron_schedule=cron_schedule,
            execution_timezone=_DUBAI_TIMEZONE,
            default_status=DefaultScheduleStatus.STOPPED,
        )
        for job_name, cron_schedule in schedule_specs.items()
    ]


def _build_source_asset_job(
    *,
    source: SourceSpec,
    name: str,
    raw_only: bool,
    config: Mapping[str, Any] | ConfigMapping | None = None,
) -> AssetJobDefinition:
    return define_asset_job(
        name=name,
        selection=_source_asset_selection(source, raw_only=raw_only),
        config=config,
    )


def _source_asset_selection(source: SourceSpec, *, raw_only: bool) -> list[str]:
    selection = [_raw_asset_name(source)]
    if source.bronze_tables and not raw_only:
        selection.append(_bronze_asset_name(source))
    return selection


def _raw_asset_run_config(source: SourceSpec, source_config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ops": {
            _raw_asset_name(source): {
                "config": dict(source_config),
            }
        }
    }


def _config_fields(
    defaults: Any,
    field_specs: Sequence[tuple[str, Any, str]],
) -> dict[str, Field]:
    return {
        name: Field(
            config_type,
            default_value=_config_default(defaults, name, config_type),
            is_required=False,
            description=description,
        )
        for name, config_type, description in field_specs
    }


def _config_default(defaults: Any, name: str, config_type: Any) -> Any:
    value = getattr(defaults, name)
    if config_type == [str]:
        return list(value)
    return value


def _permissive_config_mapping(
    *,
    config_fn: Any,
    fields: Mapping[str, Any],
) -> ConfigMapping:
    return ConfigMapping(
        config_fn=config_fn,
        config_schema=Permissive(dict(fields)),
        receive_processed_config_values=True,
    )


def _overrides_field(description: str) -> Field:
    return Field(
        Permissive(),
        default_value={},
        is_required=False,
        description=description,
    )


def _reset_checkpoint_field(description: str) -> Field:
    return Field(
        bool,
        default_value=False,
        is_required=False,
        description=description,
    )


def _section_field(description: str) -> Field:
    return Field(
        Permissive(),
        default_value={},
        is_required=False,
        description=description,
    )


def _asset_config_mapping(
    *,
    asset_name: str,
    defaults: Any,
    field_specs: Sequence[tuple[str, Any, str]],
) -> ConfigMapping:
    def _map_asset_config(config: Mapping[str, Any]) -> dict[str, Any]:
        return {"ops": {asset_name: {"config": dict(config)}}}

    return _permissive_config_mapping(
        config_fn=_map_asset_config,
        fields=_config_fields(defaults, field_specs),
    )


def _dld_pulse_historic_bronze_config_mapping() -> ConfigMapping:
    return _asset_config_mapping(
        asset_name="dld_pulse_historic_bronze",
        defaults=DldPulseHistoricBronzeConfig(),
        field_specs=(
            ("manifest_key", StringSource, "R2 raw manifest key for the archived Pulse release."),
            ("batch_size", int, "ClickHouse insert batch size."),
            ("file_names", [str], "Optional canonical Pulse CSV names to load."),
        ),
    )


def _backfill_config_mapping(
    source: SourceSpec,
    *,
    defaults: Mapping[str, Any] | None = None,
) -> ConfigMapping:
    def _map_backfill_config(config: Mapping[str, Any]) -> dict[str, Any]:
        overrides = _source_overrides(config, reserved_keys={"start_date", "end_date"})
        source_config = {
            **dict(defaults or {}),
            **overrides,
            "mode": "backfill",
            "start_date": config["start_date"],
            "end_date": config["end_date"],
        }
        return _raw_asset_run_config(source, source_config)

    return _permissive_config_mapping(
        config_fn=_map_backfill_config,
        fields={
            "start_date": Field(StringSource, description="Inclusive backfill start date."),
            "end_date": Field(StringSource, description="Inclusive backfill end date."),
            "overrides": _overrides_field("Optional source-specific raw asset config overrides."),
        },
    )


def _defaulted_raw_config_mapping(
    source: SourceSpec,
    *,
    defaults: Mapping[str, Any],
) -> ConfigMapping:
    def _map_defaulted_config(config: Mapping[str, Any]) -> dict[str, Any]:
        overrides = _source_overrides(config)
        return _raw_asset_run_config(source, {**defaults, **overrides})

    return _permissive_config_mapping(
        config_fn=_map_defaulted_config,
        fields={
            "overrides": _overrides_field("Optional source-specific raw asset config overrides.")
        },
    )


def _reelly_archive_config_mapping(source: SourceSpec) -> ConfigMapping:
    def _map_reelly_config(config: Mapping[str, Any]) -> dict[str, Any]:
        overrides = _source_overrides(config, reserved_keys={"reset_checkpoint"})
        source_config = {**REELLY_ARCHIVE_CHUNK_DEFAULTS, **overrides}
        if config.get("reset_checkpoint"):
            source_config["reset_checkpoint"] = True
        return _raw_asset_run_config(source, source_config)

    return _permissive_config_mapping(
        config_fn=_map_reelly_config,
        fields={
            "reset_checkpoint": _reset_checkpoint_field(
                "Ignore a completed Reelly archive checkpoint and start a new pass."
            ),
            "overrides": _overrides_field("Optional Reelly raw asset config overrides."),
        },
    )


def _pf_listings_config_mapping(
    source: SourceSpec,
    *,
    defaults: Mapping[str, Any],
) -> ConfigMapping:
    def _map_pf_listings_config(config: Mapping[str, Any]) -> dict[str, Any]:
        overrides = _source_overrides(config, reserved_keys={"reset_checkpoint"})
        source_config = {**defaults, **overrides}
        if config.get("reset_checkpoint"):
            source_config["reset_checkpoint"] = True
        return _raw_asset_run_config(source, source_config)

    return _permissive_config_mapping(
        config_fn=_map_pf_listings_config,
        fields={
            "reset_checkpoint": _reset_checkpoint_field(
                "Ignore the relevant Property Finder checkpoint and start over."
            ),
            "overrides": _overrides_field("Optional Property Finder raw asset config overrides."),
        },
    )


def _pf_listings_latest_delta_config_mapping(
    source: SourceSpec,
    *,
    defaults: Mapping[str, Any],
) -> ConfigMapping:
    def _map_pf_listings_latest_delta_config(config: Mapping[str, Any]) -> dict[str, Any]:
        _reject_unexpected_top_level_keys(
            config,
            allowed_keys={"raw", "media"},
            context="pf_listings_daily_latest_delta",
        )
        raw_config = dict(config.get("raw") or {})
        raw_overrides = _source_overrides(raw_config, reserved_keys={"reset_checkpoint"})
        source_config = {**defaults, **raw_overrides}
        if raw_config.get("reset_checkpoint"):
            source_config["reset_checkpoint"] = True
        return {
            "ops": {
                _raw_asset_name(source): {"config": source_config},
            }
        }

    return _permissive_config_mapping(
        config_fn=_map_pf_listings_latest_delta_config,
        fields={
            "raw": _section_field("Property Finder latest-delta raw asset config overrides."),
            "media": _section_field("Property Finder listing media hydration config overrides."),
        },
    )


def _reelly_catalog_delta_config_mapping(source: SourceSpec) -> ConfigMapping:
    def _map_reelly_catalog_delta_config(config: Mapping[str, Any]) -> dict[str, Any]:
        _reject_unexpected_top_level_keys(
            config,
            allowed_keys={"raw", "documents", "project_media"},
            context="reelly_supply_daily_catalog_delta",
        )
        raw_config = dict(config.get("raw") or {})
        source_config = {
            **REELLY_CATALOG_DELTA_DEFAULTS,
            **_source_overrides(raw_config),
        }
        return {
            "ops": {
                _raw_asset_name(source): {"config": source_config},
                "reelly_supply_document_assets": {
                    "config": {"latest_manifest_count": 1, **dict(config.get("documents") or {})},
                },
                "reelly_supply_project_media_assets": {
                    "config": {
                        "latest_manifest_count": 1,
                        **dict(config.get("project_media") or {}),
                    },
                },
            }
        }

    return _permissive_config_mapping(
        config_fn=_map_reelly_catalog_delta_config,
        fields={
            "raw": _section_field("Reelly catalog-delta raw asset config overrides."),
            "documents": _section_field("Reelly document hydration config overrides."),
            "project_media": _section_field("Reelly project-media hydration config overrides."),
        },
    )


def _reelly_document_asset_config_mapping(
    *,
    asset_name: str,
    defaults: ReellyDocumentAssetHydrationConfig,
) -> ConfigMapping:
    return _asset_config_mapping(
        asset_name=asset_name,
        defaults=defaults,
        field_specs=(
            ("manifest_prefix", StringSource, "R2 prefix containing Reelly raw manifests."),
            ("target_prefix", StringSource, "R2 prefix for hydrated Reelly document assets."),
            (
                "inventory_prefix",
                StringSource,
                "R2 prefix for document asset inventory manifests.",
            ),
            ("max_assets_per_run", int, "Maximum document rows to process in one run."),
            ("overwrite_existing", bool, "Re-download and replace objects that already exist."),
            ("allowed_document_hosts", [str], "Allowlisted HTTPS hosts for document downloads."),
            ("max_document_mb", int, "Maximum single document download size in MiB."),
            ("request_pause_seconds", float, "Pause between document download attempts."),
            ("timeout_seconds", float, "HTTP timeout for document downloads."),
            ("max_concurrent_downloads", int, "Maximum concurrent document downloads."),
            (
                "include_project_documents",
                bool,
                "Read media rows from reelly_supply_project_documents.jsonl.",
            ),
            (
                "include_project_detail_media",
                bool,
                "Discover media URLs from reelly_supply_project_details.jsonl.",
            ),
            (
                "structured_target_keys",
                bool,
                "Include asset_type and field_path segments in R2 target keys.",
            ),
            ("inventory_file_name", StringSource, "Inventory manifest JSONL file name."),
            ("asset_type_allowlist", [str], "Optional list of asset_type values to hydrate."),
        ),
    )


def _pf_listing_media_asset_config_mapping(
    *,
    defaults: PropertyFinderListingMediaHydrationConfig,
) -> ConfigMapping:
    return _asset_config_mapping(
        asset_name="pf_listing_media_assets",
        defaults=defaults,
        field_specs=(
            (
                "manifest_prefix",
                StringSource,
                "R2 prefix containing Property Finder raw manifests.",
            ),
            (
                "target_prefix",
                StringSource,
                "R2 prefix for hydrated Property Finder listing media.",
            ),
            (
                "inventory_prefix",
                StringSource,
                "R2 prefix for Property Finder media inventory manifests.",
            ),
            ("inventory_file_name", StringSource, "Inventory manifest JSONL file name."),
            ("max_assets_per_run", int, "Maximum media assets to process in one run."),
            (
                "overwrite_existing",
                bool,
                "Re-download and replace media objects that already exist.",
            ),
            (
                "allowed_media_hosts",
                [str],
                "Allowlisted HTTPS hosts for Property Finder media downloads.",
            ),
            ("max_media_mb", int, "Maximum single media download size in MiB."),
            ("request_pause_seconds", float, "Pause between media download attempts."),
            ("timeout_seconds", float, "HTTP timeout for media downloads."),
            ("max_concurrent_downloads", int, "Maximum concurrent media downloads."),
            (
                "include_search_listing_media",
                bool,
                "Discover media from pf_listing_properties.jsonl.",
            ),
            ("include_detail_media", bool, "Discover media from pf_listing_details.jsonl."),
            (
                "asset_type_allowlist",
                [str],
                "Optional list of Property Finder media asset_type values to hydrate.",
            ),
        ),
    )


def _news_poll_and_hydrate_config_mapping(source: SourceSpec) -> ConfigMapping:
    def _map_news_poll_and_hydrate_config(config: Mapping[str, Any]) -> dict[str, Any]:
        _reject_unexpected_top_level_keys(
            config,
            allowed_keys={"raw", "thumbnails"},
            context="news_feeds_poll_and_hydrate",
        )
        return {
            "ops": {
                _raw_asset_name(source): {
                    "config": _source_overrides(dict(config.get("raw") or {})),
                },
                "news_thumbnail_assets": {
                    "config": {
                        "latest_manifest_count": 1,
                        **dict(config.get("thumbnails") or {}),
                    },
                },
            }
        }

    return _permissive_config_mapping(
        config_fn=_map_news_poll_and_hydrate_config,
        fields={
            "raw": _section_field("News raw polling config overrides."),
            "thumbnails": _section_field("News thumbnail hydration config overrides."),
        },
    )


def _news_thumbnail_asset_config_mapping(
    *,
    defaults: NewsThumbnailHydrationConfig,
) -> ConfigMapping:
    return _asset_config_mapping(
        asset_name="news_thumbnail_assets",
        defaults=defaults,
        field_specs=(
            ("manifest_prefix", StringSource, "R2 prefix containing news raw manifests."),
            ("target_prefix", StringSource, "R2 prefix for mirrored news thumbnails."),
            (
                "inventory_prefix",
                StringSource,
                "R2 prefix for news thumbnail inventory manifests.",
            ),
            ("inventory_file_name", StringSource, "Inventory manifest JSONL file name."),
            (
                "lookback_days",
                int,
                "Only hydrate article thumbnails discovered or published recently.",
            ),
            ("max_assets_per_run", int, "Maximum thumbnail candidates to process in one run."),
            ("overwrite_existing", bool, "Re-download and replace thumbnails that already exist."),
            ("allowed_thumbnail_hosts", [str], "Optional allowlist for thumbnail hosts."),
            ("max_thumbnail_mb", int, "Maximum single thumbnail download size in MiB."),
            (
                "resolve_missing_from_article_pages",
                bool,
                "Fetch article pages to discover missing thumbnail URLs.",
            ),
            ("request_pause_seconds", float, "Pause between thumbnail download attempts."),
            ("timeout_seconds", float, "HTTP timeout for thumbnail downloads."),
            ("max_concurrent_downloads", int, "Maximum concurrent thumbnail downloads."),
        ),
    )


def _news_publish_config_mapping(
    *,
    defaults: NewsPublishConfig,
) -> ConfigMapping:
    thumbnail_defaults = NewsThumbnailHydrationConfig()

    def _map_news_publish_config(config: Mapping[str, Any]) -> dict[str, Any]:
        if "thumbnail_inventory_prefix" in config:
            raise ValueError(
                "Use inventory_prefix for news_publish_backfill; it configures both "
                "thumbnail hydration inventory output and publish inventory input."
            )
        thumbnail_config = {
            key: config[key]
            for key in (
                "manifest_prefix",
                "target_prefix",
                "inventory_prefix",
                "inventory_file_name",
                "lookback_days",
                "max_assets_per_run",
                "overwrite_existing",
                "allowed_thumbnail_hosts",
                "max_thumbnail_mb",
                "resolve_missing_from_article_pages",
                "request_pause_seconds",
                "timeout_seconds",
                "max_concurrent_downloads",
            )
            if key in config
        }
        publish_config = {
            key: config[key]
            for key in (
                "manifest_prefix",
                "lookback_days",
                "max_articles_per_run",
                "platform_postgres_url",
                "ensure_schema",
                "dry_run",
            )
            if key in config
        }
        publish_config["thumbnail_inventory_prefix"] = config["inventory_prefix"]
        return {
            "ops": {
                "news_thumbnail_assets": {
                    "config": thumbnail_config,
                },
                "news_publish": {
                    "config": publish_config,
                },
            }
        }

    return _permissive_config_mapping(
        config_fn=_map_news_publish_config,
        fields={
            **_config_fields(
                defaults,
                (
                    (
                        "manifest_prefix",
                        StringSource,
                        "R2 prefix containing news raw manifests.",
                    ),
                    (
                        "lookback_days",
                        int,
                        "Only publish articles discovered or published recently.",
                    ),
                    ("max_articles_per_run", int, "Maximum article rows to upsert in one run."),
                    (
                        "platform_postgres_url",
                        StringSource,
                        "Override PLATFORM_POSTGRES_URL for this publish run.",
                    ),
                    (
                        "ensure_schema",
                        bool,
                        "Create or update news_articles columns before publishing.",
                    ),
                    ("dry_run", bool, "Build article payloads without writing to Postgres."),
                ),
            ),
            **_config_fields(
                thumbnail_defaults,
                (
                    ("target_prefix", StringSource, "R2 prefix for mirrored news thumbnails."),
                    (
                        "inventory_prefix",
                        StringSource,
                        "R2 prefix for news thumbnail inventory manifests.",
                    ),
                    (
                        "inventory_file_name",
                        StringSource,
                        "Inventory manifest JSONL file name.",
                    ),
                    (
                        "max_assets_per_run",
                        int,
                        "Maximum thumbnail candidates to process in one run.",
                    ),
                    (
                        "overwrite_existing",
                        bool,
                        "Re-download and replace thumbnails that already exist.",
                    ),
                    (
                        "allowed_thumbnail_hosts",
                        [str],
                        "Optional allowlist for thumbnail hosts.",
                    ),
                    (
                        "max_thumbnail_mb",
                        int,
                        "Maximum single thumbnail download size in MiB.",
                    ),
                    (
                        "resolve_missing_from_article_pages",
                        bool,
                        "Fetch article pages to discover missing thumbnail URLs.",
                    ),
                    (
                        "request_pause_seconds",
                        float,
                        "Pause between thumbnail download attempts.",
                    ),
                    ("timeout_seconds", float, "HTTP timeout for thumbnail downloads."),
                    (
                        "max_concurrent_downloads",
                        int,
                        "Maximum concurrent thumbnail downloads.",
                    ),
                ),
            ),
        },
    )


def _source_overrides(
    config: Mapping[str, Any],
    *,
    reserved_keys: set[str] | None = None,
) -> dict[str, Any]:
    reserved = {"overrides", *(reserved_keys or set())}
    direct_overrides = {key: value for key, value in config.items() if key not in reserved}
    nested_overrides = dict(config.get("overrides") or {})
    return {**direct_overrides, **nested_overrides}


def _reject_unexpected_top_level_keys(
    config: Mapping[str, Any],
    *,
    allowed_keys: set[str],
    context: str,
) -> None:
    unexpected_keys = sorted(set(config) - allowed_keys)
    if unexpected_keys:
        allowed = ", ".join(sorted(allowed_keys))
        unexpected = ", ".join(unexpected_keys)
        raise ValueError(
            f"{context} config keys must be nested under one of: {allowed}. "
            f"Unexpected top-level keys: {unexpected}."
        )
