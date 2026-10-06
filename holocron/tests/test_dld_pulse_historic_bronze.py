import hashlib
from collections.abc import Sequence
from typing import Any

from tests.fakes import FakeS3

from holocron.sources.dld_pulse_historic.assets import load_dld_pulse_historic_bronze
from holocron.sources.dld_pulse_historic.bronze import load_release_to_clickhouse


class FakeClickHouse:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.insert_calls: list[dict[str, Any]] = []
        self.table_exists = False
        self.staged_source_rows = 0

    def command(self, sql: str) -> None:
        self.commands.append(sql)

    def query(self, sql: str) -> Any:
        if "FROM system.tables" in sql:
            return _QueryResult([(1 if self.table_exists else 0,)])
        if "WHERE source_system = 'dubai_pulse'" in sql:
            return _QueryResult([(self.staged_source_rows,)])
        raise AssertionError(f"Unexpected query: {sql}")

    def insert_rows(
        self,
        *,
        table: str,
        rows: Sequence[tuple[Any, ...]],
        column_names: Sequence[str],
    ) -> None:
        self.insert_calls.append({"table": table, "rows": rows, "column_names": column_names})


class _QueryResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.result_rows = rows


def test_dld_pulse_historic_bronze_stages_and_maps_canonical_files() -> None:
    objects = _pulse_objects()
    clickhouse = FakeClickHouse()

    result = load_release_to_clickhouse(
        raw_manifest=_manifest(objects),
        s3=FakeS3(objects),
        clickhouse=clickhouse,
        batch_size=1,
    )

    assert result["table_row_counts"] == {
        "dld_od_developers_bronze": 1,
        "dld_od_projects_bronze": 1,
        "dld_od_lands_bronze": 1,
        "dld_od_buildings_bronze": 1,
        "dld_od_units_bronze": 1,
        "dld_od_transactions_bronze": 1,
        "dld_od_rents_bronze": 1,
    }
    assert not any("DELETE WHERE" in command for command in clickhouse.commands)
    assert sum("EXCHANGE TABLES" in command for command in clickhouse.commands) == 7
    assert any(
        "INSERT INTO `dld_od_transactions_bronze_staging_pulse_" in command
        and "source_system != 'dubai_pulse'" in command
        for command in clickhouse.commands
    )

    transaction_call = _insert_call(clickhouse, "dld_od_transactions_bronze")
    transaction = dict(zip(transaction_call["column_names"], transaction_call["rows"][0]))
    assert transaction["source_system"] == "dubai_pulse"
    assert transaction["transaction_number"] == "TX-1"
    assert transaction["project_number"] == "9001"
    assert transaction["building_name_en"] == "Pulse Tower"
    assert transaction["reg_type_en"] == "Off Plan"
    assert transaction["is_offplan"] == 1
    assert transaction["area_id"] == 0
    assert "\\u0000" not in transaction["raw_json"]
    assert transaction["raw_manifest_s3_key"] == (
        "raw/source=dld_pulse_historic/manifests/manifest.json"
    )

    unit_call = _insert_call(clickhouse, "dld_od_units_bronze")
    unit = dict(zip(unit_call["column_names"], unit_call["rows"][0]))
    assert unit["source_system"] == "dubai_pulse"
    assert unit["property_id"] == 111
    assert unit["parent_property_id"] == 222
    assert unit["project_id"] == 333
    assert unit["building_number"] == "B-1"
    assert "manifest.json" in unit["raw_json"]
    assert unit["raw_manifest_s3_key"] == "raw/source=dld_pulse_historic/manifests/manifest.json"

    developer_call = _insert_call(clickhouse, "dld_od_developers_bronze")
    developer = dict(zip(developer_call["column_names"], developer_call["rows"][0]))
    assert developer["license_type_id"] == 0


def test_dld_pulse_historic_bronze_asset_reads_manifest_by_key() -> None:
    objects = _pulse_objects()
    manifest_key = "raw/source=dld_pulse_historic/manifests/manifest.json"
    s3 = FakeS3(objects)
    s3.json_objects[manifest_key] = _manifest(objects)
    clickhouse = FakeClickHouse()

    result = load_dld_pulse_historic_bronze(
        s3=s3,
        clickhouse=clickhouse,
        config={"manifest_key": manifest_key, "batch_size": 2},
    )

    assert result["total_rows"] == 7
    assert sum("EXCHANGE TABLES" in command for command in clickhouse.commands) == 7


def test_dld_pulse_historic_bronze_can_load_selected_files() -> None:
    objects = _pulse_objects()
    clickhouse = FakeClickHouse()

    result = load_release_to_clickhouse(
        raw_manifest=_manifest(objects),
        s3=FakeS3(objects),
        clickhouse=clickhouse,
        file_names=("transactions.csv",),
    )

    assert result["table_row_counts"] == {"dld_od_transactions_bronze": 1}
    assert sum("EXCHANGE TABLES" in command for command in clickhouse.commands) == 1


