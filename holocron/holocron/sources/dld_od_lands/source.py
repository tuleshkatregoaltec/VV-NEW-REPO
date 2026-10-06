from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="lands",
    default_sort="AREA_EN_ASC",
    default_filters={
        "P_PROJECT": "",
        "P_MASTER_PROJECT": "",
        "P_LAND_TYPE_ID": "",
        "P_AREA_ID": "",
        "P_ZONE_ID": "",
        "P_IS_FREE_HOLD": "",
        "P_PROP_SB_TYPE_ID": "",
    },
    snapshot_omits_date_filters=True,
    description="DLD open-data land inventory records.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
