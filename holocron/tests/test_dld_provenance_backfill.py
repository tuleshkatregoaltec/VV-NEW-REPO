from typing import Any

from holocron.platform.dld_provenance_backfill import (
    build_dld_provenance_backfill_statements,
    run_dld_provenance_backfill,
)
from tests.fakes import FakeS3


class ManifestS3(FakeS3):
    def __init__(self, manifests: dict[str, dict[str, Any]]) -> None:
        super().__init__()
        self.json_objects = manifests

    def list_keys(self, *, prefix: str) -> list[str]:
        return sorted(key for key in self.json_objects if key.startswith(prefix))


class NoCommandClickHouse:
    def command(self, sql: str) -> None:
        raise AssertionError(f"Dry-run should not execute ClickHouse SQL: {sql}")


def test_dld_provenance_backfill_builds_open_data_pointer_update() -> None:
    manifest_key = "raw/source=dld_od_transactions/manifests/run-1.json"
    s3 = ManifestS3(
        {
            manifest_key: {
                "source": "dld_od_transactions",
                "run_id": "run-1",
                "files": [
                    {
                        "path": "dld_od_transactions_rows.jsonl",
                        "s3_key": "raw/source=dld_od_transactions/extract_date=2026-05-01/"
                        "run_id=run-1/dld_od_transactions_rows.jsonl",
                    }
                ],
            }
        }
    )

    statements = build_dld_provenance_backfill_statements(
        s3=s3,
        include_pulse=False,
        sources=("dld_od_transactions",),
    )

    assert len(statements) == 1
    sql = statements[0].sql
    assert "ALTER TABLE `dld_od_transactions_bronze` UPDATE" in sql
    assert f"raw_manifest_s3_key = '{manifest_key}'" in sql
    assert (
        "source_file = if(source_file = '', 'dld_od_transactions_rows.jsonl', source_file)" in sql
    )
    assert "source_row_index = if(source_row_index = 0, row_index, source_row_index)" in sql
    assert "source_system = 'dld_open_data'" in sql
    assert "run_id = 'run-1'" in sql
    assert "SETTINGS mutations_sync = 1" in sql


def test_dld_provenance_backfill_dry_run_does_not_touch_clickhouse() -> None:
    manifest_key = "raw/source=dld_od_transactions/manifests/run-1.json"
    s3 = ManifestS3(
        {
            manifest_key: {
                "source": "dld_od_transactions",
                "run_id": "run-1",
                "files": [
                    {
                        "path": "dld_od_transactions_rows.jsonl",
                        "s3_key": "raw/source=dld_od_transactions/extract_date=2026-05-01/"
                        "run_id=run-1/dld_od_transactions_rows.jsonl",
                    }
                ],
            }
        }
    )

    result = run_dld_provenance_backfill(
        s3=s3,
        clickhouse=NoCommandClickHouse(),
        execute=False,
        include_pulse=False,
        sources=("dld_od_transactions",),
    )

    assert result["dry_run"] is True
    assert result["statement_count"] == 1


def test_dld_provenance_backfill_builds_pulse_file_pointer_updates() -> None:
    manifest_key = "raw/source=dld_pulse_historic/manifests/pulse-run.json"
    s3 = ManifestS3(
        {
            manifest_key: {
                "source": "dld_pulse_historic",
                "run_id": "pulse-run",
                "files": [
                    {
                        "path": "transactions.csv",
                        "s3_key": "raw/source=dld_pulse_historic/extract_date=2026-05-16/"
                        "run_id=pulse-run/transactions.csv",
                    },
                    {
                        "path": "areas.csv",
                        "s3_key": "raw/source=dld_pulse_historic/extract_date=2026-05-16/"
                        "run_id=pulse-run/areas.csv",
                    },
                ],
            }
        }
    )

    statements = build_dld_provenance_backfill_statements(
        s3=s3,
        include_open_data=False,
    )

    assert len(statements) == 1
    sql = statements[0].sql
    assert "ALTER TABLE `dld_od_transactions_bronze` UPDATE" in sql
    assert f"raw_manifest_s3_key = '{manifest_key}'" in sql
    assert "source_system = 'dubai_pulse'" in sql
    assert "run_id = 'pulse-run'" in sql
    assert "source_file = 'transactions.csv'" in sql
    assert "raw_manifest_s3_key = ''" in sql
