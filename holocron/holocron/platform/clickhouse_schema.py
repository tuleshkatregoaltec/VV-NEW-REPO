from __future__ import annotations

from pathlib import Path

from holocron.contracts import ClickHouseCommands

_cached_statements: list[str] | None = None


def schema_sql_path() -> Path:
    return Path(__file__).resolve().parents[1] / "lib" / "sql" / "clickhouse_schema.sql"


def iter_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    index = 0
    while index < len(sql):
        character = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if not in_single_quote and character == "-" and following == "-":
            newline = sql.find("\n", index + 2)
            if newline == -1:
                break
            current.append("\n")
            index = newline + 1
            continue
        if character == "'":
            current.append(character)
            if in_single_quote and following == "'":
                current.append(following)
                index += 2
                continue
            in_single_quote = not in_single_quote
            index += 1
            continue
        if character == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(character)
        index += 1
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def ensure_schema(*, clickhouse: ClickHouseCommands) -> None:
    global _cached_statements
    if _cached_statements is None:
        sql_path = schema_sql_path()
        if not sql_path.exists():
            raise FileNotFoundError(f"Missing ClickHouse schema file: {sql_path}")
        _cached_statements = iter_sql_statements(sql_path.read_text(encoding="utf-8"))
    for statement in _cached_statements:
        clickhouse.command(statement)
