# Project Phases

Phase 1   Foundation          Storage, SQLite catalog, DuckDB, config          ✅ Done
  - LakehouseConfig (config.py): singleton config with DATA_ROOT and
    CATALOG_PATH overrideable via env vars; zone path helpers (bronze,
    silver, gold, _metadata)
  - SQLite catalog schema (schema.sql): 11 tables covering catalog_tables,
    catalog_columns, catalog_snapshots, catalog_files, catalog_delete_files,
    catalog_column_stats, catalog_file_column_stats, catalog_views,
    catalog_lineage, catalog_partitions, catalog_audit_log; with indexes
  - CatalogManager (catalog/manager.py): full CRUD API — register_table,
    register_columns, create_snapshot, write_file_column_stats,
    upsert_column_stats, record_delete, register_view,
    refresh_materialized_view, record_lineage, register_partition,
    get_table, get_latest_snapshot, list_tables, get_schema_at_version,
    get_snapshot_files; internal _audit() on every write operation
  - Dataclass models (catalog/models.py): TableMeta, Column, Snapshot,
    CatalogFile, DeleteFile, ColumnStats, FileColumnStats, View, Partition,
    LineageRecord, AuditEntry — all with from_row() deserializers
  - write_parquet() (storage/writer.py): writes DataFrame as Snappy-compressed
    Parquet, supports optional partition columns, reads footer stats without
    loading data (_read_file_stats), computes in-memory table stats
    (_compute_table_stats), and registers everything in the catalog
  - read_parquet() (storage/writer.py): reads all Parquet files for a
    zone/entity with optional PyArrow predicate filters
  - init_catalog.py: bootstraps catalog DB from schema.sql
  - init_lakehouse.py: creates medallion folder structure (bronze/silver/gold)
  - generate_data.py: Faker-based generators for users, events, orders
  - clean_up.py: tears down catalog and warehouse for fresh starts

Phase 2   Table Format        ACID writes, snapshots, time travel, compaction   ✅ Done
  - CatalogManager.commit_write(): all catalog operations (snapshot, columns,
    stats, lineage, partitions) now run in a single SQLite transaction —
    write is fully atomic and all-or-nothing
  - CatalogManager.list_snapshots(): list all snapshots for a table ordered
    by version ascending
  - CatalogManager.get_snapshot_at_version(): point lookup of a snapshot by
    version number
  - CatalogManager.get_table_files_at_version(): returns all files across all
    snapshots up to a given version, implementing cumulative table state
    semantics (matching Iceberg / Delta Lake behaviour)
  - read_parquet_at_version(): time travel read — resolves the exact set of
    files for a given version from the catalog and reads only those
  - compact(): merges all files from the current table state into a single
    Parquet file and commits it as a new snapshot; old snapshots and their
    files remain on disk for time travel

Phase 3   Query Engine        DuckDB wired to catalog, partition pruning        ✅ Done
  - QueryEngine (query/engine.py): wraps a DuckDB in-memory connection; resolves
    the catalog file list for a zone/entity and registers it as a DuckDB view
    named {zone}_{entity} before executing arbitrary SQL
  - Time travel: version= param pins file resolution to a specific snapshot
    version via get_snapshot_at_version + get_table_files_at_version
  - Partition pruning: partition_filters= dict queries catalog_partitions to
    exclude files whose partition values don't match; files with no partition
    records are always included (cannot be pruned)
  - File deduplication: file paths are deduplicated before being passed to
    DuckDB (a file registered in multiple snapshots is read only once)

Phase 4   Schema Evolution    Versioned schemas, backward compatibility           ✅ Done
  - SchemaEvolutionError (catalog/manager.py): typed exception for invalid schema changes
  - CatalogManager.validate_schema_evolution(): checks new schema against the
    current active columns; raises if any column is removed or has its type
    changed; passes silently on first write (no existing schema to compare)
  - write_parquet() enforcement: validate_schema_evolution is called before
    commit_write so any invalid evolution is rejected before data is written
  - compact() is exempt: it re-writes existing data with the same schema and
    calls commit_write directly, bypassing write_parquet validation

