from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from holocron.contracts import BronzeTable, RawRelease, SourceSpec
from holocron.platform import bronze_replay
from holocron.platform.bronze_replay import replay_bronze_manifests, select_manifest_keys
from holocron.platform.dataset_versions import latest_complete_dataset_version_key
from tests.fakes import FakeS3 as _FakeS3Base


class FakeS3(_FakeS3Base):
    """FakeS3 for bronze replay: stores manifests (JSON) in json_objects, empty download."""

    def __init__(self, manifests: dict[str, dict[str, Any]]) -> None:
        super().__init__()
        self.json_objects = dict(manifests)

    def list_keys(self, *, prefix: str) -> list[str]:
        return [key for key in self.json_objects if key.startswith(prefix)]

    def download_file(self, *, key: str, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("", encoding="utf-8")


class FakeClickHouse:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.insert_calls: list[dict] = []

    def command(self, sql: str) -> None:
        self.commands.append(sql)

    def insert_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
    ) -> None:
        self.insert_calls.append({"table": table, "rows": rows, "column_names": column_names})

    def replace_table_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
        staging_suffix: str = "replace_rows",
    ) -> int:
        self.insert_calls.append(
            {
                "table": table,
                "rows": rows,
                "column_names": column_names,
                "staging_suffix": staging_suffix,
            }
        )
        return len(rows)


def _extract() -> RawRelease:
    return RawRelease(
        source="example_source",
        run_id="run-1",
        extract_date="2026-05-01",
        created_at="2026-05-01T00:00:00+00:00",
        files=(),
    )


def _manifest(*, source: str, run_id: str) -> dict:
    return {
        "source": source,
        "run_id": run_id,
        "extract_date": "2026-05-01",
        "created_at": "2026-05-01T00:00:00+00:00",
        "files": [
            {
                "path": "rows.jsonl",
                "s3_key": f"raw/source={source}/extract_date=2026-05-01/run_id={run_id}/rows.jsonl",
                "row_count": 2,
            }
        ],
    }


def test_select_manifest_keys_supports_latest_count_and_limit() -> None:
    s3 = FakeS3(
        {
            "raw/source=dxbi_transactions/manifests/run-1.json": {},
            "raw/source=dxbi_transactions/manifests/run-2.json": {},
            "raw/source=dxbi_transactions/manifests/run-3.json": {},
            "raw/source=other/manifests/run-4.json": {},
        }
    )

    assert select_manifest_keys(
        s3=s3,
        source_name="dxbi_transactions",
        latest_count=2,
        limit=1,
    ) == ["raw/source=dxbi_transactions/manifests/run-2.json"]


