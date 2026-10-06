from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field

ListingMode = Literal["sale", "rent"]
ListingAssetClass = Literal["residential", "commercial"]
ListingMarketPosition = Literal["below_market", "near_market", "above_market", "insufficient_data"]
ListingBenchmarkLevel = Literal["building_layout", "project_layout", "insufficient_data"]
ListingUrgencySignal = Literal["explicit_urgency", "value_language", "none"]


class ListingImageResponse(BaseModel):
    small_url: str | None = None
    medium_url: str | None = None
    original_url: str | None = None
    url: str | None = None
    label: str | None = None


class ListingFloorPlanResponse(BaseModel):
    title: str | None = None
    image_url: str | None = None
    area_sqft: float | None = None
    floor_number: int | None = None
    unit_number: str | None = None
    dimension: str | None = None


class ListingPartyResponse(BaseModel):
    id: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    image_url: str | None = None
    logo_url: str | None = None
    address: str | None = None
    slug: str | None = None
    is_super_agent: bool | None = None
    languages: list[str] = Field(default_factory=list)


class ListingFiltersResponse(BaseModel):
    modes: list[ListingMode] = Field(default_factory=list)
    asset_classes: list[ListingAssetClass] = Field(default_factory=list)
    areas: list[str] = Field(default_factory=list)
    property_types: list[str] = Field(default_factory=list)
    bedrooms: list[str] = Field(default_factory=list)
    price_min: int | None = None
    price_max: int | None = None


class ListingCardResponse(BaseModel):
    listing_id: str
    listing_mode: ListingMode
    asset_class: ListingAssetClass
    title: str
    reference: str | None = None
    property_type: str | None = None
    price_value: int | None = None
    price_currency: str | None = None
    price_period: str | None = None
    size_value: float | None = None
    size_unit: str | None = None
    bedrooms: str | None = None
    bathrooms: str | None = None
    city_name: str | None = None
    area_name: str | None = None
    subcommunity_name: str | None = None
    tower_name: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    primary_image_url: str | None = None
    image_count: int = 0
    floorplan_count: int = 0
    agent_name: str | None = None
    agent_image_url: str | None = None
    broker_name: str | None = None
    broker_logo_url: str | None = None
    listed_date: AwareDatetime | None = None
    listing_age_days: int | None = None
    price_per_sqft_aed: float | None = None
    market_median_price_per_sqft_aed: float | None = None
    market_estimate_aed: float | None = None
    market_delta_pct: float | None = None
    market_position: ListingMarketPosition = "insufficient_data"
    comparable_count: int = 0
    benchmark_level: ListingBenchmarkLevel = "insufficient_data"
    urgency_signal: ListingUrgencySignal = "none"
    urgency_terms: list[str] = Field(default_factory=list)
    is_available: bool | None = None
    is_verified: bool | None = None
    is_featured: bool | None = None
    is_premium: bool | None = None
    share_url: str | None = None


class ListingDetailResponse(ListingCardResponse):
    description: str | None = None
    amenities: list[str] = Field(default_factory=list)
    images: list[ListingImageResponse] = Field(default_factory=list)
    floorplans: list[ListingFloorPlanResponse] = Field(default_factory=list)
    agent: ListingPartyResponse | None = None
    broker: ListingPartyResponse | None = None
    client: ListingPartyResponse | None = None
    furnished: str | None = None
    completion_status: str | None = None
    rera: str | None = None
    number_of_cheques: int | None = None
    payment_method: list[str] = Field(default_factory=list)
    video_url: str | None = None
    view_360_url: str | None = None
    source_run_id: str | None = None
    source_manifest_key: str | None = None
    scraped_at: AwareDatetime | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class ListingListResponse(BaseModel):
    listings: list[ListingCardResponse]
    total: int
    limit: int
    offset: int
    filters: ListingFiltersResponse = Field(default_factory=ListingFiltersResponse)


class ListingTrendPoint(BaseModel):
    period: str
    average_asking_price_aed: float | None = None
    median_asking_price_aed: float | None = None
    median_price_per_sqft_aed: float | None = None
    listing_count: int = 0
    median_achieved_price_per_sqft_aed: float | None = None
    achieved_transaction_count: int = 0


class ListingAnalyticsResponse(BaseModel):
    total: int = 0
    average_price_aed: float | None = None
    median_price_aed: float | None = None
    median_price_per_sqft_aed: float | None = None
    average_listing_age_days: float | None = None
    median_listing_age_days: float | None = None
    newly_listed_30d: int = 0
    below_market_count: int = 0
    near_market_count: int = 0
    above_market_count: int = 0
    benchmarked_count: int = 0
    verified_count: int = 0
    area_count: int = 0
    snapshot_at: AwareDatetime | None = None
    trend: list[ListingTrendPoint] = Field(default_factory=list)
