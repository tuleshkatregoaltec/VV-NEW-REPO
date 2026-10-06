import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from holocron.sources import DDA_SOURCE, registry
from holocron.sources.dda.extract import extract_release
from holocron.sources.dda.source import DdaConfig


def test_dda_source_is_registered() -> None:
    assert registry.get("dda_planning_layers") is DDA_SOURCE


def test_dda_config_validates_max_plots() -> None:
    with pytest.raises(ValueError):
        DdaConfig(max_plots=0)


def test_extract_release_builds_manifest_with_csv_outputs(tmp_path: Path) -> None:
    def scrape_runner(output_dir: Path, *, concurrency: int, max_plots: int | None) -> None:
        assert concurrency == 5
        assert max_plots == 2
        target = output_dir / "dda_project_areas.csv"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["object_id", "project_name", "rings"])
            writer.writeheader()
            writer.writerow({"object_id": 1, "project_name": "A", "rings": "[]"})

    release = extract_release(
        tmp_path,
        config=DdaConfig(concurrency=5, max_plots=2),
        now=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
        scrape_runner=scrape_runner,
    )

    assert release.run_id == "2026-04-29T08-00-00Z"
    assert release.source == "dda_planning_layers"
    assert len(release.files) == 1
    assert release.files[0].path.endswith("dda_project_areas.csv")
    assert release.files[0].row_count == 1


def test_extract_release_counts_large_csv_fields(tmp_path: Path) -> None:
    def scrape_runner(output_dir: Path, *, concurrency: int, max_plots: int | None) -> None:
        target = output_dir / "dda_project_areas.csv"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["object_id", "project_name", "rings"])
            writer.writeheader()
            writer.writerow({"object_id": 1, "project_name": "A", "rings": "x" * 200_000})

    release = extract_release(
        tmp_path,
        config=DdaConfig(concurrency=1, max_plots=1),
        now=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
        scrape_runner=scrape_runner,
    )

    assert release.files[0].row_count == 1
