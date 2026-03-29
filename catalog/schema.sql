-- Run once to initialize the catalog database

CREATE TABLE IF NOT EXISTS catalog_tables (
    table_id     TEXT PRIMARY KEY,          -- e.g. "silver.events"
    name         TEXT NOT NULL,             -- human name
    zone         TEXT NOT NULL,             -- bronze / silver / gold
    entity       TEXT NOT NULL,             -- events / users / orders
    location     TEXT NOT NULL,             -- absolute path to folder
    owner        TEXT DEFAULT 'system',
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now')),
    row_count    INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1          -- soft delete
);

CREATE TABLE IF NOT EXISTS catalog_columns (
    column_id          TEXT PRIMARY KEY,    -- uuid
    table_id           TEXT REFERENCES catalog_tables(table_id),
    column_name        TEXT NOT NULL,
    column_type        TEXT NOT NULL,       -- e.g. "int64", "utf8", "float64"
    column_order       INTEGER NOT NULL,    -- zero-based position in schema
    nulls_allowed      INTEGER DEFAULT 1,   -- 1 = nullable, 0 = NOT NULL
    default_value      TEXT,
    added_at_version   INTEGER NOT NULL,    -- snapshot version when this column was added
    dropped_at_version INTEGER             -- snapshot version when dropped; NULL if still active
);

CREATE TABLE IF NOT EXISTS catalog_snapshots (
    snapshot_id  TEXT PRIMARY KEY,          -- uuid
    table_id     TEXT REFERENCES catalog_tables(table_id),
    version      INTEGER NOT NULL,
    row_count    INTEGER,
    byte_size    INTEGER,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalog_files (
    file_id      TEXT PRIMARY KEY,          -- uuid
    snapshot_id  TEXT REFERENCES catalog_snapshots(snapshot_id),
    table_id     TEXT REFERENCES catalog_tables(table_id),  -- denormalized for fast lookup
    file_path    TEXT NOT NULL,
    row_count    INTEGER,
    byte_size    INTEGER
);

CREATE TABLE IF NOT EXISTS catalog_delete_files (
    delete_file_id   TEXT PRIMARY KEY,      -- uuid
    table_id         TEXT REFERENCES catalog_tables(table_id),
    snapshot_id      TEXT REFERENCES catalog_snapshots(snapshot_id),
    file_id          TEXT REFERENCES catalog_files(file_id),
    delete_file_path TEXT NOT NULL,
    delete_count     INTEGER,
    byte_size        INTEGER,
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalog_column_stats (
    table_id    TEXT REFERENCES catalog_tables(table_id),
    column_id   TEXT REFERENCES catalog_columns(column_id),
    null_count  INTEGER DEFAULT 0,
    min_value   TEXT,
    max_value   TEXT,
    updated_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (table_id, column_id)
);

CREATE TABLE IF NOT EXISTS catalog_file_column_stats (
    file_id           TEXT REFERENCES catalog_files(file_id),
    table_id          TEXT REFERENCES catalog_tables(table_id),    -- denormalized
    column_id         TEXT REFERENCES catalog_columns(column_id),
    value_count       INTEGER,
    null_count        INTEGER DEFAULT 0,
    min_value         TEXT,
    max_value         TEXT,
    column_size_bytes INTEGER,
    PRIMARY KEY (file_id, column_id)
);

CREATE TABLE IF NOT EXISTS catalog_views (
    view_id             TEXT PRIMARY KEY,   -- uuid
    view_name           TEXT NOT NULL,
    zone                TEXT NOT NULL,
    view_type           TEXT NOT NULL,      -- "view" or "materialized_view"
    sql                 TEXT NOT NULL,
    owner               TEXT DEFAULT 'system',
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    is_active           INTEGER DEFAULT 1,
    last_refreshed_at   TEXT,
    refresh_snapshot_id TEXT REFERENCES catalog_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS catalog_lineage (
    lineage_id   TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,             -- table_id or "external:..." label
    target_id    TEXT REFERENCES catalog_tables(table_id),
    job_name     TEXT,
    run_id       TEXT,
    rows_read    INTEGER,
    rows_written INTEGER,
    created_at   TEXT DEFAULT (datetime('now'))
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

CREATE TABLE IF NOT EXISTS catalog_audit_log (
    log_id      TEXT PRIMARY KEY,
    operation   TEXT NOT NULL,              -- REGISTER / SNAPSHOT / LINEAGE / DELETE / VIEW
    table_id    TEXT,
    details     TEXT,                       -- JSON blob
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalog_quality_contracts (
    contract_id TEXT PRIMARY KEY,
    table_id    TEXT REFERENCES catalog_tables(table_id),
    check_type  TEXT NOT NULL,              -- "not_empty" / "freshness_days" / "max_null_fraction"
    params      TEXT NOT NULL DEFAULT '{}', -- JSON params for the check
    created_at  TEXT DEFAULT (datetime('now')),
    is_active   INTEGER DEFAULT 1
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_columns_table       ON catalog_columns(table_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_table     ON catalog_snapshots(table_id);
CREATE INDEX IF NOT EXISTS idx_files_snapshot      ON catalog_files(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_files_table         ON catalog_files(table_id);
CREATE INDEX IF NOT EXISTS idx_delete_files_file   ON catalog_delete_files(file_id);
CREATE INDEX IF NOT EXISTS idx_delete_files_snap   ON catalog_delete_files(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_file_col_stats_file ON catalog_file_column_stats(file_id);
CREATE INDEX IF NOT EXISTS idx_lineage_target      ON catalog_lineage(target_id);
CREATE INDEX IF NOT EXISTS idx_partitions_table    ON catalog_partitions(table_id);
