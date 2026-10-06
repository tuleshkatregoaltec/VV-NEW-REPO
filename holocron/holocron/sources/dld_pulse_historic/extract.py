from __future__ import annotations

from collections.abc import Iterable, Mapping
import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
from typing import Any

from holocron.contracts import RawFile, RawRelease
from holocron.platform.execution import new_run_id, utc_now
from holocron.pydantic_helpers import HolocronModel

_CSV_CONTENT_TYPE = "text/csv"
_KML_CONTENT_TYPE = "application/vnd.google-earth.kml+xml"
_SOURCE_NAME = "dld_pulse_historic"


@dataclass(frozen=True, slots=True)
class PulseArchiveFileSpec:
    original_name: str
    archive_name: str
    dataset: str
    content_type: str
    count_csv_rows: bool = True


_ARCHIVE_FILE_SPECS: tuple[PulseArchiveFileSpec, ...] = (
    PulseArchiveFileSpec(
        "rent_contracts.csv", "rent_contracts.csv", "rent_contracts", _CSV_CONTENT_TYPE
    ),
    PulseArchiveFileSpec("transactions.csv", "transactions.csv", "transactions", _CSV_CONTENT_TYPE),
    PulseArchiveFileSpec("units.csv", "units.csv", "units", _CSV_CONTENT_TYPE),
    PulseArchiveFileSpec("land_registry.csv", "lands.csv", "lands", _CSV_CONTENT_TYPE),
    PulseArchiveFileSpec("buildings.csv", "buildings.csv", "buildings", _CSV_CONTENT_TYPE),
    PulseArchiveFileSpec("developers.csv", "developers.csv", "developers", _CSV_CONTENT_TYPE),
    PulseArchiveFileSpec("projects.csv", "projects.csv", "projects", _CSV_CONTENT_TYPE),
    PulseArchiveFileSpec("lkp_areas.csv", "areas.csv", "areas", _CSV_CONTENT_TYPE),
    PulseArchiveFileSpec(
        "Community.kml",
        "communities.kml",
        "communities",
        _KML_CONTENT_TYPE,
        count_csv_rows=False,
    ),
)
_EXCLUDED_FILE_NAMES = {
    "Rent_Contracts.csv": "duplicate prefix of rent_contracts.csv",
}


class DldPulseHistoricConfig(HolocronModel):
    input_dir: str = "pulse-data"
    run_id: str = ""
    require_all_files: bool = True
    file_names: tuple[str, ...] = ()


def extract_release(
    scratch_dir: str,
    *,
    config: Mapping[str, Any] | None = None,
    progress_log: Any = None,
) -> RawRelease:
    current = utc_now()
    archive_config = DldPulseHistoricConfig.model_validate(config or {})
    input_dir = Path(archive_config.input_dir).expanduser()
    if not input_dir.is_absolute():
        input_dir = Path.cwd() / input_dir
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"DLD Pulse historic input_dir does not exist: {input_dir}")

    requested_names = {name.strip() for name in archive_config.file_names if name.strip()}
    specs = tuple(_selected_specs(requested_names)) if requested_names else _ARCHIVE_FILE_SPECS
    if not specs:
        raise ValueError("DLD Pulse historic archive selected no files")

    scratch_path = Path(scratch_dir)
    raw_files: list[RawFile] = []
    missing_files: list[str] = []
    excluded_present = sorted(name for name in _EXCLUDED_FILE_NAMES if (input_dir / name).exists())

    for spec in specs:
        source_path = input_dir / spec.original_name
        if not source_path.is_file():
            missing_files.append(spec.original_name)
            continue

        _log(
            progress_log,
            "archiving DLD Pulse file %s as %s",
            spec.original_name,
            spec.archive_name,
        )
        archive_path = scratch_path / spec.archive_name
        _hardlink_file(source_path=source_path, archive_path=archive_path)
        raw_files.append(_build_raw_file(path=archive_path, source_path=source_path, spec=spec))
        _log(
            progress_log,
            "archived DLD Pulse file %s bytes=%s rows=%s",
            spec.archive_name,
            raw_files[-1].size_bytes,
            raw_files[-1].row_count,
        )

    if missing_files and archive_config.require_all_files:
        missing = ", ".join(missing_files)
        raise FileNotFoundError(f"DLD Pulse historic archive is missing expected files: {missing}")
    if not raw_files:
        raise ValueError("DLD Pulse historic archive found no files to upload")

    run_id = archive_config.run_id.strip() or new_run_id(current)
    return RawRelease(
        source=_SOURCE_NAME,
        run_id=run_id,
        extract_date=current.date().isoformat(),
        created_at=current.isoformat(),
        files=tuple(raw_files),
        metadata={
            "mode": "historic_archive",
            "source_system": "dubai_pulse",
            "input_dir": str(input_dir),
            "selected_file_count": len(raw_files),
            "missing_files": missing_files,
            "excluded_files": {name: _EXCLUDED_FILE_NAMES[name] for name in excluded_present},
        },
    )


def _selected_specs(requested_names: set[str]) -> Iterable[PulseArchiveFileSpec]:
    valid_names = {
        name
        for spec in _ARCHIVE_FILE_SPECS
        for name in (spec.original_name, spec.archive_name, spec.dataset)
    }
    unknown_names = sorted(requested_names - valid_names)
    if unknown_names:
        raise ValueError(f"Unknown DLD Pulse historic file selections: {', '.join(unknown_names)}")

    for spec in _ARCHIVE_FILE_SPECS:
        if {spec.original_name, spec.archive_name, spec.dataset} & requested_names:
            yield spec


def _hardlink_file(*, source_path: Path, archive_path: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()
    try:
        archive_path.hardlink_to(source_path)
    except OSError as exc:
        raise OSError(
            "DLD Pulse historic archive requires input files and Dagster scratch space "
            f"on the same filesystem so files can be hard-linked without copying: {source_path}"
        ) from exc


def _build_raw_file(*, path: Path, source_path: Path, spec: PulseArchiveFileSpec) -> RawFile:
    return RawFile(
        path=str(path),
        sha256=_file_sha256(path),
        size_bytes=path.stat().st_size,
        row_count=_csv_row_count(path) if spec.count_csv_rows else None,
        content_type=spec.content_type,
        metadata={
            "dataset": spec.dataset,
            "original_name": spec.original_name,
            "archive_name": spec.archive_name,
            "source_path": str(source_path),
        },
    )


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _csv_row_count(path: Path) -> int:
    _allow_large_csv_fields()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def _allow_large_csv_fields() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _log(progress_log: Any, message: str, *args: Any) -> None:
    if progress_log is not None:
        progress_log.info(message, *args)
