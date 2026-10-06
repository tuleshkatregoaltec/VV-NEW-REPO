"""Bayut active-listing collection source.

This source deliberately requires normal, permitted browser access.  It does
not attempt to solve or evade Bayut's CAPTCHA challenge.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from holocron.contracts import SourceSpec
from holocron.pydantic_helpers import CsvTuple, HolocronModel, NonBlankStr
from holocron.sources.entrypoints import lazy_extractor

BAYUT_LISTINGS_SOURCE_NAME = "bayut_listings"
BAYUT_PROVIDER = "bayut"
BAYUT_BASE_URL = "https://www.bayut.com"
BAYUT_DEFAULT_SEARCH_PATHS = (
    "/for-sale/property/dubai/",
    "/to-rent/property/dubai/",
)


class BayutListingsConfig(HolocronModel):
    base_url: NonBlankStr = BAYUT_BASE_URL
    search_paths: CsvTuple = BAYUT_DEFAULT_SEARCH_PATHS
    start_page: int = Field(default=1, ge=1)
    max_pages_per_search: int = Field(default=1, ge=1, le=500)
    request_pause_seconds: float = Field(default=3, ge=0)
    timeout_seconds: float = Field(default=60, ge=1)
    headless: bool = True
    chrome_path: str = ""
    storage_state_path: str = ""
    block_media_requests: bool = True

    @model_validator(mode="after")
    def validate_config(self) -> "BayutListingsConfig":
        if not self.search_paths:
            raise ValueError("search_paths must include at least one Bayut search path")
        return self


extract_release = lazy_extractor(f"{__package__}.extract")

SOURCE = SourceSpec(
    name=BAYUT_LISTINGS_SOURCE_NAME,
    provider=BAYUT_PROVIDER,
    extractor=extract_release,
    checkpoint_strategy="page_cursor",
    cadence="manual",
    description=(
        "Access-gated Bayut active-listing search snapshots. Stops on CAPTCHA; "
        "requires normal, authorised browser access."
    ),
)
