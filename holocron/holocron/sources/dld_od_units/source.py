from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="units",
    default_sort="UNIT_NUMBER_ASC",
    default_filters={
        "P_AREA_ID": "",
        "P_ZONE_ID": "",
        "P_IS_FREE_HOLD": "",
        "P_IS_LEASE_HOLD": "",
        "P_IS_OFFPLAN": "",
    },
    snapshot_omits_date_filters=True,
    description="DLD open-data unit inventory records.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
