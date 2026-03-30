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

### Phase 6 — REST API

The REST API wraps all catalog, storage, and query engine functionality over HTTP. Built with FastAPI. Base URL: `http://localhost:8000/api/v1`. Full endpoint spec in `docs/api_design.md`.

**P6-1 — Setup and scaffolding**
- [ ] Add `fastapi` and `uvicorn[standard]` to `pyproject.toml` dependencies
- [ ] Create `api/` package with `__init__.py`
- [ ] Create `api/main.py` — instantiate the `FastAPI` app, register all routers under `/api/v1`, add a startup event that initializes a shared `CatalogManager` and `QueryEngine`
- [ ] Create `api/deps.py` — `get_catalog()` and `get_engine()` dependency functions that return the shared instances via `Depends`
- [ ] Create `api/errors.py` — exception handlers that map `KeyError` → 404, `SchemaEvolutionError` → 422, `ValueError` → 422, and unhandled exceptions → 500, all using the standard `{"error": {"code": ..., "message": ..., "details": {}}}` shape from the spec

**P6-2 — Tables router** (`api/routers/tables.py`)
- [ ] `GET /tables` — call `catalog.list_tables()`; accept optional `?zone=` query param to filter; return `{"tables": [...]}` with `table_id`, `zone`, `entity`, `location`, `owner`, `row_count`, `created_at`, `updated_at`
- [ ] `GET /tables/{zone}/{entity}` — call `catalog.get_table(f"{zone}.{entity}")`; raise 404 if not found; include `latest_version` from `catalog.get_latest_snapshot()`
- [ ] `DELETE /tables/{zone}/{entity}` — mark the table inactive in the catalog (set `is_active = 0`); return 204; raise 404 if not found

**P6-3 — Snapshots router** (`api/routers/snapshots.py`)
- [ ] `GET /tables/{zone}/{entity}/snapshots` — call `catalog.list_snapshots(table_id)`; return `{"table_id": ..., "snapshots": [...]}`
- [ ] `GET /tables/{zone}/{entity}/snapshots/latest` — call `catalog.get_latest_snapshot(table_id)` + `catalog.get_snapshot_files(snapshot_id)`; return snapshot with embedded `files` list; raise 404 if no snapshot exists
- [ ] `GET /tables/{zone}/{entity}/snapshots/{version}` — call `catalog.get_snapshot_at_version(table_id, version)` + `catalog.get_snapshot_files(snapshot_id)`; same response shape as `/latest`; raise 404 if version not found

**P6-4 — Schema router** (`api/routers/schema.py`)
- [ ] `GET /tables/{zone}/{entity}/schema` — accept optional `?version=` param; call `catalog.get_schema_at_version(table_id, version)` (or latest version if omitted); return `{"table_id": ..., "version": ..., "columns": [...]}`
- [ ] `POST /tables/{zone}/{entity}/schema/validate` — accept `{"schema": [{"name": ..., "type": ...}, ...]}` body; call `catalog.validate_schema_evolution(table_id, proposed_columns)` inside a try/except; return `{"valid": true, "added_columns": [...], "message": "..."}` on success or `{"valid": false, "errors": [...]}` with 422 on failure; do not write anything

**P6-5 — Data router** (`api/routers/data.py`)
- [ ] `POST /tables/{zone}/{entity}/data` — accept body with `records`, optional `partition_cols`, `job_name`, `run_id`, `source_id`; convert `records` list-of-dicts to a PyArrow Table; call `write_parquet()`; return 201 with `snapshot_id`, `version`, `files_written`, `row_count`, `byte_size`; return 422 on `SchemaEvolutionError`
- [ ] `GET /tables/{zone}/{entity}/data` — accept optional `?version=`, `?limit=` (default 1000, max 10000), `?offset=`; call `read_parquet_at_version()` if version given else `read_parquet()`; slice with limit/offset; return `{"table_id": ..., "version": ..., "row_count": ..., "columns": [...], "rows": [...]}`
- [ ] `POST /tables/{zone}/{entity}/compact` — call `compact(zone, entity)`; return `{"snapshot_id": ..., "version": ..., "compacted_file": ..., "files_merged": ..., "row_count": ...}`

**P6-6 — Partitions router** (`api/routers/partitions.py`)
- [ ] `GET /tables/{zone}/{entity}/partitions` — query `catalog_partitions` for the table; return `{"table_id": ..., "partitions": [...]}`
- [ ] `POST /tables/{zone}/{entity}/partitions` — accept `{"key": ..., "value": ..., "file_path": ..., "row_count": ...}`; call `catalog.register_partition()`; return 201 with `{"partition_id": ...}`

