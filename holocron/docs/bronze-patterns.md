# Bronze Loading Patterns

Bronze loaders transform raw S3 releases into ClickHouse tables. In standard
medallion terminology bronze is usually the immutable append-only raw layer.
Holocron keeps that immutable history in raw S3 manifests, so ClickHouse
`*_bronze` tables are the current raw-shaped warehouse surface used by Dagster
and downstream jobs. Loaders therefore use delete+insert upserts around the
affected source keys, date windows, or full-refresh table contents.

## Source Contract Wiring

Every source that has a bronze stage declares it in `source.py` using lazy
entrypoints so the heavy bronze module is not imported at import time:

```python
from holocron.sources.entrypoints import lazy_bronze_loader, lazy_extractor

extract_release = lazy_extractor(f"{__package__}.extract")
load_bronze = lazy_bronze_loader(f"{__package__}.bronze")

SOURCE = SourceSpec(
    ...
    bronze_loader=load_bronze,
    bronze_tables=(
        BronzeTable(name="source_name_bronze"),
    ),
)
```

Multiple bronze tables are listed when a single raw release feeds more than one
ClickHouse table (e.g. Reelly projects, documents, and availability in one run).

Sources that are raw-only (no bronze stage) omit `bronze_loader` and
`bronze_tables` from their `SourceSpec`.

## Bronze Loader Signature

Every `bronze.py` exposes exactly one public function:

```python
def load_release_to_clickhouse(
    *,
    raw_release: RawManifest,
    s3: RawFileStore,
    clickhouse: ClickHouseInserter,
) -> BronzeLoadResult:
```

`BronzeLoadResult` is:

```python
{
    "source": str,
    "run_id": str,
    "table_row_counts": dict[str, int],   # table_name -> row count
    "table_count": int,
    "total_rows": int,
}
```

The generic Dagster bronze asset wrapper calls this function and records the
result as asset metadata. The loader must not write to S3 or advance any
checkpoint — that is the raw asset's job.

## Schema Initialisation

Every loader calls `ensure_schema` before inserting rows. This issues each
`CREATE TABLE IF NOT EXISTS` statement from `holocron/lib/sql/clickhouse_schema.sql`
against ClickHouse. The call is idempotent and is safe to repeat on every load.

Most loaders import the shared helper:

```python
from holocron.platform.clickhouse_schema import ensure_schema

ensure_schema(clickhouse=clickhouse)
```

## Downloading Raw Files

Loaders download raw files to a `TemporaryDirectory` before parsing:

```python
with TemporaryDirectory(prefix=f"holocron-{source}-bronze-{run_id}-") as scratch:
    scratch_path = Path(scratch)
    local_path = download_manifest_file(
        file_name=file_name,
        file_entry=file_entry,
        s3=s3,
        scratch_path=scratch_path,
        source_label="MySource",
    )
    for raw_row in read_jsonl_manifest_rows(
        path=local_path,
        file_entry=file_entry,
        source_label="MySource",
    ):
        rows.append(_row_tuple(raw_row, fallback_run_id=run_id))
```

Use `require_manifest_file` when the file must be present, or
`files_by_name.get(file_name)` when a file is optional (absent in older
releases that predate a new output file).

## Delete Strategies

Bronze loaders must be idempotent and current-state compatible — replaying the
same raw manifest must produce the same table state, and recurring incremental
loads must not accumulate duplicates for overlapping source windows or keys.
There are three patterns in use:

### 1. Replace affected source keys

Used when an incremental run reports changed/current entities by stable source
keys:

```python
replace_keyed_rows(
    clickhouse=clickhouse,
    table="pf_listings_bronze",
    key_column="property_key",
    key_values=[row[0] for row in listing_rows],
    rows=listing_rows,
    column_names=_COLUMNS,
)
```

Used by: Reelly and Property Finder listings. Child tables are usually replaced
by parent entity key when a fresh detail payload is present, so removed child
rows do not linger for entities that were re-fetched.

### 2. Delete by date window (DLD open data, DXBI)

Used when rows belong to a date range that can overlap between runs:

```python
delete_predicate = _slice_delete_predicate(table_rows)
clickhouse.command(
    f"ALTER TABLE {table} DELETE WHERE {delete_predicate} "
    "SETTINGS mutations_sync = 1"
)
clickhouse.insert_rows(table=table, rows=table_rows, column_names=_COLUMNS)
```

The predicate targets the same date windows seen in the new batch, so a replay
with the same input produces the same rows without accumulating duplicates.
DLD also reads page rows so a complete zero-row date window clears stale rows
from previous overlapping lookback runs. Incomplete paginated DLD chunks are
rejected for current-state bronze because they cannot safely replace a window.

### 3. Full table replace (DDA, Property Finder locations)

Used for full-refresh sources where the raw release is always the complete
current snapshot:

```python
row_count = clickhouse.replace_table_rows(
    table=_TABLE_NAME,
    rows=rows,
    column_names=_COLUMNS,
)
```

`replace_table_rows` writes to a staging table and renames, making the swap
atomic. Used when stale rows from a previous release must not survive the load.

## DLD Open Data Shared Loader

The nine DLD open-data sources (`dld_od_transactions`, `dld_od_rents`, etc.) all
share one implementation. Each `bronze.py` is a one-liner:

```python
from holocron.sources.dld_open_data_bronze import build_open_data_bronze_loader

load_release_to_clickhouse = build_open_data_bronze_loader(source_name="dld_od_transactions")
```

`build_open_data_bronze_loader` returns a configured loader using the date-window
delete strategy against the source-specific table.

## Row Key Design

Every bronze table has a deterministic string key (usually `*_key`) computed
from stable identifiers in the raw row. This is a SHA-1 hex digest of the
pipe-joined key components:

```python
def _hash_key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()
```

SHA-1 is used for space efficiency only — collision resistance is not required
for this use case.

## Null Safety

Use `string_value` from `holocron.platform.raw_files` to extract strings from
raw rows. It coerces `None` to `""` and strips whitespace. Ints are parsed with
a two-step `int(value)` → `int(float(value))` fallback to handle values stored
as numeric strings or floats in the raw JSON.

## What Bronze Loaders Must Not Do

- Write to S3 or modify checkpoints.
- Raise on missing optional files (use `.get(file_name)` and return `[]`).
- Perform business logic or derivations not present in the raw rows.
- Import from other source packages.
- Call `ensure_schema` conditionally — always call it; it is idempotent.
