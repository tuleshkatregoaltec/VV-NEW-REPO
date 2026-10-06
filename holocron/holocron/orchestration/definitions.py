from __future__ import annotations

from dagster import Definitions

from holocron.orchestration.factory import (
    build_assets_for_source,
    build_dld_pulse_historic_assets,
    build_geography_assets,
    build_news_feed_assets,
    build_operational_jobs,
    build_operational_schedules,
    build_pf_listing_media_assets,
    build_reelly_document_assets,
    build_silver_assets,
)
from holocron.platform.resources import ClickHouseResource, ObjectStorageResource
from holocron.sources import registry

_assets = []
for _source in registry.list_sources():
    _assets.extend(build_assets_for_source(_source))
_assets.extend(build_pf_listing_media_assets())
_assets.extend(build_reelly_document_assets())
_assets.extend(build_news_feed_assets())
_assets.extend(build_dld_pulse_historic_assets())
_assets.extend(build_silver_assets())
_assets.extend(build_geography_assets())
_sources_by_name = {_source.name: _source for _source in registry.list_sources()}
_jobs = build_operational_jobs(_sources_by_name)
_schedules = build_operational_schedules({_job.name: _job for _job in _jobs})

defs = Definitions(
    assets=_assets,
    jobs=_jobs,
    schedules=_schedules,
    resources={
        "object_storage": ObjectStorageResource(),
        "clickhouse": ClickHouseResource(),
    },
)
