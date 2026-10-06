import pytest
from dagster import (
    AssetsDefinition,
    DagsterInvalidConfigError,
    DefaultScheduleStatus,
    Definitions,
    JobDefinition,
    ScheduleDefinition,
    validate_run_config,
)
from typing import Any, cast

from holocron.contracts import BronzeTable, RawRelease, SourceSpec
from holocron.definitions import defs
from holocron.orchestration.factory import (
    _DLD_OPEN_DATA_JOB_SPECS,
    _run_bronze_loader,
    build_assets_for_source,
)

DLD_OD_CATEGORIES = tuple(category for category, _, _, _ in _DLD_OPEN_DATA_JOB_SPECS)
DLD_OD_RAW_ASSETS = {f"dld_od_{category}_raw" for category in DLD_OD_CATEGORIES}
DLD_OD_BRONZE_ASSETS = {f"dld_od_{category}_bronze" for category in DLD_OD_CATEGORIES}
DLD_OD_INCREMENTAL_JOBS = {f"dld_od_{category}_daily_incremental" for category in DLD_OD_CATEGORIES}
DLD_OD_MANUAL_BACKFILL_JOBS = {
    f"dld_od_{category}_manual_backfill" for category in DLD_OD_CATEGORIES
}
DLD_OD_MANUAL_SNAPSHOT_JOBS = {
    f"dld_od_{category}_manual_snapshot" for category in DLD_OD_CATEGORIES
}
DLD_OD_MANUAL_JOBS = DLD_OD_MANUAL_BACKFILL_JOBS | DLD_OD_MANUAL_SNAPSHOT_JOBS
DLD_OD_INCREMENTAL_CRONS = {category: cron for category, cron, _, _ in _DLD_OPEN_DATA_JOB_SPECS}


def test_definitions_validate_loadable() -> None:
    Definitions.validate_loadable(defs)


def test_definitions_expose_source_assets() -> None:
    asset_keys = {asset.key.to_user_string() for asset in _defs_assets()}

    assert asset_keys == {
        "bayut_listings_raw",
        "dda_planning_layers_raw",
        "dda_planning_layers_bronze",
        *DLD_OD_RAW_ASSETS,
        *DLD_OD_BRONZE_ASSETS,
        "dld_mashrooi_raw",
        "dld_pulse_historic_raw",
        "dld_pulse_historic_bronze",
        "dxbi_transactions_raw",
        "dxbi_transactions_bronze",
        "news_feeds_raw",
        "news_thumbnail_assets",
        "news_publish",
        "pf_locations_raw",
        "pf_locations_bronze",
        "pf_listings_raw",
        "pf_listings_bronze",
        "pf_listing_media_assets",
        "reelly_supply_raw",
        "reelly_supply_bronze",
        "reelly_supply_document_assets",
        "reelly_supply_project_media_assets",
        "silver_transactions",
        "silver_rent_contracts",
        "geo_location_nodes",
        "geo_location_closure",
        "geo_source_signatures",
        "geo_entity_links",
        "offplan_reelly_project_links",
    }


def test_assets_use_provider_groups() -> None:
    group_by_asset_key = {
        key.to_user_string(): group_name
        for asset in _defs_assets()
        for key, group_name in asset.group_names_by_key.items()
    }

    assert group_by_asset_key["dld_od_transactions_raw"] == "dld"
    assert group_by_asset_key["dld_od_transactions_bronze"] == "dld"
    assert group_by_asset_key["dld_mashrooi_raw"] == "dld"
    assert group_by_asset_key["dld_pulse_historic_raw"] == "dld"
    assert group_by_asset_key["dld_pulse_historic_bronze"] == "dld"
    assert group_by_asset_key["pf_locations_bronze"] == "propertyfinder"
    assert group_by_asset_key["pf_listings_raw"] == "propertyfinder"
    assert group_by_asset_key["pf_listings_bronze"] == "propertyfinder"
    assert group_by_asset_key["reelly_supply_bronze"] == "reelly"
    assert group_by_asset_key["pf_listing_media_assets"] == "propertyfinder"
    assert group_by_asset_key["reelly_supply_document_assets"] == "reelly"
    assert group_by_asset_key["news_publish"] == "news"


