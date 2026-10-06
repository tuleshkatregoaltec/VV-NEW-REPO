from __future__ import annotations

from pydantic import Field

from holocron.contracts import SourceSpec
from holocron.pydantic_helpers import HolocronModel, NonBlankStr
from holocron.sources.entrypoints import lazy_extractor

DLD_MASHROOI_SOURCE_NAME = "dld_mashrooi"
DLD_PROVIDER = "dld"
DLD_MASHROOI_BASE_URL = "https://b2c.dubailand.gov.ae/mashrooi"
DLD_MASHROOI_CONSUMER_ID = "gkb3WvEG0rY9eilwXC0P2pTz8UzvLj9F"


class DldMashrooiConfig(HolocronModel):
    base_url: NonBlankStr = DLD_MASHROOI_BASE_URL
    consumer_id: NonBlankStr = DLD_MASHROOI_CONSUMER_ID
    search_query: str = ""
    fetch_details: bool = True
    max_projects: int | None = Field(default=None, ge=1)
    max_details: int | None = Field(default=None, ge=1)
    continue_on_detail_error: bool = True
    request_pause_seconds: float = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=60, ge=1)
    user_agent: NonBlankStr = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )


extract_release = lazy_extractor(f"{__package__}.extract")


SOURCE = SourceSpec(
    name=DLD_MASHROOI_SOURCE_NAME,
    provider=DLD_PROVIDER,
    extractor=extract_release,
    checkpoint_strategy="full_refresh",
    cadence="manual",
    description="DLD Mashrooi project list and project detail payloads with project/building/land coordinates.",
)
