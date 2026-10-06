from __future__ import annotations

from pydantic import Field, model_validator

from holocron.contracts import BronzeTable, SourceSpec
from holocron.pydantic_helpers import CsvIntTuple, HolocronModel, NonBlankStr
from holocron.sources.entrypoints import lazy_bronze_loader, lazy_extractor
from holocron.sources.pf_listings.source import (
    PF_BASE_URL,
    PF_DUBAI_LOCATION_ID,
    PF_LISTING_CATEGORY_IDS,
    PF_PROVIDER,
    PF_STATIC_ASSETS_BASE_URL,
)

PF_LOCATIONS_SOURCE_NAME = "pf_locations"


class PropertyFinderLocationsConfig(HolocronModel):
    base_url: NonBlankStr = PF_BASE_URL
    static_assets_base_url: NonBlankStr = PF_STATIC_ASSETS_BASE_URL
    locale: NonBlankStr = "en"
    country_code: NonBlankStr = "ae"
    categories: CsvIntTuple = PF_LISTING_CATEGORY_IDS
    location_page_limit: int = Field(default=500, ge=1, le=500)
    max_location_pages: int = Field(default=40, ge=1)
    only_dubai: bool = True
    dubai_location_id: NonBlankStr = PF_DUBAI_LOCATION_ID
    request_pause_seconds: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=60, ge=1)

    @model_validator(mode="after")
    def validate_config(self) -> "PropertyFinderLocationsConfig":
        if not self.categories:
            raise ValueError("categories must include at least one Property Finder category id")
        if any(category <= 0 for category in self.categories):
            raise ValueError("categories must be positive integers")
        return self


extract_release = lazy_extractor(f"{__package__}.extract")
load_bronze = lazy_bronze_loader(f"{__package__}.bronze")


SOURCE = SourceSpec(
    name=PF_LOCATIONS_SOURCE_NAME,
    provider=PF_PROVIDER,
    extractor=extract_release,
    bronze_loader=load_bronze,
    bronze_tables=(BronzeTable(name="pf_locations_bronze"),),
    checkpoint_strategy="full_refresh",
    cadence="manual",
    description=(
        "Property Finder Dubai location hierarchy and listing filter settings for "
        "scrape planning and future cross-source joins."
    ),
)
