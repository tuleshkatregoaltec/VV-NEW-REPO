import gzip
import importlib.util
import json
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest


def _load_script(name: str) -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(profile_id: str, configuration_hash: str) -> dict:
    return {
        "source_account": "account-b",
        "filter_profile": {"id": profile_id},
        "source_location": {"id": "1", "text": "Dubai", "slug": "dubai"},
        "configuration_hash": configuration_hash,
        "shard": {"date": "2026-07-01"},
        "columns": [
            {
                "id": "PATH_NAME",
                "text": "L-07, Greece Cluster, International City Apartment, No. 1204",
            },
            {"id": "PROP_SIZES", "text": "1 Bed 732 sqft"},
            {"id": "TOTAL_PRICES", "text": "38,000 Renewed"},
            {"id": "START_DATE", "text": "1 Jul, 2026 - 30 Jun, 2027 12 Months"},
        ],
    }


class FakeClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, list[list[object]], list[str]]] = []

    def insert(self, table: str, rows: list[list[object]], *, column_names: list[str]) -> None:
        self.inserts.append((table, rows, column_names))


def test_loader_reconciles_profile_union_before_insert(tmp_path: Path) -> None:
    loader = _load_script("load_dxbi_rental_events.py")
    broad_path = tmp_path / "profile=broad" / "location=1" / "date=2026-07-01" / "a.jsonl.gz"
    leaf_path = tmp_path / "profile=leaf" / "location=1" / "date=2026-07-01" / "b.jsonl.gz"
    broad_path.parent.mkdir(parents=True)
    leaf_path.parent.mkdir(parents=True)
    with gzip.open(broad_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(_payload("broad", "12345678901234567890")) + "\n")
    with gzip.open(leaf_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(_payload("leaf", "abcdefghijklmnopqrst")) + "\n")
    client = FakeClient()

    totals = loader.load_files(
        [broad_path, leaf_path],
        client=client,
        min_start_date=date(2025, 1, 1),
        batch_size=100,
    )

    assert totals == {
        "raw_rows": 2,
        "unique_source_rows": 1,
        "normalized_rows": 2,
        "quarantined_rows": 0,
        "profile_overlap_rows": 1,
        "loaded_contracts": 1,
        "out_of_scope_rows": 0,
    }
    assert len(client.inserts) == 1
    table, rows, columns = client.inserts[0]
    assert table == "dxbi_rental_events_v2"
    assert len(rows) == 1
    assert rows[0][columns.index("unit_number")] == "1204"
    assert rows[0][columns.index("source_account")] == "account-b"


def test_loader_quarantines_malformed_json_and_preserves_accounting(tmp_path: Path) -> None:
    loader = _load_script("load_dxbi_rental_events.py")
    path = tmp_path / "date=2026-07-01" / "bad.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{bad json\n")
    quarantine = tmp_path / "quarantine.jsonl"

    totals = loader.load_files(
        [path],
        client=FakeClient(),
        min_start_date=date(2025, 1, 1),
        batch_size=100,
        quarantine_path=quarantine,
    )

    assert totals["raw_rows"] == 1
    assert totals["normalized_rows"] == 0
    assert totals["quarantined_rows"] == 1
    assert quarantine.exists()


