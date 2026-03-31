
## Puddlehouse Architecture

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │  lh CLI  (Typer)                                                     │
  │  cli/commands/*  →  cli/client.py  →  HTTP/JSON  →  FastAPI          │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────────┐
  │  FastAPI  (api/)                                                     │
  │  10 routers: tables · snapshots · schema · data · query ·           │
  │              stats · views · lineage · partitions · governance       │
  └─────────────┬────────────────────────────────────────┬──────────────┘
                │                                        │
  ┌─────────────▼──────────────┐          ┌─────────────▼──────────────┐
  │  storage/writer.py         │          │  query/engine.py            │
  │  (PyArrow + Parquet)       │          │  (DuckDB)                   │
  └─────────────┬──────────────┘          └─────────────┬──────────────┘
                │                                        │
                │  write / commit                        │  resolve files
                └──────────────────┬─────────────────────┘
                                   │
  ┌────────────────────────────────▼─────────────────────────────────────┐
  │  SQLite Catalog  (warehouse/catalog.db)                              │
  │                                                                      │
  │  catalog_tables · catalog_columns · catalog_snapshots ·              │
  │  catalog_files · catalog_delete_files · catalog_column_stats ·       │
  │  catalog_file_column_stats · catalog_views · catalog_lineage ·       │
  │  catalog_partitions · catalog_audit_log · catalog_quality_contracts  │
  └────────────────────────────────┬─────────────────────────────────────┘
                                   │
  ┌────────────────────────────────▼─────────────────────────────────────┐
  │  warehouse/                                                          │
  │  <zone>/<entity>/<run-uuid>.parquet  (append-only, immutable)        │
  │  Zones: bronze · silver · gold                                       │
  └──────────────────────────────────────────────────────────────────────┘
```

---

## Write Path

**File first, then atomic catalog commit.**

The writer (`storage/writer.py`) follows a strict two-phase sequence:

1. Write Parquet files to disk with PyArrow (`pq.write_table` or `pq.write_to_dataset` for partitioned tables).
2. Read back file metadata (row count, byte size) and per-column statistics from the Parquet footer — without loading any data.
3. Validate schema evolution against what the catalog already knows.
4. Call `catalog.commit_write(...)`, which executes all catalog mutations in a **single SQLite transaction**: table upsert, snapshot creation, file registration, column upsert, per-file stats, aggregate stats, lineage, and partitions.

**Why file first?**
The alternative — write catalog first, then write the file — would leave the catalog pointing to a file that may not exist yet if the write fails midway. The chosen order is safer: if the Parquet write fails, the catalog is untouched and the table remains in its prior clean state. If the catalog commit fails after the file is written, the file is orphaned on disk but the catalog is still consistent. Orphaned files are recoverable via `vacuum`.

**Why a single transaction for catalog?**
All catalog side effects of a write (snapshot, files, columns, stats, lineage, partitions) are committed atomically via a `with self._connect() as con:` block, which SQLite treats as a transaction. If anything inside that block raises, SQLite rolls back all changes. This means the catalog is never left in a half-committed state where, for example, a snapshot exists but its files are missing.

---

## Snapshot Model and Time Travel

Every write creates a new **snapshot** — a monotonically increasing integer version. Snapshots are immutable records: they are never updated, only appended.

The file-to-snapshot relationship is cumulative. `get_table_files_at_version(table_id, v)` returns all files from snapshots with `version <= v`. This reflects the append-only nature of the format: each new write adds files on top of the previous state rather than replacing them.

**Time travel** is implemented entirely in the query layer: `QueryEngine.query(... version=N)` asks the catalog for the file set at version N, then creates a DuckDB view over exactly those files. This means time travel works without any special file format support — it is purely a catalog-level operation.

**Tradeoff:** Because the file set is cumulative, querying old versions still reads all physical files that existed at that point, even if some were logically deleted by later snapshots. The volume of files queried for old versions grows with the write history. Vacuum (see below) is the mechanism for reclaiming disk space and bounding this cost.

---

## Schema Evolution

The catalog tracks schema at two levels:

- **`catalog_columns`**: one row per column, per table. Each column has `added_at_version` (when it was first seen) and `dropped_at_version` (NULL while active, set to the version when it disappeared from the schema). This gives a full point-in-time schema for any version.
- **`get_schema_at_version(table_id, version)`**: reconstructs the active column set at any historical version by filtering on `added_at_version <= v AND (dropped_at_version IS NULL OR dropped_at_version > v)`.

**Enforcement (`validate_schema_evolution`)**:
- **Allowed**: adding new columns.
- **Disallowed**: removing a column, changing a column's type.

Enforcement happens in the writer before the catalog commit — validation fires before any catalog state is modified. If the incoming schema removes a column or changes a type, a `SchemaEvolutionError` is raised and the write is aborted. The file has already been written to disk at this point (file-first), but the catalog remains unchanged, so the orphaned file can be cleaned up by vacuum.

**Why these rules?** Dropping columns or changing types would invalidate historical queries that relied on those columns being present. Since files are immutable, old files still carry the old schema. Enforcing additive-only evolution keeps every file readable under any snapshot's schema.

---

## Partitioning

When `partition_cols` is provided to `write_parquet`, PyArrow's `write_to_dataset` writes Hive-style partition directories (`date=2025-01-01/`, etc.). The catalog mirrors this in `catalog_partitions`: one row per (partition_key, partition_val, file_path) combination.

**Partition pruning in the query engine**: before executing SQL, `QueryEngine._prune_by_partitions` consults `catalog_partitions` to exclude files whose partition values don't match the requested filters. Files with no partition records are always included (they can't be pruned because the catalog has no partition information for them). The pruning is conservative in this direction — it never excludes a file it is uncertain about.

**Partition IDs are content-addressed**: `hashlib.md5(table_id + key + val + file_path)` is used as the partition_id, with `INSERT OR REPLACE`. This makes re-registering the same partition on repeat writes idempotent.

**Limitation**: partitioned writes currently re-scan the entire partition directory for written files (`out_dir.rglob("*.parquet")`), which means re-registering files from previous writes. The query engine deduplicates file paths before executing, but the catalog_partitions table may accumulate duplicate entries if the same file appears in multiple writes. The `INSERT OR REPLACE` on the content-addressed ID mitigates this.

---

## Column Statistics

Two levels of stats are collected on every write:

**1. Table-level aggregate stats (`catalog_column_stats`)**
One row per (table, column). Stores `min_value`, `max_value`, `null_count` aggregated over the entire write batch. Updated on every write via `INSERT OR REPLACE`. Reflects the state from the most recent write, not the full historical table.

**2. Per-file, per-column stats (`catalog_file_column_stats`)**
One row per (file, column). Stats are read from the Parquet footer metadata (row group statistics) without loading any data into memory. Stores `value_count`, `null_count`, `min_value`, `max_value`, and `column_size_bytes`.

**Why two levels?** Table-level stats give fast answers for data quality checks and catalog browsing without scanning files. Per-file stats are the foundation for future file-skipping during queries (predicate pushdown) — the query engine can inspect the per-file min/max before deciding which files to read.

**Stats are read from the Parquet footer**, not recomputed from the data. This is zero-copy: `pq.ParquetFile(path).metadata` reads only the footer. The tradeoff is that footer statistics are only as accurate as the writer that produced the file — if statistics were disabled at write time, the catalog will store NULL.

---

## Logical Deletes

The catalog tracks deletes in `catalog_delete_files`. A delete record points to a specific `file_id` (a Parquet data file) and references a `delete_file_path` — a separate file that encodes which rows are logically removed.

This follows Iceberg's equality-delete pattern: data files are never mutated. A delete is a new file that the reader must apply on top of the data file. The catalog links them explicitly via `file_id`.

**Current limitation**: the query engine (`query/engine.py`) does not yet apply delete files at read time. `QueryEngine.query` resolves data files via snapshots but does not join against `catalog_delete_files`. Delete files are registered and tracked in the catalog but are not enforced during reads. This is a known gap — applying equality deletes at query time requires a filter pass in DuckDB after loading the data file.

---

## Compaction

`compact(zone, entity)` merges all physical files from the latest snapshot into a single new Parquet file and commits it as a new snapshot. Old snapshots and their files are left untouched on disk, preserving time travel to any prior version.

**Why compact?** Each write appends a new file. Without compaction, a table with many writes accumulates many small files, and queries must open all of them. Compaction reduces file count and improves scan performance. It also resets the per-file stats on the compacted file.

**Compaction is always a new snapshot**, not a replacement. The compacted file is registered as a new write, meaning the previous write history is preserved. `vacuum` is the separate operation that actually removes old files from disk.

---

## Vacuum

`vacuum(table_id, retain_last_n, dry_run)` deletes Parquet files from disk for snapshots older than the retention window (`retain_last_n` controls how many recent snapshots to keep). It also removes the corresponding `catalog_files` entries.

**After vacuum, time travel to expired snapshots fails** — there are no longer any files for the query engine to read. The snapshots remain in `catalog_snapshots` as tombstones (version history), but their files are gone.

`dry_run=True` (the default in the API) returns the list of eligible files without deleting anything, allowing inspection before committing.

**Vacuum is not automatic.** It must be explicitly triggered. This is intentional — deleting files is irreversible, and the right retention policy is workload-dependent.

---

## Views

Views are stored SQL expressions registered in `catalog_views`. Two types:

- **`view`**: a named SQL definition. The query is stored; execution happens at read time against the current snapshot.
- **`materialized_view`**: same as a view, but with a `refresh_snapshot_id` pointer. Refreshing a materialized view creates a new snapshot from the query result and updates this pointer. Between refreshes the materialized view may be stale.

Views are not enforced by DuckDB at the storage layer — they are metadata-only. The API exposes them for catalog browsing and for the query router to potentially resolve named views to their SQL.

---

## Lineage

Every write automatically records a lineage entry in `catalog_lineage`:
- `source_id`: the origin of the data (defaults to `"external"` for manual writes, `"external:api"` for API writes, or a `table_id@vN` reference for compaction).
- `target_id`: the table being written to.
- `job_name`, `run_id`: free-form labels identifying the pipeline job.

Lineage is directional: `get_lineage(table_id, direction="upstream")` returns what fed this table; `direction="downstream"` returns what this table feeds into. `direction="both"` returns both.

**Lineage is recorded at write time, not computed.** This is a catalog-only feature — it does not inspect dataflow or code. If a pipeline forgets to set `source_id`, the lineage record defaults to `"external"` and the upstream is unknown.

---

## Audit Log

`catalog_audit_log` records every mutating catalog operation with a timestamp and a JSON `details` blob. Operations currently logged:

| Operation    | Triggered by                           |
|-------------|----------------------------------------|
| `REGISTER`  | Table registration (on every write)    |
| `DEREGISTER`| Soft-delete of a table                 |
| `SNAPSHOT`  | Every committed write                  |
| `DELETE`    | Logical delete file registration       |
| `LINEAGE`   | Every committed write                  |
| `VIEW`      | View registration                      |
| `VACUUM`    | Each file deleted during vacuum        |

The audit log is append-only and is never modified after insertion. It is queryable via `GET /api/v1/tables/{zone}/{entity}/audit`.

---

## Quality Contracts

Quality contracts are per-table rules stored in `catalog_quality_contracts`. The supported check types are:

- **`not_empty`**: fails if the table has zero rows.
- **`freshness_days`**: fails if the most recent snapshot is older than `params.days` days.
- **`max_null_fraction`**: fails if any column's null fraction exceeds `params.threshold` (0–1).

`run_quality_checks(table_id)` evaluates all active contracts for the table using current catalog state (no file reads). Each check returns `{"check_type", "passed", "message"}`.

**Checks are catalog-only, not file-level.** They rely on stats and snapshot timestamps stored in the catalog. If stats are stale (e.g. from a write that produced incomplete Parquet footer stats), a quality check may give a false pass or fail.

---

## Catalog: What It Tracks

| Concern              | Table(s)                                                    |
|---------------------|-------------------------------------------------------------|
| Table registry       | `catalog_tables`                                            |
| Schema               | `catalog_columns` (with version ranges)                     |
| Snapshot history     | `catalog_snapshots`                                         |
| File manifest        | `catalog_files`                                             |
| Logical deletes      | `catalog_delete_files`                                      |
| Aggregate stats      | `catalog_column_stats`                                      |
| Per-file stats       | `catalog_file_column_stats`                                 |
| Views                | `catalog_views`                                             |
| Data lineage         | `catalog_lineage`                                           |
| Partition layout     | `catalog_partitions`                                        |
| Audit trail          | `catalog_audit_log`                                         |
| Quality contracts    | `catalog_quality_contracts`                                 |

**What the catalog does not track:**
- Whether a physical file still exists on disk. The catalog assumes files are immutable and present unless vacuum has been run. There is no file-existence check at query time.
- Concurrent writers. SQLite serializes writes via its locking model, but there is no optimistic concurrency control (OCC) or version-fencing between concurrent API calls. Two simultaneous writes will serialize correctly at the SQLite level but there is no conflict detection (e.g. two writers both reading `MAX(version) = 5` and both trying to commit version 6).
- Cross-zone consistency. Each `zone.entity` is an independent table. There is no cross-table transaction — a pipeline that writes silver and gold in one logical step will produce two separate catalog commits.

---

## Catalog Failure Modes

**File written, catalog commit fails**: the Parquet file is on disk but has no catalog entry. The file is invisible to the query engine. Cleaning it up requires manual intervention or vacuum (though vacuum only knows about files the catalog registered). This is the main operational risk of the file-first approach.

**Catalog commit partially succeeds**: impossible within a single `commit_write` call because all mutations happen in one SQLite transaction. If the process crashes inside the `with con:` block, SQLite rolls back all changes on the next connection.

**Schema evolution validation fires after file write**: if `validate_schema_evolution` raises, the file is already on disk (orphaned). The writer raises before calling `commit_write`, so the catalog is clean. The orphaned file will accumulate over time and must be cleaned up manually.

**Vacuum removes files that a slow reader is still using**: there is no reference counting or file leasing. A query in progress that has resolved a file path may fail with a file-not-found error if vacuum deletes that file mid-query.

**Stats accuracy**: column stats in `catalog_file_column_stats` are read from Parquet row group statistics. If the Parquet writer (PyArrow) produced a file without statistics (e.g. for certain complex types), the catalog stores NULL for min/max. Quality checks and future predicate pushdown will be degraded for those columns.

---

## API Layer

The FastAPI app (`api/`) is a thin HTTP interface over the catalog and storage layers. Responsibilities:

- Route HTTP requests to the right catalog or storage operation.
- Validate request shapes via Pydantic models.
- Translate internal exceptions (`KeyError`, `ValueError`, `SchemaEvolutionError`) to appropriate HTTP status codes (404, 400, 422).
- Share a single `CatalogManager` and `QueryEngine` instance across requests via `api/deps.py` (initialized at startup in the lifespan handler).

The API does not own any business logic — all writes, reads, and catalog mutations go through `storage/writer.py`, `query/engine.py`, and `catalog/manager.py` directly.

**Versioning**: all routes are under `/api/v1/`. The version prefix is applied at the router registration level in `api/main.py`.

---

## CLI Layer

The CLI (`cli/`) is a Typer app with one command group per domain, mirroring the API routers. All CLI commands make HTTP calls to the running API server via `cli/client.py` — the CLI is a pure client and has no direct dependency on the catalog or storage layers.

Output is rendered via `cli/render.py` using Rich (tables for structured data, plain text for simple values). The `--output json` flag on most commands bypasses Rich and prints raw JSON, suitable for scripting.

Configuration (base URL, timeout) is read from environment variables or `cli/config.py` defaults, not from a config file on disk.

---

## Storage Format and Configuration

All data files use **Parquet with Snappy compression**. Snappy is chosen over Zstd or Gzip for its balance of compression ratio and decompression speed — it is the default for interactive analytics workloads.

The warehouse root and catalog path are set in `config.py` and can be overridden with `DATA_ROOT` and `CATALOG_PATH` environment variables. The comment in `config.py` notes that `data_root` is the intended hook for a future S3 backend — swapping the root path is the only change required at the storage layer, since DuckDB's `read_parquet()` supports S3 URLs natively.

The warehouse is organized as `<zone>/<entity>/` with no sub-namespacing beyond zone and entity. This maps directly to the three medallion zones (bronze, silver, gold) and is the level at which all catalog operations are keyed (the `table_id` is `"{zone}.{entity}"`).
