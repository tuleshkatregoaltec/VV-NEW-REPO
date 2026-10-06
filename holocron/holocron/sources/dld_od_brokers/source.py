from __future__ import annotations

from holocron.sources.dld_open_data_shared import build_open_data_endpoint, build_open_data_source

ENDPOINT = build_open_data_endpoint(
    category="brokers",
    default_sort="BROKER_NUMBER_ASC",
    default_filters={
        "P_GENDER": "",
    },
    snapshot_omits_date_filters=True,
    description="DLD open-data broker records.",
)

SOURCE = build_open_data_source(endpoint=ENDPOINT, extractor_module=f"{__package__}.extract")
