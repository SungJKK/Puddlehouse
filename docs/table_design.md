# Catalog Tables

The SQLite catalog (`catalog.db`) tracks all metadata for the lakehouse. It is hand-rolled — no external catalog framework is used. There are twelve tables.

---

## catalog_tables

The central registry. Every Parquet dataset in the warehouse has exactly one row here.

| Column | Type | Description |
|---|---|---|
| `table_id` | TEXT PK | Composite key `"{zone}.{entity}"`, e.g. `"silver.events"` |
| `name` | TEXT | Human-readable name, e.g. `"silver_events"` |
| `zone` | TEXT | Data zone: `bronze`, `silver`, or `gold` |
| `entity` | TEXT | Logical entity name, e.g. `events`, `users`, `orders` |
| `location` | TEXT | Absolute path to the folder containing Parquet files |
| `owner` | TEXT | Owner identifier, defaults to `"system"` |
| `created_at` | TEXT | UTC ISO-8601 timestamp, set on insert |
| `updated_at` | TEXT | UTC ISO-8601 timestamp, updated on schema change or new snapshot |
| `row_count` | INTEGER | Latest known row count, synced on each snapshot |
| `is_active` | INTEGER | Soft-delete flag: `1` = active, `0` = deleted |

> **Changed from previous design:** `schema_json` (a JSON blob encoding column definitions) has been removed. Column definitions are now stored as versioned rows in `catalog_columns`, enabling queryable schema history and proper schema evolution tracking.

---

## catalog_columns

Versioned column definitions for each table. Each column is a row here; when a column is added, renamed, or dropped, a new row is inserted (or `dropped_at_version` is set) rather than overwriting anything. This makes schema evolution fully auditable and enables reading historical snapshots with the schema that was active at the time.

| Column | Type | Description |
|---|---|---|
| `column_id` | TEXT PK | UUID |
| `table_id` | TEXT FK → `catalog_tables.table_id` | The table this column belongs to |
| `column_name` | TEXT | Column name as it appears in the Parquet file |
| `column_type` | TEXT | Data type string, e.g. `"int64"`, `"utf8"`, `"float64"` |
| `column_order` | INTEGER | Zero-based position in the schema |
| `nulls_allowed` | INTEGER | `1` if nullable, `0` if NOT NULL |
| `default_value` | TEXT | Default value expression (nullable) |
| `added_at_version` | INTEGER | Snapshot version when this column was added |
| `dropped_at_version` | INTEGER | Snapshot version when this column was dropped; `NULL` if still active |

To get the active schema for a table at a given snapshot version `V`:
```sql
SELECT * FROM catalog_columns
WHERE table_id = ?
  AND added_at_version <= V
  AND (dropped_at_version IS NULL OR dropped_at_version > V)
ORDER BY column_order;
```

---

## catalog_snapshots

Immutable point-in-time versions of a table. Each write operation commits a new snapshot, which serves as the atomic unit of change. The files belonging to a snapshot are stored in `catalog_files` (not in an external JSON file on disk), keeping the catalog fully self-contained in SQLite.

| Column | Type | Description |
|---|---|---|
| `snapshot_id` | TEXT PK | UUID |
| `table_id` | TEXT FK → `catalog_tables.table_id` | The table this snapshot belongs to |
| `version` | INTEGER | Monotonically increasing version number per table |
| `row_count` | INTEGER | Cumulative row count up to and including this snapshot, adjusted for logical deletes (raw writes minus total deleted rows at commit time) |
| `byte_size` | INTEGER | Total byte size across all Parquet files in this snapshot |
| `created_at` | TEXT | UTC ISO-8601 timestamp |

> **Changed from previous design:** `manifest_path` (a pointer to an external JSON file on disk) has been removed. File membership is now stored directly in `catalog_files`, eliminating the external JSON dependency and making the catalog a single source of truth.

---

## catalog_files

Maps each snapshot to the exact set of live Parquet data files it contains. This replaces the previous external manifest JSON files. To reconstruct any version of a table, join `catalog_snapshots` → `catalog_files` → read the listed paths.

| Column | Type | Description |
|---|---|---|
| `file_id` | TEXT PK | UUID |
| `snapshot_id` | TEXT FK → `catalog_snapshots.snapshot_id` | The snapshot this file belongs to |
| `table_id` | TEXT FK → `catalog_tables.table_id` | Denormalized for fast file lookup by table |
| `file_path` | TEXT | Absolute path to the Parquet file |
| `row_count` | INTEGER | Row count within this file (before any logical deletes) |
| `byte_size` | INTEGER | File size in bytes |

---

## catalog_delete_files

Tracks logical delete files — small Parquet files that record which row positions in a data file have been deleted, without rewriting the original file. When reading a table, the query engine loads the data file and subtracts any matching delete entries before returning results.

