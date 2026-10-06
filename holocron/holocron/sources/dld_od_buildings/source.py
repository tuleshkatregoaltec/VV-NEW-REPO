from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="buildings",
    default_sort="CREATION_DATE_DESC",
    default_filters={
        "P_IS_FREE_HOLD": "",
        "P_AREA_ID": "",
        "P_ZONE_ID": "",
        "P_IS_LEASE_HOLD": "",
        "P_IS_OFFPLAN": "",
    },
    snapshot_blank_date_filters=True,
    description="DLD open-data building inventory records.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
