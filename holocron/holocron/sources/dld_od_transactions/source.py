from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="transactions",
    default_sort="INSTANCE_DATE_DESC",
    default_filters={
        "P_GROUP_ID": "",
        "P_IS_OFFPLAN": "",
        "P_IS_FREE_HOLD": "",
        "P_AREA_ID": "",
        "P_USAGE_ID": "",
        "P_PROP_TYPE_ID": "",
    },
    request_to_date_offset_days=1,
    row_date_field="INSTANCE_DATE",
    description="DLD open-data sale, mortgage, and gift transactions.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
