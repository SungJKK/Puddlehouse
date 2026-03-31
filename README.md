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




