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

Phase 3   Query Engine        DuckDB wired to catalog, partition pruning
Phase 4   Schema Evolution    Versioned schemas, backward compatibility
Phase 5   Governance          Audit log, freshness (vacuum/expiry), quality contracts
Phase 6   Platform API        Clean Python API & CLI wrapping everything
Phase 7   Job Scheduling      Add job scheduling capabilities
Phase 7   UI                  FastAPI backend + React frontend
Phase 8   Benchmarking        Load tests, metrics, final report


## Future Phases

- [ ] Add option to save files to local, S3, or other cloud file storages
- [ ] Add custom LLM applications into the database
- [ ] Add docker and kubernetes to spin up multiple nodes for scalability