A delete file always targets exactly one data file (`file_id`). Deletes are applied cumulatively: if two delete files target the same data file, both are applied.

| Column | Type | Description |
|---|---|---|
| `delete_file_id` | TEXT PK | UUID |
| `table_id` | TEXT FK → `catalog_tables.table_id` | The table this delete belongs to |
| `snapshot_id` | TEXT FK → `catalog_snapshots.snapshot_id` | Snapshot in which this delete was committed |
| `file_id` | TEXT FK → `catalog_files.file_id` | The data file whose rows are being logically deleted |
| `delete_file_path` | TEXT | Absolute path to the Parquet delete file (contains deleted row positions) |
| `delete_count` | INTEGER | Number of rows deleted |
| `byte_size` | INTEGER | Size of the delete file in bytes |
| `created_at` | TEXT | UTC ISO-8601 timestamp |

To read a table at snapshot version `V`, for each data file apply all delete files where `snapshot_id.version <= V`.

---

## catalog_column_stats

Per-table, per-column aggregate statistics across the entire current table. Updated on each snapshot commit. Used for high-level query planning and data quality visibility.

| Column | Type | Description |
|---|---|---|
| `table_id` | TEXT FK → `catalog_tables.table_id` | The table |
| `column_id` | TEXT FK → `catalog_columns.column_id` | The column |
| `null_count` | INTEGER | Total null values across all files |
| `min_value` | TEXT | Serialized minimum value (cast to TEXT for generality) |
| `max_value` | TEXT | Serialized maximum value |
| `updated_at` | TEXT | UTC ISO-8601 timestamp of last update |

PRIMARY KEY is `(table_id, column_id)`.

---

## catalog_file_column_stats

Per-file, per-column statistics. Written once when a file is first committed and never updated (files are immutable). This is what enables **file-level predicate pushdown**: before handing a file to DuckDB, the query planner checks these stats to determine whether the file can be skipped entirely.

Example: `WHERE amount > 400` — any file whose `max_value` for `amount` is `≤ 400` is skipped without being opened.

| Column | Type | Description |
|---|---|---|
| `file_id` | TEXT FK → `catalog_files.file_id` | The data file |
| `table_id` | TEXT FK → `catalog_tables.table_id` | Denormalized for fast lookup |
| `column_id` | TEXT FK → `catalog_columns.column_id` | The column |
| `value_count` | INTEGER | Total values (including nulls) in this column in this file |
| `null_count` | INTEGER | Number of null values |
| `min_value` | TEXT | Serialized minimum non-null value |
| `max_value` | TEXT | Serialized maximum non-null value |
| `column_size_bytes` | INTEGER | Compressed byte size of this column in the file |

PRIMARY KEY is `(file_id, column_id)`.

---

## catalog_views

Stores view and materialized view definitions. A view is a named SQL query; a materialized view is a view whose result has been physically written to a Parquet snapshot and cached until the next refresh.

| Column | Type | Description |
|---|---|---|
| `view_id` | TEXT PK | UUID |
| `view_name` | TEXT | Name of the view |
| `zone` | TEXT | Data zone the view logically belongs to: `bronze`, `silver`, or `gold` |
| `view_type` | TEXT | `"view"` or `"materialized_view"` |
| `sql` | TEXT | The SQL query that defines this view |
| `owner` | TEXT | Owner identifier, defaults to `"system"` |
| `created_at` | TEXT | UTC ISO-8601 timestamp |
| `updated_at` | TEXT | UTC ISO-8601 timestamp |
| `is_active` | INTEGER | Soft-delete flag: `1` = active, `0` = deleted |
| `last_refreshed_at` | TEXT | For materialized views: UTC timestamp of last successful refresh; `NULL` for plain views or if never refreshed |
| `refresh_snapshot_id` | TEXT FK → `catalog_snapshots.snapshot_id` | For materialized views: the snapshot that holds the cached result; `NULL` for plain views |

A plain view is always computed at query time from its `sql`. A materialized view behaves like a plain view until it has been refreshed — once refreshed, reads are served from `refresh_snapshot_id` instead of re-executing `sql`.

---

## catalog_lineage

Records data flow between tables (or from external sources into tables). One row per job run that produced a target table from a source.

| Column | Type | Description |
|---|---|---|
| `lineage_id` | TEXT PK | UUID |
| `source_id` | TEXT | Source table_id or an external label like `"external:s3"` |
| `target_id` | TEXT FK → `catalog_tables.table_id` | The table that was produced |
| `job_name` | TEXT | Name of the transformation job |
| `run_id` | TEXT | Run identifier for the job execution |
| `rows_read` | INTEGER | Rows consumed from the source |
| `rows_written` | INTEGER | Rows written to the target |
| `created_at` | TEXT | UTC ISO-8601 timestamp |