def test_definitions_expose_named_operational_jobs() -> None:
    assert {job.name for job in _defs_jobs()} == {
        *DLD_OD_INCREMENTAL_JOBS,
        "dxbi_transactions_daily_incremental",
        "dda_planning_layers_weekly_full_refresh",
        *DLD_OD_MANUAL_BACKFILL_JOBS,
        *DLD_OD_MANUAL_SNAPSHOT_JOBS,
        "dxbi_transactions_manual_backfill",
        "dda_planning_layers_manual_full_refresh",
        "dld_pulse_historic_archive",
        "dld_pulse_historic_bronze_backfill",
        "pf_locations_manual_full_fetch",
        "pf_listings_manual_snapshot",
        "pf_listings_plan_snapshot",
        "pf_listings_search_chunk",
        "pf_listings_detail_chunk",
        "pf_listings_daily_latest_delta",
        "news_feeds_poll_and_hydrate",
        "news_feeds_manual_poll",
        "news_thumbnail_assets_backfill",
        "news_publish_backfill",
        "reelly_supply_archive_chunk",
        "reelly_supply_daily_catalog_delta",
        "reelly_supply_daily_availability_delta",
        "reelly_supply_document_assets_backfill",
        "reelly_supply_project_media_assets_backfill",
        "pf_listing_media_assets_backfill",
        "silver_transactions_refresh",
        "silver_rent_contracts_refresh",
        "silver_refresh",
        "geography_crosswalk_refresh",
    }


