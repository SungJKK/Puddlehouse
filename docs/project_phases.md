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

Phase 5   Governance          Audit log, freshness (vacuum/expiry), quality contracts

Phase 6   Platform API        Clean Python API & CLI wrapping everything

Phase 7   UI                  FastAPI backend + React frontend

Phase 8   Benchmarking        Load tests, metrics, final report


## Future Phases

- [ ] Add docker and kubernetes to spin up multiple nodes for scalability
- [ ] Add option to save files to local, S3, or other cloud file storages

