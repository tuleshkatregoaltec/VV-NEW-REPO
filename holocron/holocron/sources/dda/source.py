from __future__ import annotations

from pydantic import Field

from holocron.contracts import BronzeTable, SourceSpec
from holocron.pydantic_helpers import HolocronModel
from holocron.sources.entrypoints import lazy_bronze_loader, lazy_extractor

DDA_SOURCE_NAME = "dda_planning_layers"
DDA_PROVIDER = "dda"


class DdaConfig(HolocronModel):
    concurrency: int = Field(default=20, ge=1)
    max_plots: int | None = Field(default=None, ge=1)


extract_release = lazy_extractor(f"{__package__}.extract")
load_bronze = lazy_bronze_loader(f"{__package__}.bronze")


SOURCE = SourceSpec(
    name=DDA_SOURCE_NAME,
    provider=DDA_PROVIDER,
    extractor=extract_release,
    bronze_loader=load_bronze,
    bronze_tables=(
        BronzeTable(name="dda_land_plots"),
        BronzeTable(name="dda_project_areas"),
        BronzeTable(name="dda_subproject_areas"),
        BronzeTable(name="dda_plot_building_limits"),
        BronzeTable(name="dda_plot_podium_limits"),
        BronzeTable(name="dda_plot_features"),
        BronzeTable(name="dda_frozen_plots"),
        BronzeTable(name="dda_landuse_symbols"),
        BronzeTable(name="dda_plot_built_to_lines"),
        BronzeTable(name="dda_plot_arcades"),
        BronzeTable(name="dda_plot_retail"),
    ),
    checkpoint_strategy="full_refresh",
    cadence="0 7 * * 1",
    description="DDA planning map extraction into immutable raw CSV releases.",
)