def test_dld_pulse_historic_bronze_can_resume_existing_staging() -> None:
    prefix = "raw/source=dld_pulse_historic/extract_date=2026-05-16/run_id=pulse-run"
    rent_key = f"{prefix}/rent_contracts.csv"
    objects = {
        rent_key: _csv_many(
            [
                "contract_id",
                "line_number",
                "contract_start_date",
                "contract_end_date",
                "annual_amount",
                "project_number",
                "project_name_en",
                "tenant_type_en",
                "area_id",
                "area_name_en",
            ],
            [
                [
                    "RC-1",
                    "1",
                    "01-01-2020",
                    "31-12-2020",
                    "100000",
                    "9001",
                    "One",
                    "Person",
                    "10",
                    "Downtown",
                ],
                [
                    "RC-2",
                    "2",
                    "01-01-2021",
                    "31-12-2021",
                    "120000",
                    "9002",
                    "Two",
                    "Company",
                    "11",
                    "Marina",
                ],
            ],
        )
    }
    manifest = _manifest(objects)
    manifest["files"][0]["row_count"] = 2
    clickhouse = FakeClickHouse()
    clickhouse.table_exists = True
    clickhouse.staged_source_rows = 1

    result = load_release_to_clickhouse(
        raw_manifest=manifest,
        s3=FakeS3(objects),
        clickhouse=clickhouse,
        batch_size=1,
        file_names=("rent_contracts.csv",),
        resume_existing_staging=True,
    )

    assert result["table_row_counts"] == {"dld_od_rents_bronze": 2}
    assert not any(
        command.startswith("CREATE TABLE `dld_od_rents_bronze_staging_pulse_")
        for command in clickhouse.commands
    )
    rent_call = _insert_call(clickhouse, "dld_od_rents_bronze")
    rent = dict(zip(rent_call["column_names"], rent_call["rows"][0]))
    assert rent["contract_number"] == "RC-2"
    assert rent["source_row_index"] == 2


def _insert_call(clickhouse: FakeClickHouse, target_table: str) -> dict[str, Any]:
    call = next(
        call
        for call in clickhouse.insert_calls
        if call["table"].startswith(f"{target_table}_staging_pulse_")
    )
    return call


def _manifest(objects: dict[str, bytes]) -> dict[str, Any]:
    return {
        "source": "dld_pulse_historic",
        "run_id": "pulse-run",
        "extract_date": "2026-05-16",
        "created_at": "2026-05-16T00:00:00+00:00",
        "manifest_s3_key": "raw/source=dld_pulse_historic/manifests/manifest.json",
        "files": [
            {
                "path": key.rsplit("/", 1)[-1],
                "s3_key": key,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "row_count": 1,
                "content_type": "text/csv",
            }
            for key, payload in objects.items()
        ],
    }


def _pulse_objects() -> dict[str, bytes]:
    prefix = "raw/source=dld_pulse_historic/extract_date=2026-05-16/run_id=pulse-run"
    files = {
        "developers.csv": _csv(
            [
                "developer_number",
                "developer_id",
                "developer_name_en",
                "developer_name_ar",
                "registration_date",
                "license_type_id",
            ],
            ["77", "88", "Pulse Dev", "Pulse Dev AR", "01-01-2020", "-1"],
        ),
        "projects.csv": _csv(
            [
                "project_number",
                "project_id",
                "project_name",
                "developer_id",
                "developer_number",
                "developer_name",
                "area_id",
                "area_name_en",
            ],
            ["9001", "333", "Pulse Project", "88", "77", "Pulse Dev", "10", "Downtown"],
        ),
        "lands.csv": _csv(
            [
                "property_id",
                "parcel_id",
                "land_number",
                "area_id",
                "area_name_en",
                "project_id",
                "project_name_en",
            ],
            ["444", "PARCEL-1", "LAND-1", "10", "Downtown", "333", "Pulse Project"],
        ),
        "buildings.csv": _csv(
            [
                "property_id",
                "building_number",
                "parcel_id",
                "parent_property_id",
                "area_id",
                "area_name_en",
                "project_id",
                "project_name_en",
            ],
            ["222", "B-1", "PARCEL-1", "444", "10", "Downtown", "333", "Pulse Project"],
        ),
        "units.csv": _csv(
            [
                "property_id",
                "parent_property_id",
                "grandparent_property_id",
                "building_number",
                "unit_number",
                "project_id",
                "project_name_en",
                "area_id",
                "area_name_en",
                "creation_date",
            ],
            [
                "111",
                "222",
                "444",
                "B-1",
                "101",
                "333",
                "Pulse Project",
                "10",
                "Downtown",
                "02-01-2020",
            ],
        ),
        "transactions.csv": _csv(
            [
                "transaction_id",
                "instance_date",
                "actual_worth",
                "project_number",
                "project_name_en",
                "building_name_en",
                "reg_type_en",
                "area_id",
                "area_name_en",
            ],
            [
                "TX-1",
                "03-01-2020",
                "1000000",
                "9001",
                "Pulse Project",
                "Pulse Tower",
                "Off Plan\x00",
                "TOWER 108",
                "Downtown",
            ],
        ),
        "rent_contracts.csv": _csv(
            [
                "contract_id",
                "line_number",
                "contract_start_date",
                "contract_end_date",
                "annual_amount",
                "project_number",
                "project_name_en",
                "tenant_type_en",
                "area_id",
                "area_name_en",
            ],
            [
                "RC-1",
                "1",
                "01-01-2020",
                "31-12-2020",
                "100000",
                "9001",
                "Pulse Project",
                "Person",
                "10",
                "Downtown",
            ],
        ),
    }
    return {f"{prefix}/{file_name}": payload for file_name, payload in files.items()}


def _csv(header: list[str], row: list[str]) -> bytes:
    return (",".join(header) + "\n" + ",".join(row) + "\n").encode("utf-8")


def _csv_many(header: list[str], rows: list[list[str]]) -> bytes:
    return (",".join(header) + "\n" + "\n".join(",".join(row) for row in rows) + "\n").encode(
        "utf-8"
    )
