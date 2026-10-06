from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from typing import Literal

from pydantic import Field, model_validator

from holocron.contracts import BronzeTable, SourceSpec
from holocron.pydantic_helpers import CsvTuple, HolocronModel
from holocron.sources.entrypoints import lazy_bronze_loader, lazy_extractor

DXBI_SOURCE_NAME = "dxbi_transactions"
DXBI_PROVIDER = "dxbinteract"
DXBI_BASE_URL = "https://dxbinteract.com/"
DATE_SLICE_CHECKPOINT_STRATEGY = "date_window"
DXBI_DEFAULT_HEATMAP_PROPERTY_TYPES = ("Apartment", "Villa", "Plot", "Commercial")
DXBI_DEFAULT_HEATMAP_BEDROOMS = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")


@dataclass(frozen=True, slots=True)
class DateSlice:
    start_date: date
    end_date: date

    @property
    def key(self) -> str:
        return f"{self.start_date.isoformat()}_{self.end_date.isoformat()}"


class DxbiConfig(HolocronModel):
    scrape_mode: Literal["comprehensive", "report_tables", "both"] = "comprehensive"
    mode: Literal["incremental", "backfill"] = "incremental"
    start_date: date | None = None
    end_date: date | None = None
    lookback_days: int = Field(default=2, ge=1)
    slice_days: int = Field(default=7, ge=1)
    page_urls: str = ""
    page_urls_file: str = ""
    max_pages: int | None = Field(default=None, ge=1)
    headless: bool = False
    chrome_path: str = ""
    storage_state_path: str = ""
    twocaptcha_api_key: str = ""
    heatmap_property_types: CsvTuple = DXBI_DEFAULT_HEATMAP_PROPERTY_TYPES
    heatmap_bedrooms: CsvTuple = DXBI_DEFAULT_HEATMAP_BEDROOMS
    max_heatmap_buildings: int | None = Field(default=None, ge=1)
    include_heatmap_building_details: bool = True
    include_heatmap_building_status: bool = True
    include_heatmap_chessboard: bool = True
    include_fam_map_buildings: bool = True
    heatmap_request_pause_seconds: float = Field(default=0.5, ge=0)
    heatmap_fetch_timeout_seconds: float = Field(default=30, ge=1)
    heatmap_progress_interval: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def validate_dates(self) -> "DxbiConfig":
        if self.mode == "backfill":
            if self.start_date is None or self.end_date is None:
                raise ValueError("backfill mode requires start_date and end_date")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if not self.heatmap_property_types:
            raise ValueError("heatmap_property_types must include at least one property type")
        if not self.heatmap_bedrooms:
            raise ValueError("heatmap_bedrooms must include at least one bedroom value")
        return self


def utc_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).date()


def resolve_date_window(config: DxbiConfig, *, today: date | None = None) -> tuple[date, date]:
    current_day = today or utc_today()
    if config.mode == "backfill":
        if config.start_date is None or config.end_date is None:
            raise ValueError("backfill mode requires start_date and end_date")
        return config.start_date, config.end_date
    start_date = current_day - timedelta(days=config.lookback_days)
    return start_date, current_day


def build_date_slices(config: DxbiConfig, *, today: date | None = None) -> tuple[DateSlice, ...]:
    start_date, end_date = resolve_date_window(config, today=today)
    slices: list[DateSlice] = []
    current_start = start_date
    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=config.slice_days - 1), end_date)
        slices.append(DateSlice(start_date=current_start, end_date=current_end))
        current_start = current_end + timedelta(days=1)
    return tuple(slices)


extract_release = lazy_extractor(f"{__package__}.extract")
load_bronze = lazy_bronze_loader(f"{__package__}.bronze")


SOURCE = SourceSpec(
    name=DXBI_SOURCE_NAME,
    provider=DXBI_PROVIDER,
    extractor=extract_release,
    bronze_loader=load_bronze,
    bronze_tables=(
        BronzeTable(name="dxbi_transactions_bronze"),
        BronzeTable(name="dxbi_heatmap_rental_buildings_bronze"),
        BronzeTable(name="dxbi_heatmap_buildings_bronze"),
        BronzeTable(name="dxbi_heatmap_building_statuses_bronze"),
        BronzeTable(name="dxbi_heatmap_chessboards_bronze"),
        BronzeTable(name="dxbi_fam_map_buildings_bronze"),
        BronzeTable(name="dxbi_heatmap_errors_bronze"),
    ),
    checkpoint_strategy=DATE_SLICE_CHECKPOINT_STRATEGY,
    cadence="daily",
    description="Slice-based DXB Interact transaction extraction into immutable raw releases.",
)
