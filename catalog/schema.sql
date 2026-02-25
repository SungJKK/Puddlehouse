-- Run once to initialize the catalog database

CREATE TABLE IF NOT EXISTS catalog_tables (
    table_id     TEXT PRIMARY KEY,          -- e.g. "silver.events"
    name         TEXT NOT NULL,             -- human name
    zone         TEXT NOT NULL,             -- bronze / silver / gold
    entity       TEXT NOT NULL,             -- events / users / orders
    location     TEXT NOT NULL,             -- absolute path to folder
    schema_json  TEXT,                      -- JSON: [{name, type, nullable}]
    owner        TEXT DEFAULT 'system',
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now')),
    row_count    INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1          -- soft delete
);

CREATE TABLE IF NOT EXISTS catalog_snapshots (
    snapshot_id   TEXT PRIMARY KEY,         -- uuid
    table_id      TEXT REFERENCES catalog_tables(table_id),
    version       INTEGER NOT NULL,
    manifest_path TEXT NOT NULL,            -- path to JSON file listing parquet files
    row_count     INTEGER,
    byte_size     INTEGER,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalog_lineage (
    lineage_id  TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,              -- table_id or "external:kafka" etc.
    target_id   TEXT REFERENCES catalog_tables(table_id),
    job_name    TEXT,
    run_id      TEXT,
    rows_read   INTEGER,
    rows_written INTEGER,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalog_partitions (
    partition_id  TEXT PRIMARY KEY,
    table_id      TEXT REFERENCES catalog_tables(table_id),
    partition_key TEXT NOT NULL,            -- e.g. "date"
    partition_val TEXT NOT NULL,            -- e.g. "2025-01-01"
    file_path     TEXT NOT NULL,
    row_count     INTEGER,
    created_at    TEXT DEFAULT (datetime('now'))
);

-- Audit log: every catalog write operation is recorded
CREATE TABLE IF NOT EXISTS catalog_audit_log (
    log_id      TEXT PRIMARY KEY,
    operation   TEXT NOT NULL,              -- INSERT / UPDATE / SNAPSHOT / LINEAGE
    table_id    TEXT,
    details     TEXT,                       -- JSON blob
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_snapshots_table  ON catalog_snapshots(table_id);
CREATE INDEX IF NOT EXISTS idx_lineage_target   ON catalog_lineage(target_id);
CREATE INDEX IF NOT EXISTS idx_partitions_table ON catalog_partitions(table_id);