---

## catalog_partitions

Tracks individual Parquet files for partitioned tables. Each row maps a single partition key/value pair to a specific file.

| Column | Type | Description |
|---|---|---|
| `partition_id` | TEXT PK | MD5 hash of `table_id + partition_key + partition_val + file_path` |
| `table_id` | TEXT FK → `catalog_tables.table_id` | The table this partition belongs to |
| `partition_key` | TEXT | Partition column name, e.g. `"date"` |
| `partition_val` | TEXT | Partition value, e.g. `"2025-01-01"` |
| `file_path` | TEXT | Absolute path to the Parquet file for this partition |
| `row_count` | INTEGER | Row count within this partition file |
| `created_at` | TEXT | UTC ISO-8601 timestamp |

---

## catalog_audit_log

Append-only log of every write operation performed through `CatalogManager`. Used for debugging and operational visibility.

| Column | Type | Description |
|---|---|---|
| `log_id` | TEXT PK | UUID |
| `operation` | TEXT | Operation type: `REGISTER`, `SNAPSHOT`, `LINEAGE`, `DELETE`, `VIEW` |
| `table_id` | TEXT | The table affected (nullable for non-table operations) |
| `details` | TEXT | JSON blob with operation-specific context |
| `created_at` | TEXT | UTC ISO-8601 timestamp |

---

## catalog_quality_contracts

Stores quality check definitions for tables. Each row is one contract — a named check type and its parameters. Contracts are evaluated on demand via the `/quality/run` endpoint; no files are read, only catalog metadata is inspected.

| Column | Type | Description |
|---|---|---|
| `contract_id` | TEXT PK | UUID |
| `table_id` | TEXT FK → `catalog_tables.table_id` | The table this contract applies to |
| `check_type` | TEXT | Contract kind: `not_empty`, `freshness_days`, or `max_null_fraction` |
| `params` | TEXT | JSON blob of check-specific parameters, e.g. `{"min_rows": 1}` |
| `created_at` | TEXT | UTC ISO-8601 timestamp |
| `is_active` | INTEGER | Soft-delete flag: `1` = active, `0` = deactivated |

No index exists for this table — contract lists are always looked up by `table_id` with a full scan, which is acceptable given the expected low row count.

---

## Relationships

```
catalog_tables    (1) ──< catalog_columns          (many versioned columns per table)
catalog_tables    (1) ──< catalog_snapshots         (many versions per table)
catalog_snapshots (1) ──< catalog_files             (many files per snapshot)
catalog_tables    (1) ──< catalog_files             (denormalized — fast file lookup by table)
catalog_files     (1) ──< catalog_delete_files      (many logical deletes per data file)
catalog_files     (1) ──< catalog_file_column_stats (one stats row per column per file)
catalog_tables    (1) ──< catalog_column_stats      (one aggregate stats row per column per table)
catalog_columns   (1) ──< catalog_column_stats      (stats tied to versioned column)
catalog_columns   (1) ──< catalog_file_column_stats (stats tied to versioned column)
catalog_tables    (1) ──< catalog_lineage           (many jobs produced this table)
catalog_tables    (1) ──< catalog_partitions        (many partition files per table)
catalog_tables    (1) ──< catalog_audit_log         (many audit entries per table)
catalog_tables    (1) ──< catalog_quality_contracts (many quality contracts per table)
catalog_views     (0..1) ─ catalog_snapshots        (materialized views reference a result snapshot)
```

`catalog_lineage.source_id` is a plain TEXT column (not a foreign key) so it can reference either a `table_id` or a free-form external source label.

---

## Indexes

| Index | Table | Column(s) | Purpose |
|---|---|---|---|
| `idx_columns_table` | `catalog_columns` | `table_id` | Fast column listing by table |
| `idx_snapshots_table` | `catalog_snapshots` | `table_id` | Fast snapshot lookup by table |
| `idx_files_snapshot` | `catalog_files` | `snapshot_id` | Fast file listing by snapshot |
| `idx_files_table` | `catalog_files` | `table_id` | Fast file listing by table |
| `idx_delete_files_file` | `catalog_delete_files` | `file_id` | Fast delete lookup by data file |
| `idx_delete_files_snapshot` | `catalog_delete_files` | `snapshot_id` | Fast delete lookup by snapshot |
| `idx_file_col_stats_file` | `catalog_file_column_stats` | `file_id` | Fast stats lookup by file |
| `idx_lineage_target` | `catalog_lineage` | `target_id` | Fast lineage lookup by target table |
| `idx_partitions_table` | `catalog_partitions` | `table_id` | Fast partition listing by table |