def test_active_v1_load_updates_the_app_table_and_retains_legacy_identity(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from holocron.sources.dxbi.rental_events import legacy_rental_event, normalize_rental_row

    loader = _load_script("load_dxbi_rental_events.py")
    payload = _payload("broad", "12345678901234567890")
    event = normalize_rental_row(payload)
    assert event is not None
    canonical = legacy_rental_event(event)
    columns = [
        "event_key",
        "unit_candidate_key",
        "unit_cohort_key",
        "lease_start",
        "lease_end",
        "contract_amount_aed",
        "annual_rent_aed",
        "scraped_at",
        "loaded_at",
    ]

    class ActiveClient(FakeClient):
        def query(self, sql):
            names = columns
            if "dxbi_rental_unit_candidates" in sql:
                names = [*columns[:-2], "observed_contracts", "last_scraped_at", "loaded_at"]
            return SimpleNamespace(result_rows=[(name,) for name in names])

    client = ActiveClient()
    loader.configure_target(client, "active")
    path = tmp_path / "date=2026-07-01" / "row.jsonl"
    path.parent.mkdir()
    path.write_text(json.dumps(payload) + "\n")
    loader.load_files([path], client=client, min_start_date=date(2025, 1, 1), batch_size=100)
    table, rows, inserted_columns = client.inserts[0]
    assert table == "dxbi_rental_events"
    assert "contract_key" not in inserted_columns
    assert rows[0][inserted_columns.index("event_key")] == canonical["event_key"]
    assert rows[0][inserted_columns.index("unit_candidate_key")] == canonical["unit_candidate_key"]


def test_legacy_identity_survives_annualization_and_new_unit_visibility() -> None:
    from holocron.sources.dxbi.rental_events import legacy_rental_event, normalize_rental_row

    event = normalize_rental_row(_payload("broad", "12345678901234567890"))
    assert event is not None
    original = legacy_rental_event(event)
    corrected = legacy_rental_event({**event, "annual_rent_aed": 76_000, "unit_number": "1205"})
    assert original["event_key"] == corrected["event_key"]
    assert original["unit_candidate_key"] == corrected["unit_candidate_key"]
    changed_amount = legacy_rental_event({**event, "contract_amount_aed": 40_000})
    assert original["event_key"] != changed_amount["event_key"]


def test_legacy_checkpoint_failures_prevent_a_successful_reconciliation(tmp_path: Path) -> None:
    loader = _load_script("load_dxbi_rental_events.py")
    (tmp_path / "checkpoint.json").write_text(
        json.dumps(
            {"completed": {"done": {}}, "failed": {"failed": {}}, "paged": {"incomplete": {}}}
        )
    )
    assert loader._partition_counts([tmp_path]) == (3, 1, 2, "")


def test_active_refresh_replaces_hidden_overlap_and_keeps_other_history(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from holocron.sources.dxbi.rental_events import normalize_rental_rows

    loader = _load_script("load_dxbi_rental_events.py")
    loader.TABLE = "dxbi_rental_events"
    hidden = _payload("broad", "12345678901234567890")
    hidden["columns"][0]["text"] = hidden["columns"][0]["text"].replace(", No. 1204", "")
    hidden["source_run_id"] = "old"
    old = normalize_rental_rows([(hidden, "/old/date=2026-07-01/a.jsonl", "account-b")]).events
    distinct = dict(old[0])
    distinct["contract_key"] = "different-amount"
    distinct["contract_amount_aed"] += 1
    distinct["configuration_hash"] = distinct["configuration_hash"].encode()
    distinct["raw_row_fingerprint"] = distinct["raw_row_fingerprint"].encode()
    old.append(distinct)

    class ActiveClient(FakeClient):
        commands: list[str] = []

        def query(self, sql, parameters):
            return SimpleNamespace(named_results=lambda: iter(old))

        def command(self, sql, parameters=None):
            self.commands.append(sql)

    path = tmp_path / "date=2026-07-01" / "row.jsonl"
    path.parent.mkdir()
    payload = _payload("broad", "12345678901234567890")
    payload["source_run_id"] = "new"
    path.write_text(json.dumps(payload) + "\n")
    client = ActiveClient()
    totals = loader.load_files(
        [path], client=client, min_start_date=date(2025, 1, 1), batch_size=100
    )
    assert totals["out_of_scope_rows"] == 0
    assert totals["loaded_contracts"] == 2
    assert client.inserts[0][1][0][loader.COLUMNS.index("unit_number")] == "1204"
    assert all(
        isinstance(row[loader.COLUMNS.index("configuration_hash")], str)
        for row in client.inserts[0][1]
    )
    assert "WHERE lease_start NOT IN" in client.commands[-3]
    assert client.commands[-2] == (
        "EXCHANGE TABLES dxbi_rental_events AND dxbi_rental_events_history_refresh"
    )


def test_invalid_active_refresh_never_exchanges_canonical_data(tmp_path: Path) -> None:
    from types import SimpleNamespace

    loader = _load_script("load_dxbi_rental_events.py")
    loader.TABLE = "dxbi_rental_events"

    class ActiveClient(FakeClient):
        commands: list[str] = []

        def query(self, sql, parameters):
            return SimpleNamespace(named_results=lambda: iter([]))

        def command(self, sql, parameters=None):
            self.commands.append(sql)

    path = tmp_path / "date=2026-07-01" / "bad.jsonl"
    path.parent.mkdir()
    path.write_text("{bad\n")
    client = ActiveClient()
    with pytest.raises(RuntimeError, match="previous data retained"):
        loader.load_files([path], client=client, min_start_date=date(2025, 1, 1), batch_size=100)
    assert not any("EXCHANGE" in command for command in client.commands)
