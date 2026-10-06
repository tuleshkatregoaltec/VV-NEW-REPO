from collections.abc import Sequence
from typing import Any

from holocron.platform import bronze
from holocron.platform.bronze import replace_keyed_rows


class FakeClickHouse:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.insert_calls: list[dict[str, Any]] = []

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


def test_replace_keyed_rows_chunks_large_delete_predicates(
    monkeypatch,
) -> None:
    monkeypatch.setattr(bronze, "_MAX_REPLACE_KEYED_DELETE_BYTES", 35)
    clickhouse = FakeClickHouse()

    replace_keyed_rows(
        clickhouse=clickhouse,
        table="example_bronze",
        key_column="property_key",
        key_values=("alpha", "beta", "gamma"),
        rows=(("alpha", 1), ("beta", 2), ("gamma", 3)),
        column_names=("property_key", "value"),
    )

    delete_commands = [command for command in clickhouse.commands if "DELETE WHERE" in command]
    assert delete_commands == [
        "ALTER TABLE `example_bronze` DELETE WHERE `property_key` IN ('alpha', 'beta') "
        "SETTINGS mutations_sync = 1",
        "ALTER TABLE `example_bronze` DELETE WHERE `property_key` IN ('gamma') "
        "SETTINGS mutations_sync = 1",
    ]
    assert clickhouse.insert_calls == [
        {
            "table": "example_bronze",
            "rows": (("alpha", 1), ("beta", 2), ("gamma", 3)),
            "column_names": ("property_key", "value"),
        }
    ]
