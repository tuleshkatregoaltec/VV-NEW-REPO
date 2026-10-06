from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="developers",
    default_sort="REGISTRATION_DATE_DESC",
    default_filters={
        "P_NAME": "",
    },
    description="DLD open-data developer records.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