**P6-7 — Stats router** (`api/routers/stats.py`)
- [ ] `GET /tables/{zone}/{entity}/stats` — query `catalog_column_stats` for the table's columns; return `{"table_id": ..., "column_stats": [...]}`
- [ ] `GET /tables/{zone}/{entity}/stats/files` — query `catalog_file_column_stats` joined to `catalog_files`; group by file; return `{"table_id": ..., "file_stats": [{"file_id": ..., "file_path": ..., "column_stats": [...]}]}`

**P6-8 — Lineage router** (`api/routers/lineage.py`)
- [ ] `GET /tables/{zone}/{entity}/lineage` — accept optional `?direction=` (`upstream`, `downstream`, `both`); query `catalog_lineage` where `target_id = table_id` (upstream) and/or `source_id = table_id` (downstream); return `{"table_id": ..., "upstream": [...], "downstream": [...]}`
- [ ] `POST /tables/{zone}/{entity}/lineage` — accept `{"source_id": ..., "job_name": ..., "run_id": ..., "rows_read": ..., "rows_written": ...}`; call `catalog.record_lineage()`; return 201 with `{"lineage_id": ...}`

**P6-9 — Governance router** (`api/routers/governance.py`)
- [ ] `GET /tables/{zone}/{entity}/audit` — accept optional `?limit=` (default 100); call `catalog.get_audit_log(table_id, limit)`; return `{"table_id": ..., "entries": [...]}`
- [ ] `GET /tables/{zone}/{entity}/quality/contracts` — query `catalog_quality_contracts` for active contracts; return `{"table_id": ..., "contracts": [...]}`
- [ ] `POST /tables/{zone}/{entity}/quality/contracts` — accept `{"check_type": ..., "params": {...}}`; call `catalog.add_quality_contract()`; return 201 with `{"contract_id": ...}`
- [ ] `POST /tables/{zone}/{entity}/quality/run` — call `catalog.run_quality_checks(table_id)`; return `{"table_id": ..., "all_passed": bool, "results": [...]}`
- [ ] `POST /tables/{zone}/{entity}/vacuum` — accept `{"retain_last_n": int, "dry_run": bool}` (defaults: `retain_last_n=1`, `dry_run=true`); call `catalog.vacuum()`; return `{"table_id": ..., "dry_run": bool, "snapshots_removed": ..., "files_removed": ..., "paths": [...]}`

**P6-10 — Query router** (`api/routers/query.py`)
- [ ] `POST /query` — accept `{"sql": ..., "context": {"zone": ..., "entity": ..., "version": ..., "partition_filters": {...}}}`; instantiate (or reuse) `QueryEngine`; call `engine.query(sql, zone, entity, version, partition_filters)`; serialize the DuckDB result to `{"columns": [...], "rows": [[...]], "row_count": ..., "version_used": ...}`; return 400 on SQL errors, 404 if table not found

**P6-11 — Views router** (`api/routers/views.py`)
- [ ] `GET /views` — accept optional `?zone=` and `?type=` (`view` or `materialized_view`); query `catalog_views`; return `{"views": [...]}`
- [ ] `POST /views` — accept `{"name": ..., "zone": ..., "view_type": ..., "sql": ..., "owner": ...}`; call `catalog.register_view()`; return 201 with `{"view_id": ...}`
- [ ] `GET /views/{view_id}` — look up view by `view_id`; return full view record including `refresh_snapshot_id` and `last_refreshed_at`; raise 404 if not found
- [ ] `POST /views/{view_id}/refresh` — accept `{"snapshot_id": ...}`; call `catalog.refresh_materialized_view(view_id, snapshot_id)`; return 422 if the view is a plain `view` (not materialized); return `{"view_id": ..., "refresh_snapshot_id": ..., "last_refreshed_at": ...}`

**P6-12 — Tests** (`tests/test_api.py`)
- [ ] Use FastAPI's `TestClient` (from `starlette.testclient`); patch the catalog and query engine with real in-memory instances populated from `generate_data.py` fixtures
- [ ] One happy-path test per router group (tables, snapshots, schema, data write+read, compact, partitions, stats, lineage, audit, quality contracts + run, vacuum, query, views)
- [ ] One error-path test per meaningful error case: 404 for unknown table/snapshot/view, 422 for schema evolution violation, 422 for refreshing a non-materialized view


## Project Status

Refer to file `docs/project_phases.md`

