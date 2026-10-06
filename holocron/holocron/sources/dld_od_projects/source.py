from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="projects",
    default_sort="ADOPTION_DATE_DESC",
    default_filters={
        "P_DATE_TYPE": "3",  # 3 = adoption date filter
        "P_PRJ_TYPE_ID": "",
        "P_PRJ_STATUS": "",
        "P_ZONE_ID": "",
        "P_AREA_ID": "",
    },
    description="DLD open-data project records.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
