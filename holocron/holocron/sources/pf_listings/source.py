from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from holocron.contracts import BronzeTable, SourceSpec
from holocron.pydantic_helpers import CsvIntTuple, CsvTuple, HolocronModel, NonBlankStr
from holocron.sources.entrypoints import lazy_bronze_loader, lazy_extractor

PF_LISTINGS_SOURCE_NAME = "pf_listings"
PF_PROVIDER = "propertyfinder"
PF_BASE_URL = "https://www.propertyfinder.ae"
PF_STATIC_ASSETS_BASE_URL = "https://static-assets.propertyfinder.com"
PF_DUBAI_LOCATION_ID = "1"
PF_LISTING_CATEGORY_IDS = (1, 2, 3, 4)
PF_RESIDENTIAL_CATEGORY_IDS = (1, 2)
PF_BEDROOM_ELIGIBLE_PROPERTY_TYPE_IDS = (1, 18, 20, 22, 24, 29, 31, 35, 42, 45)
PF_DEFAULT_SEARCH_BOOTSTRAP_PATH = "/en/buy/dubai/properties-for-sale.html"
PF_DEFAULT_LISTING_SEARCH_SORT = "nd"
PF_MANIFEST_PREFIX = "raw/source=pf_listings/manifests/"
PF_LATEST_DELTA_STATE_KEY = "state/source=pf_listings/operation=latest_delta_inventory.json"


class PropertyFinderListingsConfig(HolocronModel):
    base_url: NonBlankStr = PF_BASE_URL
    static_assets_base_url: NonBlankStr = PF_STATIC_ASSETS_BASE_URL
    locale: NonBlankStr = "en"
    country_code: NonBlankStr = "ae"
    mode: Literal["snapshot", "plan", "search", "details", "latest_delta"] = "snapshot"
    categories: CsvIntTuple = PF_LISTING_CATEGORY_IDS
    location_ids: CsvTuple = (PF_DUBAI_LOCATION_ID,)
    sort: NonBlankStr = PF_DEFAULT_LISTING_SEARCH_SORT
    bootstrap_search_path: NonBlankStr = PF_DEFAULT_SEARCH_BOOTSTRAP_PATH
    max_pages_per_query: int = Field(default=50, ge=1, le=50)
    max_results_per_query: int = Field(default=1000, ge=1)
    max_planned_queries: int = Field(default=12000, ge=1)
    max_plan_queries_per_run: int = Field(default=500, ge=1)
    max_search_pages_per_run: int = Field(default=50000, ge=1)
    max_partition_depth: int = Field(default=8, ge=0)
    split_by_property_type: bool = True
    split_by_location: bool = True
    split_by_bedrooms: bool = True
    split_by_price: bool = True
    location_page_limit: int = Field(default=500, ge=1, le=500)
    max_location_pages: int = Field(default=40, ge=1)
    bedroom_values: CsvIntTuple = (0, 1, 2, 3, 4, 5, 6, 7, 8)
    bedroom_eligible_property_type_ids: CsvIntTuple = PF_BEDROOM_ELIGIBLE_PROPERTY_TYPE_IDS
    fetch_details: bool = True
    max_details_per_run: int = Field(default=100000, ge=0)
    manifest_prefix: NonBlankStr = PF_MANIFEST_PREFIX
    plan_manifest_s3_key: str = ""
    plan_manifest_s3_keys: CsvTuple = ()
    plan_state_manifest_s3_key: str = ""
    search_query_cursor: int = Field(default=0, ge=0)
    search_page_cursor: int = Field(default=1, ge=1)
    detail_manifest_cursor: int = Field(default=0, ge=0)
    detail_row_cursor: int = Field(default=0, ge=0)
    latest_delta_state_key: NonBlankStr = PF_LATEST_DELTA_STATE_KEY
    latest_delta_stop_after_seen_pages: int = Field(default=2, ge=1)
    latest_delta_bootstrap_details: bool = False
    latest_delta_detail_audit_limit: int = Field(default=0, ge=0)
    request_pause_seconds: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=90, ge=1)
    headless: bool = True
    chrome_path: str = ""
    storage_state_path: str = ""
    block_media_requests: bool = True

    @model_validator(mode="after")
    def validate_config(self) -> "PropertyFinderListingsConfig":
        if self.mode == "search" and not self.plan_manifest_s3_key.strip():
            if not self.plan_manifest_s3_keys:
                raise ValueError(
                    "plan_manifest_s3_key or plan_manifest_s3_keys is required in search mode"
                )
        if not self.categories:
            raise ValueError("categories must include at least one Property Finder category id")
        if any(category <= 0 for category in self.categories):
            raise ValueError("categories must be positive integers")
        if not self.location_ids:
            raise ValueError("location_ids must include at least one Property Finder location id")
        if self.fetch_details and self.max_details_per_run <= 0:
            raise ValueError("max_details_per_run must be positive when fetch_details is true")
        if any(value < 0 for value in self.bedroom_values):
            raise ValueError("bedroom_values must be non-negative integers")
        return self


extract_release = lazy_extractor(f"{__package__}.extract")
load_bronze = lazy_bronze_loader(f"{__package__}.bronze")


SOURCE = SourceSpec(
    name=PF_LISTINGS_SOURCE_NAME,
    provider=PF_PROVIDER,
    extractor=extract_release,
    bronze_loader=load_bronze,
    bronze_tables=(
        BronzeTable(name="pf_listings_bronze"),
        BronzeTable(name="pf_listing_details_bronze"),
    ),
    checkpoint_strategy="partitioned_chunks",
    cadence="manual",
    description=(
        "Property Finder Dubai listing search snapshots with adaptive query partitions, "
        "optional listing detail pages, and media-oriented raw context."
    ),
)
