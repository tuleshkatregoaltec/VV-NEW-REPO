#!/usr/bin/env python3
"""Refresh the canonical PF-to-registry crosswalk without a Dagster instance."""

from __future__ import annotations

import json

from holocron.assets.geography import (
    materialize_geo_entity_links,
    materialize_geo_location_closure,
    materialize_geo_location_nodes,
    materialize_offplan_reelly_project_links,
    materialize_geo_source_signatures,
)
from holocron.platform.clickhouse import ClickHouseClient
from holocron.platform.settings import settings


def main() -> None:
    client = ClickHouseClient(settings)
    result = {
        "nodes": materialize_geo_location_nodes(clickhouse=client),
        "closure_rows": materialize_geo_location_closure(clickhouse=client),
        "signatures": materialize_geo_source_signatures(clickhouse=client),
        "links": materialize_geo_entity_links(clickhouse=client),
        "offplan_reelly_links": materialize_offplan_reelly_project_links(clickhouse=client),
    }
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
