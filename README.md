# Puddlehouse

Puddlehouse, a local data lakehouse platform built from scratch — Parquet files, a lightweight SQLite metadata catalog, and DuckDB as the query engine. No cloud account or managed service required.


## Project Structure

```
Puddlehouse/
├── config.py                       # Paths and environment config
├── pyproject.toml
├── uv.lock
│
├── catalog/                        # Metadata catalog (SQLite-backed)
├── storage/                        # Write layer (Parquet writer)
├── query/                          # Query layer (DuckDB engine)
├── api/                            # FastAPI server
│   └── routers/                    # One router per domain
├── cli/                            # lh CLI (Typer)
│   └── commands/                   # One module per command group
├── scripts/                        # Dev utilities (init, seed, teardown)
├── docs/                           # Architecture and design docs
├── tests/
│   ├── lakehouse/                  # Core lakehouse unit/integration tests
│   └── api/                        # API integration tests
└── warehouse/                      # Parquet data files (gitignored except .gitkeep)
    ├── _metadata/
    ├── bronze/
    ├── silver/
    └── gold/
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

## Tech Stack

| Layer | Tool | Role |
|---|---|---|
| Storage Format | Parquet | Columnar file format for all lakehouse data (via PyArrow) |
| Query Engine | DuckDB | Fast local OLAP queries directly on Parquet files |
| Metadata Catalog | SQLite | Hand-rolled local catalog (tracks tables, columns, snapshots, files, delete files, column stats, views, lineage, partitions, and audit log) |


## Lakehouse platform architecture

For the architectural design choices of the lakehouse platform and its functionalities, refer to
file `docs/puddlehouse_design.md`


## Known Limitations

### `lh data write` — Parquet input only

`lh data write` currently accepts only `.parquet` files. CSV and JSON input files are not yet supported — the CLI would need to parse them client-side and convert to records before POSTing to the API.

Planned: add CSV and JSON support to `lh data write` once the core CLI is stable.

---

# Project Status

Refer to `docs/project_phases.md` for an overview of project phases.

## TODO

### Bugs
- [x] **`row_count` in snapshots and tables is per-batch, not cumulative** — `commit_write` stores `len(df)` (the current write batch) as the snapshot and table row count. `tables_design.md` specifies snapshot `row_count` as "total live rows across all data files in this snapshot", which requires summing all prior snapshots. A table with three writes of 100 rows each will show `row_count=100` everywhere instead of 300.
- [x] **Partition `row_count` is always the total DataFrame count, not per-partition** — In `storage/writer.py`, each partition entry is registered with `row_count=len(df)` (the full write batch size). Every partition file gets the same inflated number regardless of how many rows actually landed in that partition.
- [x] **Delete files are tracked in the catalog but never applied at query time** — `catalog_delete_files` is populated correctly via `record_delete`, but `query/engine.py` never joins against it when resolving files. Logical deletes are silently ignored on read; deleted rows are still returned by queries.

### Documentation inaccuracies
- [x] **`project_phases.md` says schema validation fires "before data is written" — it doesn't** — Phase 4 states "validate_schema_evolution is called before `commit_write` so any invalid evolution is rejected before data is written." In reality, the Parquet file is written to disk first (Step 1 in `write_parquet`), and validation only runs at Step 3. If validation fails, the file is already orphaned on disk. `puddlehouse_design.md` describes this correctly; the phases doc contradicts it.
- [ ] **`cli_design.md` documents CSV/JSON write support that isn't implemented** — The `--file` flag is described as accepting "a local Parquet, CSV, or JSON file", but `cli/commands/data.py` rejects anything that isn't `.parquet` with an explicit error. The README Known Limitations section acknowledges this gap, but the CLI design doc does not.
- [ ] **`puddlehouse_design.md` audit log table is missing the `VACUUM` operation** — The documented operations are `REGISTER`, `DEREGISTER`, `SNAPSHOT`, `DELETE`, `LINEAGE`, `VIEW`. But `catalog/manager.py` also writes a `VACUUM` audit entry on each file deletion during vacuum. This operation is never listed in the docs.
- [ ] **`api_design.md` schema validate errors show per-column granularity that the code doesn't produce** — The design shows separate error strings per removed/changed column. The actual `validate_schema_evolution` raises a single combined `SchemaEvolutionError` (e.g. `"Cannot remove columns from bronze.users: ['user_id', 'age']"`), and the router wraps it as `[str(e)]` — one string in the list, not one entry per column.

### Minor / Cosmetic
- [ ] **CLI quality contracts `params` column display doesn't match the design doc** — `cli_design.md` shows params rendered as `min_rows=1` (key=value style). The actual `cli/commands/quality.py` renders `json.dumps(params)`, producing `{"min_rows": 1}` instead.



