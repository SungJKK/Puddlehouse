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
$ python -m tests.lakehouse.test_smoke
```


---

## Known Limitations

### `lh data write` — Parquet input only

`lh data write` currently accepts only `.parquet` files. CSV and JSON input files are not yet supported — the CLI would need to parse them client-side and convert to records before POSTing to the API.

Planned: add CSV and JSON support to `lh data write` once the core CLI is stable.

---

# TODO


## Project Status

Refer to file `docs/project_phases.md`

---

## Phase 6.2: CLI Wrapper

The CLI (`lh`) is a thin Typer-based client over the REST API. Every command translates to one or more `httpx` calls. No direct catalog or storage access from the CLI.

### Step 1 — Scaffold the CLI package

- [ ] Add `typer`, `httpx`, and `rich` to `pyproject.toml` dependencies
- [ ] Create the `cli/` package with the following layout:
  ```
  cli/
  ├── __init__.py
  ├── main.py          # root `lh` Typer app; registers all command groups
  ├── config.py        # resolves api_url from flag → LH_API_URL → ~/.lh/config.toml → default
  ├── client.py        # thin httpx wrapper; raises on non-2xx with parsed error body
  ├── render.py        # table / json / csv output formatters using rich
  └── commands/
      ├── __init__.py
      ├── tables.py
      ├── snapshots.py
      ├── schema.py
      ├── data.py
      ├── partitions.py
      ├── stats.py
      ├── lineage.py
      ├── audit.py
      ├── quality.py
      ├── vacuum.py
      ├── query.py
      └── views.py
  ```
- [ ] Register `lh` as a script entrypoint in `pyproject.toml` pointing at `cli.main:app`

### Step 2 — Config, client, and render layer

- [ ] `config.py`: load `api_url` and `output` format with precedence: CLI flag → `LH_API_URL` env var → `~/.lh/config.toml` → built-in default (`http://localhost:8000/api/v1`)
- [ ] `client.py`: wrap `httpx` with a base URL; on non-2xx responses parse the `{"error": {"code", "message"}}` body and raise a typed exception that commands can catch and print cleanly
- [ ] `render.py`: implement three formatters — `table` (rich), `json` (pretty-printed), `csv` (stdlib) — that accept a list of column headers and rows and write to stdout

### Step 3 — Implement command groups (one module each)

Implement in this order (simpler → more complex):

- [ ] `tables.py` — `list`, `get`, `delete` (with interactive confirmation)
- [ ] `snapshots.py` — `list`, `latest`, `get`
- [ ] `schema.py` — `get`, `validate` (reads schema JSON from `--file`; exits 1 on failure)
- [ ] `data.py` — `read`, `write` (Parquet only via PyArrow), `compact`
- [ ] `partitions.py` — `list`, `add`
- [ ] `stats.py` — `table`, `files`
- [ ] `lineage.py` — `get`, `record`
- [ ] `audit.py` — `audit` (top-level command, not a subgroup)
- [ ] `quality.py` — `contracts list`, `contracts add`, `run` (exits 1 if any check fails)
- [ ] `vacuum.py` — top-level command; dry-run by default, `--execute` to commit
- [ ] `query.py` — top-level command; accepts `--sql` or `--file`; exits 1 on query error
- [ ] `views.py` — `list`, `get`, `create` (SQL from `--sql` or `--file`), `refresh`

### Step 4 — Wire up `main.py`

- [ ] Create the root `lh` Typer app in `main.py`
- [ ] Add global options (`--api-url`, `--output`/`-o`, `--quiet`/`-q`) via a shared callback
- [ ] Register all command groups and top-level commands from `commands/`

### Step 5 — Smoke test

- [ ] Start the API server (`uvicorn api.main:app`) and run each command group manually against live data to verify end-to-end output (table, json, and csv formats)

