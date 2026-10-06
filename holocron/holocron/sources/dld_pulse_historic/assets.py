"""Dagster-facing loader for the archived Dubai Pulse historic release."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from holocron.contracts import BronzeLoadResult
from holocron.platform.raw_files import read_and_validate_manifest
from holocron.pydantic_helpers import CsvTuple, HolocronModel, NonBlankStr
from holocron.sources.dld_pulse_historic.bronze import load_release_to_clickhouse

DLD_PULSE_HISTORIC_SOURCE = "dld_pulse_historic"
DLD_PULSE_HISTORIC_DEFAULT_MANIFEST_KEY = (
    "raw/source=dld_pulse_historic/manifests/dld-pulse-historic-2026-05-16.json"
)


class DldPulseHistoricBronzeConfig(HolocronModel):
    manifest_key: NonBlankStr = DLD_PULSE_HISTORIC_DEFAULT_MANIFEST_KEY
    batch_size: int = Field(default=5_000, ge=1)
    file_names: CsvTuple = ()
    resume_existing_staging: bool = False


def load_dld_pulse_historic_bronze(
    *,
    s3: Any,
    clickhouse: Any,
    config: DldPulseHistoricBronzeConfig | Mapping[str, Any] | None = None,
    progress_log: Any = None,
) -> BronzeLoadResult:
    parsed_config = (
        config
        if isinstance(config, DldPulseHistoricBronzeConfig)
        else DldPulseHistoricBronzeConfig.model_validate(config or {})
    )
    raw_manifest = read_and_validate_manifest(
        s3=s3,
        source_name=DLD_PULSE_HISTORIC_SOURCE,
        manifest_key=parsed_config.manifest_key,
    )
    return load_release_to_clickhouse(
        raw_manifest=raw_manifest,
        s3=s3,
        clickhouse=clickhouse,
        batch_size=parsed_config.batch_size,
        file_names=parsed_config.file_names,
        resume_existing_staging=parsed_config.resume_existing_staging,
        progress_log=progress_log,
    )


__all__ = [
    "DLD_PULSE_HISTORIC_DEFAULT_MANIFEST_KEY",
    "DldPulseHistoricBronzeConfig",
    "load_dld_pulse_historic_bronze",
]
