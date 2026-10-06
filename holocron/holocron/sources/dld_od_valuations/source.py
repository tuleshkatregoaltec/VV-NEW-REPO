from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="valuations",
    default_sort="INSTANCE_DATE_DESC",
    default_filters={
        "P_AREA_ID": "",
        "P_PROP_TYPE_ID": "",
    },
    description="DLD open-data valuation transaction records.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