def test_definitions_expose_only_recurring_operational_schedules() -> None:
    assert {
        schedule.name: (
            schedule.job_name,
            schedule.cron_schedule,
            schedule.execution_timezone,
            schedule.default_status,
        )
        for schedule in _defs_schedules()
    } == {
        **{
            f"dld_od_{category}_daily_incremental_schedule": (
                f"dld_od_{category}_daily_incremental",
                cron,
                "Asia/Dubai",
                DefaultScheduleStatus.STOPPED,
            )
            for category, cron in DLD_OD_INCREMENTAL_CRONS.items()
        },
        "dxbi_transactions_daily_incremental_schedule": (
            "dxbi_transactions_daily_incremental",
            "0 6 * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "reelly_supply_daily_catalog_delta_schedule": (
            "reelly_supply_daily_catalog_delta",
            "0 2 * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "reelly_supply_daily_availability_delta_schedule": (
            "reelly_supply_daily_availability_delta",
            "30 2 * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "pf_listings_daily_latest_delta_schedule": (
            "pf_listings_daily_latest_delta",
            "0 3 * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "dda_planning_layers_weekly_full_refresh_schedule": (
            "dda_planning_layers_weekly_full_refresh",
            "0 6 * * 0",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "news_feeds_poll_and_hydrate_schedule": (
            "news_feeds_poll_and_hydrate",
            "*/15 * * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "silver_refresh_schedule": (
            "silver_refresh",
            "0 6 * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "silver_transactions_refresh_schedule": (
            "silver_transactions_refresh",
            "0 6 * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
        "silver_rent_contracts_refresh_schedule": (
            "silver_rent_contracts_refresh",
            "10 6 * * *",
            "Asia/Dubai",
            DefaultScheduleStatus.STOPPED,
        ),
    }


def test_operational_jobs_select_expected_assets() -> None:
    expected_assets = {
        **{
            f"dld_od_{category}_daily_incremental": {
                f"dld_od_{category}_raw",
                f"dld_od_{category}_bronze",
            }
            for category in DLD_OD_CATEGORIES
        },
        "dxbi_transactions_daily_incremental": {
            "dxbi_transactions_raw",
            "dxbi_transactions_bronze",
        },
        "dda_planning_layers_weekly_full_refresh": {
            "dda_planning_layers_raw",
            "dda_planning_layers_bronze",
        },
        "reelly_supply_daily_availability_delta": {
            "reelly_supply_raw",
            "reelly_supply_bronze",
        },
        "reelly_supply_daily_catalog_delta": {
            "reelly_supply_raw",
            "reelly_supply_bronze",
            "reelly_supply_document_assets",
            "reelly_supply_project_media_assets",
        },
        "pf_listings_daily_latest_delta": {
            "pf_listings_raw",
            "pf_listings_bronze",
        },
        "news_feeds_poll_and_hydrate": {"news_feeds_raw", "news_thumbnail_assets"},
        "geography_crosswalk_refresh": {
            "geo_location_nodes",
            "geo_location_closure",
            "geo_source_signatures",
            "geo_entity_links",
            "offplan_reelly_project_links",
        },
        "dda_planning_layers_manual_full_refresh": {
            "dda_planning_layers_raw",
            "dda_planning_layers_bronze",
        },
        "dld_pulse_historic_archive": {"dld_pulse_historic_raw"},
        "dld_pulse_historic_bronze_backfill": {"dld_pulse_historic_bronze"},
        "pf_locations_manual_full_fetch": {"pf_locations_raw", "pf_locations_bronze"},
        "pf_listings_manual_snapshot": {"pf_listings_raw", "pf_listings_bronze"},
        "pf_listings_plan_snapshot": {"pf_listings_raw"},
        "pf_listings_search_chunk": {"pf_listings_raw"},
        "pf_listings_detail_chunk": {"pf_listings_raw"},
        **{
            f"dld_od_{category}_manual_backfill": {f"dld_od_{category}_raw"}
            for category in DLD_OD_CATEGORIES
        },
        **{
            f"dld_od_{category}_manual_snapshot": {f"dld_od_{category}_raw"}
            for category in DLD_OD_CATEGORIES
        },
        "dxbi_transactions_manual_backfill": {"dxbi_transactions_raw"},
        "pf_listing_media_assets_backfill": {"pf_listing_media_assets"},
        "news_feeds_manual_poll": {"news_feeds_raw"},
        "news_thumbnail_assets_backfill": {"news_thumbnail_assets"},
        "news_publish_backfill": {"news_thumbnail_assets", "news_publish"},
        "reelly_supply_archive_chunk": {"reelly_supply_raw"},
        "reelly_supply_document_assets_backfill": {"reelly_supply_document_assets"},
        "reelly_supply_project_media_assets_backfill": {"reelly_supply_project_media_assets"},
    }
    for job_name, assets in expected_assets.items():
        assert _selected_assets(job_name) == assets


def test_manual_one_shot_jobs_do_not_have_schedules() -> None:
    scheduled_jobs = {schedule.job_name for schedule in _defs_schedules()}
    assert (
        not {
            *DLD_OD_MANUAL_JOBS,
            "dxbi_transactions_manual_backfill",
            "dda_planning_layers_manual_full_refresh",
            "dld_pulse_historic_archive",
            "dld_pulse_historic_bronze_backfill",
            "pf_locations_manual_full_fetch",
            "pf_listings_manual_snapshot",
            "pf_listings_plan_snapshot",
            "pf_listings_search_chunk",
            "pf_listings_detail_chunk",
            "pf_listing_media_assets_backfill",
            "news_feeds_manual_poll",
            "news_thumbnail_assets_backfill",
            "news_publish_backfill",
            "reelly_supply_archive_chunk",
            "reelly_supply_document_assets_backfill",
            "reelly_supply_project_media_assets_backfill",
        }
        & scheduled_jobs
    )


@pytest.mark.parametrize(
    ("job_name", "raw_asset_name"),
    [
        *[
            (f"dld_od_{category}_manual_backfill", f"dld_od_{category}_raw")
            for category in DLD_OD_CATEGORIES
        ],
        ("dxbi_transactions_manual_backfill", "dxbi_transactions_raw"),
    ],
)
def test_manual_backfill_jobs_require_dates_and_inject_backfill_mode(
    job_name: str,
    raw_asset_name: str,
) -> None:
    job = defs.resolve_job_def(job_name)

    with pytest.raises(DagsterInvalidConfigError):
        validate_run_config(job, {"start_date": "2026-01-01"})

    backfill_dates = {"start_date": "2026-01-01", "end_date": "2026-01-31"}
    raw_config = _op_config(job_name, raw_asset_name, {**backfill_dates, "max_pages": 3})
    _assert_config_contains(
        raw_config,
        {"mode": "backfill", **backfill_dates, "max_pages": 3},
    )

    if job_name.startswith("dld_od_"):
        default_raw_config = _op_config(job_name, raw_asset_name, backfill_dates)
        _assert_config_contains(
            default_raw_config,
            {"page_size": 10000, "max_pages": 1, "slice_days": 366},
        )
        if job_name == "dld_od_rents_manual_backfill":
            _assert_config_contains(
                default_raw_config,
                {"start_date": "2026-01-01", "filters": {"P_DATE_TYPE": "1"}},
            )


def test_manual_one_shot_jobs_default_raw_config() -> None:
    config_cases = (
        (
            "dld_od_rents_manual_snapshot",
            "dld_od_rents_raw",
            {},
            {
                "mode": "snapshot",
                "page_size": 10000,
                "max_pages": 1,
                "slice_days": 366,
                "start_date": "2017-01-01",
                "filters": {"P_DATE_TYPE": "1"},
            },
        ),
        (
            "dld_od_rents_daily_incremental",
            "dld_od_rents_raw",
            {},
            {
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
            },
        ),
        (
            "dld_pulse_historic_archive",
            "dld_pulse_historic_raw",
            {},
            {"input_dir": "pulse-data"},
        ),
        (
            "dld_pulse_historic_bronze_backfill",
            "dld_pulse_historic_bronze",
            {},
            {
                "manifest_key": (
                    "raw/source=dld_pulse_historic/manifests/dld-pulse-historic-2026-05-16.json"
                ),
                "batch_size": 5000,
                "file_names": [],
            },
        ),
        (
            "reelly_supply_archive_chunk",
            "reelly_supply_raw",
            {"page_cursor": 7},
            {
                "pages_per_run": 5,
                "page_cursor": 7,
                "download_documents": False,
                "download_all_project_docs": True,
            },
        ),
        (
            "reelly_supply_daily_availability_delta",
            "reelly_supply_raw",
            {},
            {"mode": "availability_delta", "try_matrix_availability": True},
        ),
        (
            "reelly_supply_document_assets_backfill",
            "reelly_supply_document_assets",
            {},
            {
                "manifest_prefix": "raw/source=reelly_supply/manifests/",
                "target_prefix": "media/reelly_supply/documents",
                "max_assets_per_run": 500,
                "overwrite_existing": False,
                "include_project_documents": True,
                "include_project_detail_media": False,
                "structured_target_keys": False,
                "max_concurrent_downloads": 1,
            },
        ),
        (
            "reelly_supply_project_media_assets_backfill",
            "reelly_supply_project_media_assets",
            {},
            {
                "manifest_prefix": "raw/source=reelly_supply/manifests/",
                "target_prefix": "media/reelly_supply/project_media",
                "inventory_prefix": "raw/source=reelly_supply/project_media_asset_manifests",
                "inventory_file_name": "reelly_supply_project_media_assets.jsonl",
                "include_project_documents": False,
                "include_project_detail_media": True,
                "structured_target_keys": True,
                "max_concurrent_downloads": 8,
            },
        ),
        (
            "pf_listings_manual_snapshot",
            "pf_listings_raw",
            {},
            {
                "mode": "snapshot",
                "max_planned_queries": 12000,
                "max_search_pages_per_run": 50000,
                "max_details_per_run": 100000,
                "fetch_details": True,
                "split_by_location": True,
            },
        ),
        (
            "pf_listings_plan_snapshot",
            "pf_listings_raw",
            {},
            {
                "mode": "plan",
                "max_planned_queries": 25000,
                "max_plan_queries_per_run": 500,
                "max_results_per_query": 750,
                "max_partition_depth": 10,
            },
        ),
        (
            "pf_listings_search_chunk",
            "pf_listings_raw",
            {},
            {"mode": "search", "max_search_pages_per_run": 500, "fetch_details": False},
        ),
        (
            "pf_listings_detail_chunk",
            "pf_listings_raw",
            {},
            {"mode": "details", "max_details_per_run": 1000},
        ),
        (
            "pf_listing_media_assets_backfill",
            "pf_listing_media_assets",
            {},
            {
                "manifest_prefix": "raw/source=pf_listings/manifests/",
                "target_prefix": "media/pf_listings/listing_media",
                "inventory_prefix": "raw/source=pf_listings/listing_media_asset_manifests",
                "inventory_file_name": "pf_listing_media_assets.jsonl",
                "max_assets_per_run": 100000,
                "overwrite_existing": False,
                "include_search_listing_media": True,
                "include_detail_media": True,
                "max_concurrent_downloads": 8,
            },
        ),
        (
            "news_thumbnail_assets_backfill",
            "news_thumbnail_assets",
            {},
            {
                "manifest_prefix": "raw/source=news_feeds/manifests/",
                "target_prefix": "media/news/thumbnails",
                "inventory_prefix": "raw/source=news_feeds/thumbnail_asset_manifests",
                "inventory_file_name": "news_thumbnail_assets.jsonl",
                "lookback_days": 0,
                "max_assets_per_run": 100000,
                "overwrite_existing": False,
                "max_concurrent_downloads": 8,
                "resolve_missing_from_article_pages": True,
            },
        ),
    )
    configs = {}
    for job_name, op_name, run_config, expected in config_cases:
        config = _op_config(job_name, op_name, run_config)
        _assert_config_contains(config, expected)
        configs[(job_name, op_name)] = config

    for job_name, raw_asset_name in (
        ("dld_od_lands_daily_incremental", "dld_od_lands_raw"),
        ("dld_od_units_daily_incremental", "dld_od_units_raw"),
        ("dld_od_brokers_daily_incremental", "dld_od_brokers_raw"),
    ):
        dld_od_inventory_incremental_config = _op_config(job_name, raw_asset_name)
        assert dld_od_inventory_incremental_config["mode"] == "incremental"

    reelly_catalog_run_config = _run_config("reelly_supply_daily_catalog_delta")
    reelly_catalog_config = _run_op_config(reelly_catalog_run_config, "reelly_supply_raw")
    _assert_config_contains(
        reelly_catalog_config,
        {
            "mode": "catalog_delta",
            "pages_per_run": 200,
            "download_documents": False,
            "fetch_documents_for_delta": True,
            "detail_audit_limit": 50,
        },
    )
    _assert_config_contains(
        _run_op_config(reelly_catalog_run_config, "reelly_supply_document_assets"),
        {"latest_manifest_count": 1},
    )
    _assert_config_contains(
        _run_op_config(reelly_catalog_run_config, "reelly_supply_project_media_assets"),
        {"latest_manifest_count": 1},
    )
    reelly_catalog_override_config = _run_config(
        "reelly_supply_daily_catalog_delta",
        {
            "raw": {"pages_per_run": 9},
            "documents": {"max_assets_per_run": 3},
            "project_media": {"max_assets_per_run": 4},
        },
    )
    _assert_config_contains(
        _run_op_config(reelly_catalog_override_config, "reelly_supply_raw"),
        {"pages_per_run": 9},
    )
    _assert_config_contains(
        _run_op_config(reelly_catalog_override_config, "reelly_supply_document_assets"),
        {"max_assets_per_run": 3},
    )
    _assert_config_contains(
        _run_op_config(reelly_catalog_override_config, "reelly_supply_project_media_assets"),
        {"max_assets_per_run": 4},
    )

    reelly_media_config = configs[
        "reelly_supply_project_media_assets_backfill", "reelly_supply_project_media_assets"
    ]
    assert "brochure" not in reelly_media_config["asset_type_allowlist"]
    assert "profile_image" not in reelly_media_config["asset_type_allowlist"]
    assert {"cover_image", "developer_logo", "floorplan"} <= set(
        reelly_media_config["asset_type_allowlist"]
    )

    pf_latest_delta_run_config = _run_config("pf_listings_daily_latest_delta")
    pf_latest_delta_config = _run_op_config(pf_latest_delta_run_config, "pf_listings_raw")
    _assert_config_contains(
        pf_latest_delta_config,
        {
            "mode": "latest_delta",
            "max_pages_per_query": 5,
            "max_search_pages_per_run": 40,
            "latest_delta_stop_after_seen_pages": 2,
            "latest_delta_bootstrap_details": False,
        },
    )
    pf_latest_delta_override_config = _run_config(
        "pf_listings_daily_latest_delta",
        {
            "raw": {"max_details_per_run": 25},
        },
    )
    _assert_config_contains(
        _run_op_config(pf_latest_delta_override_config, "pf_listings_raw"),
        {"max_details_per_run": 25},
    )

    pf_media_config = configs[("pf_listing_media_assets_backfill", "pf_listing_media_assets")]
    assert "static.shared.propertyfinder.ae" in pf_media_config["allowed_media_hosts"]

    news_publish_config = _run_config("news_publish_backfill")
    _assert_config_contains(
        _run_op_config(news_publish_config, "news_thumbnail_assets"),
        {"lookback_days": 3, "resolve_missing_from_article_pages": False},
    )
    _assert_config_contains(
        _run_op_config(news_publish_config, "news_publish"),
        {
            "manifest_prefix": "raw/source=news_feeds/manifests/",
            "thumbnail_inventory_prefix": "raw/source=news_feeds/thumbnail_asset_manifests",
            "lookback_days": 3,
            "max_articles_per_run": 1000,
            "ensure_schema": True,
            "dry_run": False,
        },
    )
    custom_news_publish_config = _run_config(
        "news_publish_backfill",
        {"inventory_prefix": "raw/source=news_feeds/custom_thumbnail_inventory"},
    )
    _assert_config_contains(
        _run_op_config(custom_news_publish_config, "news_thumbnail_assets"),
        {"inventory_prefix": "raw/source=news_feeds/custom_thumbnail_inventory"},
    )
    _assert_config_contains(
        _run_op_config(custom_news_publish_config, "news_publish"),
        {"thumbnail_inventory_prefix": "raw/source=news_feeds/custom_thumbnail_inventory"},
    )

    news_poll_config = _run_config("news_feeds_poll_and_hydrate")
    _assert_config_contains(
        _run_op_config(news_poll_config, "news_thumbnail_assets"),
        {"latest_manifest_count": 1},
    )
    custom_news_poll_config = _run_config(
        "news_feeds_poll_and_hydrate",
        {
            "raw": {"max_entries_per_feed": 5},
            "thumbnails": {"latest_manifest_count": 2},
        },
    )
    _assert_config_contains(
        _run_op_config(custom_news_poll_config, "news_feeds_raw"),
        {"max_entries_per_feed": 5},
    )
    _assert_config_contains(
        _run_op_config(custom_news_poll_config, "news_thumbnail_assets"),
        {"latest_manifest_count": 2},
    )


def test_bronze_loader_routes_through_source_metadata() -> None:
    calls = []

    def extractor() -> RawRelease:
        return RawRelease(
            source="synthetic_source",
            run_id="run-1",
            extract_date="2026-05-01",
            created_at="2026-05-01T00:00:00+00:00",
            files=(),
        )

    def bronze_loader(**kwargs):
        calls.append(kwargs)
        return {
            "run_id": "run-1",
            "table_count": 1,
            "total_rows": 2,
            "table_row_counts": {"synthetic_bronze": 2},
        }

    source = SourceSpec(
        name="synthetic_source",
        provider="synthetic",
        extractor=extractor,
        bronze_loader=bronze_loader,
        bronze_tables=(BronzeTable(name="synthetic_bronze"),),
    )

    class Resource:
        def __init__(self, client: str) -> None:
            self._client = client

        def client(self) -> str:
            return self._client

    result = _run_bronze_loader(
        source=source,
        raw_manifest={"source": "synthetic_source", "run_id": "run-1"},
        object_storage=Resource("s3-client"),
        clickhouse=Resource("clickhouse-client"),
    )

    assert calls == [
        {
            "raw_manifest": {"source": "synthetic_source", "run_id": "run-1"},
            "s3": "s3-client",
            "clickhouse": "clickhouse-client",
        }
    ]
    assert result.metadata is not None
    assert result.metadata["source"] == "synthetic_source"
    assert result.metadata["run_id"] == "run-1"


def test_bronze_loader_rejects_smoke_raw_manifest() -> None:
    def extractor() -> RawRelease:
        return RawRelease(
            source="synthetic_source",
            run_id="run-1",
            extract_date="2026-05-01",
            created_at="2026-05-01T00:00:00+00:00",
            files=(),
        )

    source = SourceSpec(
        name="synthetic_source",
        provider="synthetic",
        extractor=extractor,
        bronze_loader=lambda **kwargs: {},
        bronze_tables=(BronzeTable(name="synthetic_bronze"),),
    )

    class Resource:
        def client(self) -> str:
            return "client"

    with pytest.raises(ValueError, match="Smoke raw manifest"):
        _run_bronze_loader(
            source=source,
            raw_manifest={
                "source": "synthetic_source",
                "run_id": "run-1",
                "metadata": {"dataset_kind": "smoke"},
            },
            object_storage=Resource(),
            clickhouse=Resource(),
        )


def test_source_with_bronze_tables_requires_bronze_loader() -> None:
    def extractor() -> RawRelease:
        return RawRelease(
            source="bad_source",
            run_id="run-1",
            extract_date="2026-05-01",
            created_at="2026-05-01T00:00:00+00:00",
            files=(),
        )

    source = SourceSpec(
        name="bad_source",
        provider="synthetic",
        extractor=extractor,
        bronze_tables=(BronzeTable(name="bad_bronze"),),
    )

    with pytest.raises(ValueError, match="declares bronze tables without a bronze loader"):
        build_assets_for_source(source)


def _defs_assets() -> list[AssetsDefinition]:
    return cast(list[AssetsDefinition], list(defs.assets or []))


def _defs_jobs() -> list[JobDefinition]:
    return cast(list[JobDefinition], list(defs.jobs or []))


def _defs_schedules() -> list[ScheduleDefinition]:
    return cast(list[ScheduleDefinition], list(defs.schedules or []))


def _run_config(job_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(validate_run_config(defs.resolve_job_def(job_name), config or {}))


def _op_config(job_name: str, op_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _run_op_config(_run_config(job_name, config), op_name)


def _run_op_config(run_config: dict[str, Any], op_name: str) -> dict[str, Any]:
    return run_config["ops"][op_name]["config"]


def _assert_config_contains(config: dict[str, Any], expected: dict[str, Any]) -> None:
    assert {key: config[key] for key in expected} == expected


def _selected_assets(job_name: str) -> set[str]:
    job = defs.resolve_job_def(job_name)
    return {key.to_user_string() for key in job.asset_layer.selected_asset_keys}
