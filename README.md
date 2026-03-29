# Local Data Lakehouse

A local lakehouse platform built from scratch — Parquet files, a lightweight SQLite metadata catalog, and DuckDB as the query engine. No cloud account or managed service required.

## Stack

| Layer | Tool | Role |
|---|---|---|
| Storage Format | Parquet | Columnar file format for all lakehouse data (via PyArrow) |
| Query Engine | DuckDB | Fast local OLAP queries directly on Parquet files |
| Metadata Catalog | SQLite | Hand-rolled local catalog (tracks tables, columns, snapshots, files, delete files, column stats, views, lineage, partitions, and audit log) |

## Architecture

```
   ╭──────────────────╮                          ╭───────────────────────╮
   │    Writer API    │                          │    DuckDB             │
   │    (PyArrow)     │                          │    Query Engine       │
   ╰────────┬─────────╯                          ╰──────────┬────────────╯
            │                                               │
            │  ① write Parquet file                         │  ① resolve current
            │     to warehouse/                             │     (or past) snapshot
            │                                               │
            │  ② commit new snapshot             ② fetch    │
            │     to catalog                  file manifest │
            │     (atomic, all-or-nothing)                  │
            │                                               │
            ▼                                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          SQLite Catalog                               │
│                                                                       │
│  ┌──────────────────────┐   ┌──────────────────────────────────────┐ │
│  │  catalog_tables      │──▶│  catalog_snapshots                   │ │
│  │                      │   │                                      │ │
│  │  · table_id          │   │  · snapshot_id                       │ │
│  │  · name, zone,       │   │  · version  (monotonic integer)      │ │
│  │    entity, location  │   │  · row_count, byte_size              │ │
│  │  · owner, row_count  │   └──────────────┬───────────────────────┘ │
│  │  · is_active         │                  │                         │
│  └──────────┬───────────┘                  ▼                         │
│             │                  ┌──────────────────────────────────┐  │
│             │                  │  catalog_files                   │  │
│             │                  │  · file_path, row_count,         │  │
│             ▼                  │    byte_size                     │  │
│  ┌──────────────────────┐      └──────────────┬───────────────────┘  │
│  │  catalog_columns     │                     │                      │
│  │                      │                     ▼                      │
│  │  · column_name/type  │      ┌──────────────────────────────────┐  │
│  │  · column_order      │      │  catalog_delete_files            │  │
│  │  · nulls_allowed     │      │  · logical deletes per file      │  │
│  │  · added_at_version  │      └──────────────────────────────────┘  │
│  │  · dropped_at_version│                                            │
│  └──────────┬───────────┘      ┌──────────────────────────────────┐  │
│             │                  │  catalog_views                   │  │
│             ▼                  │  · view / materialized_view      │  │
│  ┌──────────────────────┐      │  · sql, refresh_snapshot_id      │  │
│  │  catalog_column_stats│      └──────────────────────────────────┘  │
│  │  aggregate min/max/  │                                            │
│  │  null per column     │      ┌──────────────────────────────────┐  │
│  └──────────────────────┘      │  catalog_lineage                 │  │
│                                │  · source_id → target_id         │  │
│  ┌──────────────────────┐      │  · job_name, run_id, row counts  │  │
│  │  catalog_file_column │      └──────────────────────────────────┘  │
│  │  _stats              │                                            │
│  │  per-file min/max/   │      ┌──────────────────────────────────┐  │
│  │  null/size per column│      │  catalog_partitions              │  │
│  └──────────────────────┘      │  · partition_key / _val / path   │  │
│                                └──────────────────────────────────┘  │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  catalog_audit_log  — REGISTER / SNAPSHOT / DELETE / LINEAGE /  │ │
│  │                       VIEW operations with JSON details          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  · time travel    — query any snapshot by monotonic version number   │
│  · schema evol.   — columns tracked with added/dropped version range │
│  · logical deletes — delete files point at specific data files       │
│  · partition pruning — file manifest filtered before data is read    │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    │  ③ read Parquet files
                                    ▼
             ┌──────────────────────────────────────────────────┐
             │                  warehouse/                       │
             │                                                   │
             │   <namespace>/                                    │
             │     <table>/                                      │
             │       <partition_key=value>/                      │
             │         <write-uuid>.parquet                      │
             │                                                   │
             │   Files are immutable and append-only.            │
             │   Deletes and updates are logical — tracked       │
             │   in snapshots, never mutating existing files.    │
             └──────────────────────────────────────────────────┘
```

## Project Structure

```
lakehouse/
├── config.py                       # Paths and environment config
├── pyproject.toml
├── uv.lock
│
├── catalog/                        # Metadata catalog (SQLite-backed)
│   ├── __init__.py
│   ├── manager.py                  # Catalog API (tables, columns, snapshots, files, stats, views, lineage, partitions)
│   ├── models.py                   # Dataclass models for catalog entities
│   └── schema.sql                  # SQLite DDL for catalog tables
│
├── storage/                        # Write layer
│   ├── __init__.py
│   └── writer.py                   # Parquet writer (append, overwrite)
│
├── scripts/
│   ├── init_catalog.py             # Bootstrap catalog schema
│   ├── init_lakehouse.py           # Create namespaces and register tables
│   ├── generate_data.py            # Generate sample Parquet data
│   └── clean_up.py                 # Tear down catalog and warehouse files
│
├── tests/
│   └── smoke_test.py
│
└── warehouse/                      # Parquet data files (gitignored except .gitkeep)
    ├── _metadata/                  # Per-table Iceberg-style metadata
    │   ├── events/
    │   ├── orders/
    │   └── users/
    ├── bronze/                     # Raw ingested data
    │   ├── events/
    │   ├── orders/
    │   └── users/
    ├── silver/                     # Cleaned and conformed data
    │   ├── events/
    │   ├── orders/
    │   └── users/
    └── gold/                       # Aggregated, query-ready data
        ├── events/
        ├── orders/
        └── users/
```

---

## Getting Started

```bash
uv sync
source .venv/bin/activate
uv run python scripts/init_catalog.py
```

### Running tools

```
$ python -m scripts.[init_catalog, init_lakehouse, ...]
$ python -m tests.smoke_test
```


---
# TODO

### Phase 4 — Schema Evolution

- [x] **P4-1** — `SchemaEvolutionError` + `CatalogManager.validate_schema_evolution()` — raises if an existing column is removed or has its type changed; adding new columns is allowed
- [x] **P4-2** — Enforce in `write_parquet()` — call `validate_schema_evolution` before `commit_write`; `compact()` bypasses validation (schema never changes during compaction)
- [x] **P4-3** — Tests for schema evolution validation via the writer

# Project Status
Refer to file `docs/project_phases.md`

