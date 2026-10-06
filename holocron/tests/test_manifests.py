import pytest

from holocron.platform.manifests import (
    RawManifestModel,
    manifest_s3_key,
    raw_file_s3_key,
    raw_manifest_prefix,
    require_normal_raw_manifest,
)
from holocron.platform.raw_files import read_and_validate_manifest


def test_manifest_key_uses_source_scoped_raw_layout() -> None:
    assert manifest_s3_key(source="dxbi_transactions", run_id="run-1") == (
        "raw/source=dxbi_transactions/manifests/run-1.json"
    )
    assert (
        raw_manifest_prefix(source="dxbi_transactions") == "raw/source=dxbi_transactions/manifests/"
    )


def test_raw_file_key_uses_extract_date_and_run_id_partitioning() -> None:
    assert (
        raw_file_s3_key(
            source="dxbi_transactions",
            extract_date="2026-03-31",
            run_id="run-1",
            file_name="sales.csv",
        )
        == "raw/source=dxbi_transactions/extract_date=2026-03-31/run_id=run-1/sales.csv"
    )


def test_normal_raw_manifest_scope_rejects_smoke_manifest_key() -> None:
    with pytest.raises(ValueError, match="Normal raw manifest keys"):
        require_normal_raw_manifest(
            source="dxbi_transactions",
            manifest_key="smoke/raw/source=dxbi_transactions/manifests/run-1.json",
            manifest=_manifest(),
        )


def test_normal_raw_manifest_scope_rejects_smoke_marker() -> None:
    manifest = _manifest()
    manifest["metadata"] = {"dataset_kind": "smoke"}

    with pytest.raises(ValueError, match="Smoke raw manifest"):
        require_normal_raw_manifest(
            source="dxbi_transactions",
            manifest_key="raw/source=dxbi_transactions/manifests/run-1.json",
            manifest=manifest,
        )


def test_normal_raw_manifest_scope_rejects_noncanonical_file_keys() -> None:
    manifest = _manifest()
    manifest["files"][0]["s3_key"] = (
        "smoke/raw/source=dxbi_transactions/extract_date=2026-03-31/run_id=run-1/sales.csv"
    )

    with pytest.raises(ValueError, match="Normal raw manifest file keys"):
        require_normal_raw_manifest(
            source="dxbi_transactions",
            manifest_key="raw/source=dxbi_transactions/manifests/run-1.json",
            manifest=manifest,
        )


def test_raw_manifest_model_strips_required_strings_and_validates_files() -> None:
    model = RawManifestModel.model_validate(
        {
            "source": " dxbi_transactions ",
            "run_id": " run-1 ",
            "files": [
                {
                    "path": " sales.csv ",
                    "s3_key": (
                        " raw/source=dxbi_transactions/extract_date=2026-03-31/"
                        "run_id=run-1/sales.csv "
                    ),
                    "row_count": 1,
                }
            ],
        }
    )

    assert model.source == "dxbi_transactions"
    assert model.run_id == "run-1"
    assert model.files[0].path == "sales.csv"
    assert model.files[0].s3_key.endswith("sales.csv")


def test_read_and_validate_manifest_returns_normalized_model_payload() -> None:
    class FakeS3:
        def get_json(self, *, key: str) -> dict:
            assert key == "raw/source=dxbi_transactions/manifests/run-1.json"
            return {
                "source": " dxbi_transactions ",
                "run_id": " run-1 ",
                "extract_date": "2026-03-31",
                "files": [
                    {
                        "path": " sales.csv ",
                        "s3_key": (
                            "raw/source=dxbi_transactions/extract_date=2026-03-31/"
                            "run_id=run-1/sales.csv"
                        ),
                        "row_count": 1,
                    }
                ],
            }

    manifest = read_and_validate_manifest(
        s3=FakeS3(),
        source_name="dxbi_transactions",
        manifest_key="raw/source=dxbi_transactions/manifests/run-1.json",
    )

    assert manifest["source"] == "dxbi_transactions"
    assert manifest["run_id"] == "run-1"
    assert manifest["files"][0]["path"] == "sales.csv"
    assert manifest["manifest_s3_key"] == "raw/source=dxbi_transactions/manifests/run-1.json"


def _manifest() -> dict:
    return {
        "source": "dxbi_transactions",
        "run_id": "run-1",
        "extract_date": "2026-03-31",
        "files": [
            {
                "path": "sales.csv",
                "s3_key": (
                    "raw/source=dxbi_transactions/extract_date=2026-03-31/run_id=run-1/sales.csv"
                ),
                "row_count": 1,
            }
        ],
    }