Phase 5   Governance          Audit log, freshness (vacuum/expiry), quality contracts  ✅ Done
  - CatalogManager.get_audit_log(): read API for the existing catalog_audit_log
    table; filters by table_id and limit; returns list[AuditEntry] newest-first
  - CatalogManager.vacuum(): deletes Parquet files from snapshots older than
    retain_last_n; removes catalog_files entries; dry_run=True previews without
    deleting; vacuum operations are written to the audit log
  - catalog_quality_contracts table added to schema.sql (created on-demand via
    _ensure_quality_table for existing DBs)
  - CatalogManager.add_quality_contract(): registers not_empty, freshness_days,
    or max_null_fraction checks with JSON params
  - CatalogManager.run_quality_checks(): evaluates all active contracts against
    the latest snapshot and catalog stats; returns [{contract_id, check_type,
    passed, details}] per contract

Phase 6   Platform API        Clean REST API (FastAPI) & CLI (Typer) wrapper   ✅ Done
  Phase 6.1 — REST API (api/)
  - FastAPI app (api/main.py): lifespan context initializes shared CatalogManager
    and QueryEngine via init_shared(); all routers mounted under /api/v1
  - api/deps.py: get_catalog() and get_engine() FastAPI dependency functions
    returning shared instances
  - api/errors.py: exception handlers mapping KeyError → 404, SchemaEvolutionError
    → 422, ValueError → 422, unhandled → 500; all errors use standard
    {"error": {"code", "message", "details"}} shape
  - Tables router: GET /tables (list, filter by zone), GET/DELETE /tables/{zone}/{entity}
  - Snapshots router: GET .../snapshots (list), .../snapshots/latest,
    .../snapshots/{version} — each with embedded file manifest
  - Schema router: GET .../schema (with optional ?version= for time travel),
    POST .../schema/validate (backward-compat check, no writes)
  - Data router: POST .../data (write records, atomic snapshot commit),
    GET .../data (read with limit/offset/version), POST .../compact
  - Partitions router: GET/POST .../partitions
  - Stats router: GET .../stats (table-level aggregates),
    GET .../stats/files (per-file per-column stats)
  - Lineage router: GET .../lineage (upstream/downstream/both),
    POST .../lineage (record a source → target relationship)
  - Governance router: GET .../audit, GET/POST .../quality/contracts,
    POST .../quality/run (exits with all_passed bool),
    POST .../vacuum (dry_run=true default)
  - Query router: POST /query — executes arbitrary SQL via DuckDB; table
    registered as {zone}_{entity} view; supports time travel and partition filters
  - Views router: GET/POST /views, GET /views/{view_id},
    POST /views/{view_id}/refresh (materialized views only)
  - Test suite (tests/api/): TestClient-based; one happy-path + error-path
    test per router group

  Phase 6.2 — CLI (cli/)
  - cli/config.py: load_config() resolves api_url and output format with
    precedence: CLI flag → LH_API_URL/LH_OUTPUT env vars →
    ~/.lh/config.toml → built-in defaults
  - cli/client.py: LakehouseClient wraps httpx; on non-2xx responses parses
    {"error": {"code", "message"}} body and raises typed ApiError
  - cli/render.py: render() dispatches to rich table (default), csv (stdlib),
    or json; render_kv() for single-record detail views; print_success /
    print_error (stderr via dedicated Console); set_quiet() suppresses
    decorative output globally
  - cli/utils.py: parse_target() splits 'zone/entity' argument strings
  - cli/main.py: root lh Typer app; group commands (tables, snapshots, schema,
    data, partitions, stats, lineage, quality, views) via add_typer; top-level
    commands (audit, vacuum, query) registered directly to avoid double-nesting;
    @app.callback sets ctx.obj = Config and calls set_quiet()
  - 12 command modules in cli/commands/:
      tables (list, get, delete with confirmation)
      snapshots (list, latest, get --version)
      schema (get, validate — exits 1 on incompatible schema)
      data (read, write [Parquet only], compact)
      partitions (list, add)
      stats (table, files)
      lineage (get --direction, record)
      audit (top-level, --limit)
      quality (contracts list, contracts add, run — exits 1 on failure)
      vacuum (top-level, dry-run default, --execute to commit)
      query (top-level, --sql or --file, --partition repeatable)
      views (list, get, create --sql/--file, refresh --snapshot-id)
  - Registered as lh entrypoint via pyproject.toml [project.scripts];
    tool.uv.package=true + tool.setuptools.packages.find avoids needing
    a separate build backend

Phase 7   Benchmarking        Load tests, metrics, final report


## Future Phases

- [ ] Add docker and kubernetes to spin up multiple nodes for scalability
- [ ] Add option to save files to local, S3, or other cloud file storages
- [ ] Add user credentials
- [ ] Add frontend web app for user

