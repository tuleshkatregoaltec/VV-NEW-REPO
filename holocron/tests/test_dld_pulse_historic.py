from pathlib import Path

import pytest

from holocron.sources.dld_pulse_historic.extract import extract_release


def test_dld_pulse_historic_archives_canonical_files_with_normalized_names(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "pulse-data"
    scratch_dir = tmp_path / "scratch"
    input_dir.mkdir()
    scratch_dir.mkdir()
    _write(input_dir / "rent_contracts.csv", "contract_id\n1\n2\n")
    _write(input_dir / "land_registry.csv", "property_id\nland-1\n")
    _write(input_dir / "Rent_Contracts.csv", "contract_id\n1\n")

    release = extract_release(
        str(scratch_dir),
        config={
            "input_dir": str(input_dir),
            "run_id": "pulse-run",
            "file_names": ["rent_contracts", "lands"],
        },
    )

    files_by_name = {Path(raw_file.path).name: raw_file for raw_file in release.files}

    assert release.source == "dld_pulse_historic"
    assert release.run_id == "pulse-run"
    assert set(files_by_name) == {"rent_contracts.csv", "lands.csv"}
    assert files_by_name["rent_contracts.csv"].row_count == 2
    assert files_by_name["lands.csv"].metadata["original_name"] == "land_registry.csv"
    assert release.metadata["excluded_files"] == {
        "Rent_Contracts.csv": "duplicate prefix of rent_contracts.csv"
    }


def test_dld_pulse_historic_fails_when_required_file_is_missing(tmp_path: Path) -> None:
    input_dir = tmp_path / "pulse-data"
    scratch_dir = tmp_path / "scratch"
    input_dir.mkdir()
    scratch_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="rent_contracts.csv"):
        extract_release(
            str(scratch_dir),
            config={"input_dir": str(input_dir), "file_names": ["rent_contracts"]},
        )


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
