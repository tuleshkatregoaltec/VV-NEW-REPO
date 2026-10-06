from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from holocron.contracts import BronzeTable, SourceSpec
from holocron.pydantic_helpers import CsvTuple, HolocronModel, NonBlankStr
from holocron.sources.entrypoints import lazy_bronze_loader, lazy_extractor

REELLY_SUPPLY_SOURCE_NAME = "reelly_supply"
REELLY_PROVIDER = "reelly"
REELLY_API_BASE_URL = "https://api.reelly.io/api:sk5LT7jx"
REELLY_DOCUMENTS_BASE_URL = "https://xdil-qda0-zofk.m2.xano.io/api:sk5LT7jx"
REELLY_AVAILABILITY_BASE_URL = "https://xdil-qda0-zofk.m2.xano.io/api:ukkgO6DN"
REELLY_DEFAULT_REGION = "2"
REELLY_DEFAULT_SALE_STATUSES = ("start_of_sales", "on_sale", "out_of_stock")
REELLY_DEFAULT_ALLOWED_DOCUMENT_HOSTS = (
    "api.reelly.io",
    "drive.google.com",
    "drive.usercontent.google.com",
    ".googleusercontent.com",
    "storage.googleapis.com",
    "xdil-qda0-zofk.m2.xano.io",
)
REELLY_CATALOG_STATE_KEY = "state/source=reelly_supply/operation=catalog_inventory.json"


class ReellySupplyConfig(HolocronModel):
    mode: Literal["archive", "catalog_delta", "availability_delta"] = "archive"
    email: str = ""
    password: str = ""
    base_url: NonBlankStr = REELLY_API_BASE_URL
    documents_base_url: NonBlankStr = REELLY_DOCUMENTS_BASE_URL
    availability_base_url: NonBlankStr = REELLY_AVAILABILITY_BASE_URL
    region: NonBlankStr = REELLY_DEFAULT_REGION
    sale_statuses: CsvTuple = REELLY_DEFAULT_SALE_STATUSES
    pages_per_run: int = Field(default=5, ge=1)
    start_page: int = Field(default=1, ge=1)
    page_cursor: int | None = Field(default=None, ge=1)
    max_pages: int | None = Field(default=None, ge=1)
    download_documents: bool = False
    download_all_project_docs: bool = True
    max_document_mb: int = Field(default=100, ge=1)
    allowed_document_hosts: CsvTuple = REELLY_DEFAULT_ALLOWED_DOCUMENT_HOSTS
    try_matrix_availability: bool = True
    matrix_endpoints: CsvTuple = ("floors", "bedrooms")
    catalog_state_key: NonBlankStr = REELLY_CATALOG_STATE_KEY
    bootstrap_details: bool = False
    detail_audit_limit: int = Field(default=0, ge=0)
    fetch_documents_for_delta: bool = False
    max_availability_projects_per_run: int | None = Field(default=None, ge=1)
    request_pause_seconds: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=60, ge=1)

    @model_validator(mode="after")
    def validate_config(self) -> "ReellySupplyConfig":
        if not self.sale_statuses:
            raise ValueError("sale_statuses must include at least one status")
        if not self.matrix_endpoints:
            raise ValueError("matrix_endpoints must include at least one endpoint")
        if not self.allowed_document_hosts:
            raise ValueError("allowed_document_hosts must include at least one host")
        return self

    @property
    def resolved_start_page(self) -> int:
        return self.page_cursor or self.start_page


extract_release = lazy_extractor(f"{__package__}.extract")
load_bronze = lazy_bronze_loader(f"{__package__}.bronze")


SOURCE = SourceSpec(
    name=REELLY_SUPPLY_SOURCE_NAME,
    provider=REELLY_PROVIDER,
    extractor=extract_release,
    bronze_loader=load_bronze,
    bronze_tables=(
        BronzeTable(name="reelly_projects_bronze"),
        BronzeTable(name="reelly_documents_bronze"),
        BronzeTable(name="reelly_matrix_availability_bronze"),
    ),
    checkpoint_strategy="cursor_pages",
    cadence="daily",
    description="Bounded raw Reelly supply extraction with project details, documents, and availability probes.",
)