def test_replay_bronze_manifests_dry_run_validates_and_reports_selection() -> None:
    key = "raw/source=dxbi_transactions/manifests/run-1.json"
    clickhouse = FakeClickHouse()

    result = replay_bronze_manifests(
        source_name="dxbi_transactions",
        s3=FakeS3({key: _manifest(source="dxbi_transactions", run_id="run-1")}),
        clickhouse=clickhouse,
        manifest_keys=[key],
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["manifest_count"] == 1
    assert result["manifests"][0]["run_id"] == "run-1"
    assert result["manifests"][0]["manifest_row_count"] == 2
    assert clickhouse.commands == []


def test_replay_bronze_manifests_rejects_source_mismatch() -> None:
    key = "raw/source=dxbi_transactions/manifests/run-1.json"

    with pytest.raises(ValueError, match="source mismatch"):
        replay_bronze_manifests(
            source_name="dxbi_transactions",
            s3=FakeS3({key: _manifest(source="dld_od_transactions", run_id="run-1")}),
            clickhouse=FakeClickHouse(),
            manifest_keys=[key],
            dry_run=True,
        )


def test_replay_bronze_manifests_rejects_smoke_manifest_key() -> None:
    key = "smoke/raw/source=dxbi_transactions/manifests/run-1.json"

    with pytest.raises(ValueError, match="Normal raw manifest keys"):
        replay_bronze_manifests(
            source_name="dxbi_transactions",
            s3=FakeS3({key: _manifest(source="dxbi_transactions", run_id="run-1")}),
            clickhouse=FakeClickHouse(),
            manifest_keys=[key],
            dry_run=True,
        )


def test_replay_bronze_manifests_rejects_smoke_marked_manifest() -> None:
    key = "raw/source=dxbi_transactions/manifests/run-1.json"
    manifest = _manifest(source="dxbi_transactions", run_id="run-1")
    manifest["metadata"] = {"dataset_kind": "smoke"}

    with pytest.raises(ValueError, match="Smoke raw manifest"):
        replay_bronze_manifests(
            source_name="dxbi_transactions",
            s3=FakeS3({key: manifest}),
            clickhouse=FakeClickHouse(),
            manifest_keys=[key],
            dry_run=True,
        )


def test_replay_bronze_manifests_rejects_missing_loader() -> None:
    with pytest.raises(ValueError, match="No bronze loader"):
        replay_bronze_manifests(
            source_name="news_feeds",
            s3=FakeS3({}),
            clickhouse=FakeClickHouse(),
            dry_run=True,
        )


class _FakeRegistry:
    def __init__(self, source: SourceSpec) -> None:
        self.source = source

    def get(self, name: str) -> SourceSpec:
        if name != self.source.name:
            raise KeyError(name)
        return self.source


def _descriptor(*, source: str, table_names: list[str], manifest_keys: list[str]) -> dict:
    return {
        "source": source,
        "dataset_version": "2026-05-01T00-00-00Z",
        "status": "complete",
        "created_at": "2026-05-01T00:00:00+00:00",
        "base_manifest_keys": manifest_keys[:1],
        "incremental_manifest_keys": manifest_keys[1:],
        "manifest_keys": manifest_keys,
        "table_names": table_names,
        "replay_strategy": "truncate_then_apply_ordered_manifests",
        "coverage": {"shape": "base-plus-incrementals"},
        "notes": "",
    }


def _fake_source(*, loader) -> SourceSpec:
    return SourceSpec(
        name="example_source",
        provider="example",
        extractor=_extract,
        bronze_loader=loader,
        bronze_tables=(BronzeTable(name="example_bronze"),),
    )


def test_dataset_version_replay_requires_initial_load(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _fake_source(loader=lambda **kwargs: {})
    monkeypatch.setattr(bronze_replay, "registry", _FakeRegistry(source))

    with pytest.raises(ValueError, match="requires --initial-load"):
        replay_bronze_manifests(
            source_name=source.name,
            s3=FakeS3({}),
            clickhouse=FakeClickHouse(),
            dataset_version="latest_complete",
            dry_run=True,
        )


def test_dataset_version_replay_rejects_mixed_selectors(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _fake_source(loader=lambda **kwargs: {})
    monkeypatch.setattr(bronze_replay, "registry", _FakeRegistry(source))

    with pytest.raises(ValueError, match="cannot be combined"):
        replay_bronze_manifests(
            source_name=source.name,
            s3=FakeS3({}),
            clickhouse=FakeClickHouse(),
            manifest_keys=["raw/source=example_source/manifests/run-1.json"],
            dataset_version="latest_complete",
            initial_load=True,
            dry_run=True,
        )


def test_dataset_version_replay_loads_ordered_manifests_and_writes_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_run_ids: list[str] = []

    def loader(*, raw_manifest, s3, clickhouse) -> dict:
        loaded_run_ids.append(raw_manifest["run_id"])
        if raw_manifest["run_id"] == "run-2":
            raise RuntimeError("load failed")
        return {
            "run_id": raw_manifest["run_id"],
            "table_row_counts": {"example_bronze": raw_manifest["files"][0]["row_count"]},
            "total_rows": raw_manifest["files"][0]["row_count"],
        }

    source = _fake_source(loader=loader)
    monkeypatch.setattr(bronze_replay, "registry", _FakeRegistry(source))
    run_1_key = "raw/source=example_source/manifests/run-1.json"
    run_2_key = "raw/source=example_source/manifests/run-2.json"
    descriptor_key = latest_complete_dataset_version_key(source=source.name)
    s3 = FakeS3(
        {
            run_1_key: _manifest(source=source.name, run_id="run-1"),
            run_2_key: _manifest(source=source.name, run_id="run-2"),
            descriptor_key: _descriptor(
                source=source.name,
                table_names=["example_bronze"],
                manifest_keys=[run_1_key, run_2_key],
            ),
        }
    )
    clickhouse = FakeClickHouse()

    result = replay_bronze_manifests(
        source_name=source.name,
        s3=s3,
        clickhouse=clickhouse,
        dataset_version="latest_complete",
        initial_load=True,
    )

    assert loaded_run_ids == ["run-1", "run-2"]
    assert result["dataset_version"] == "2026-05-01T00-00-00Z"
    assert result["manifest_count"] == 2
    assert result["table_row_counts"] == {"example_bronze": 2}
    assert result["failures"] == [{"manifest_s3_key": run_2_key, "error": "load failed"}]
    assert result["ledger_rows"] == 2

    ledger_rows = [
        row
        for call in clickhouse.insert_calls
        if call["table"] == "bronze_load_ledger"
        for row in call["rows"]
    ]
    assert [row[3] for row in ledger_rows] == ["run-1", "run-2"]
    assert [row[7] for row in ledger_rows] == ["success", "failure"]
    assert ledger_rows[0][4:6] == ("example_bronze", 2)
    assert ledger_rows[1][4:6] == ("", 0)
