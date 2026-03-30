# Lakehouse REST API Design

**Base URL**: `http://localhost:8000/api/v1`

All responses return JSON. All timestamps are ISO 8601 UTC. HTTP status codes follow standard conventions (200 OK, 201 Created, 400 Bad Request, 404 Not Found, 409 Conflict, 422 Unprocessable Entity, 500 Internal Server Error).

---

## Resource Hierarchy

```
/tables
  /{zone}/{entity}
    /snapshots
      /latest
      /{version}
    /schema
    /data
    /partitions
    /stats
    /lineage
    /audit
    /quality
      /contracts
      /run
    /vacuum
    /compact
/query
/views
  /{view_id}
    /refresh
```

Tables are uniquely identified by `{zone}/{entity}` (e.g., `bronze/users`), which maps to the internal `table_id` of `bronze.users`. Zones are `bronze`, `silver`, or `gold`.

---

## 1. Tables

Table discovery and registration.

### `GET /tables`
List all registered tables.

**Query parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `zone` | string | Filter by zone: `bronze`, `silver`, `gold` |

**Response `200`**:
```json
{
  "tables": [
    {
      "table_id": "bronze.users",
      "zone": "bronze",
      "entity": "users",
      "location": "warehouse/bronze/users",
      "owner": "default",
      "row_count": 10000,
      "created_at": "2026-03-01T10:00:00Z",
      "updated_at": "2026-03-29T12:00:00Z"
    }
  ]
}
```

---

### `GET /tables/{zone}/{entity}`
Get metadata for a specific table.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "zone": "bronze",
  "entity": "users",
  "location": "warehouse/bronze/users",
  "owner": "default",
  "row_count": 10000,
  "latest_version": 5,
  "created_at": "2026-03-01T10:00:00Z",
  "updated_at": "2026-03-29T12:00:00Z"
}
```

**Response `404`**: Table does not exist.

---

### `DELETE /tables/{zone}/{entity}`
Deregister a table from the catalog (does not delete Parquet files).

**Response `204`**: Table deregistered.

**Response `404`**: Table does not exist.

---

## 2. Snapshots

Each write creates an immutable snapshot. Snapshots are the foundation of time travel.

### `GET /tables/{zone}/{entity}/snapshots`
List all snapshots for a table, ordered by version ascending.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "snapshots": [
    {
      "snapshot_id": "snap_abc123",
      "version": 1,
      "row_count": 1000,
      "byte_size": 204800,
      "created_at": "2026-03-01T10:00:00Z"
    },
    {
      "snapshot_id": "snap_def456",
      "version": 2,
      "row_count": 2000,
      "byte_size": 409600,
      "created_at": "2026-03-05T14:30:00Z"
    }
  ]
}
```

---

### `GET /tables/{zone}/{entity}/snapshots/latest`
Get the most recent snapshot.

**Response `200`**:
```json
{
  "snapshot_id": "snap_def456",
  "version": 2,
  "row_count": 2000,
  "byte_size": 409600,
  "created_at": "2026-03-05T14:30:00Z",
  "files": [
    {
      "file_id": "file_xyz789",
      "path": "warehouse/bronze/users/part-0.parquet",
      "row_count": 2000,
      "byte_size": 409600
    }
  ]
}
```

**Response `404`**: Table has no snapshots.

---

### `GET /tables/{zone}/{entity}/snapshots/{version}`
Get a specific snapshot by version number.

**Response `200`**: Same shape as `/snapshots/latest`.

**Response `404`**: Version does not exist.

---

## 3. Schema

Track and inspect column schemas across versions.

### `GET /tables/{zone}/{entity}/schema`
Get the current (latest) schema.

**Query parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `version` | integer | Return schema as it existed at this snapshot version |

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "version": 5,
  "columns": [
    {
      "column_id": "col_001",
      "name": "user_id",
      "type": "string",
      "position": 0,
      "added_version": 1,
      "dropped_version": null
    },
    {
      "column_id": "col_002",
      "name": "age",
      "type": "int64",
      "position": 1,
      "added_version": 1,
      "dropped_version": null
    }
  ]
}
```

---

### `POST /tables/{zone}/{entity}/schema/validate`
Validate whether a proposed schema is backward-compatible with the current schema. Does not modify anything.

**Request body**:
```json
{
  "schema": [
    {"name": "user_id", "type": "string"},
    {"name": "age", "type": "int64"},
    {"name": "email", "type": "string"}
  ]
}
```

**Response `200`** (compatible):
```json
{
  "valid": true,
  "added_columns": ["email"],
  "message": "Schema is backward-compatible."
}
```

**Response `422`** (incompatible):
```json
{
  "valid": false,
  "errors": [
    "Column 'age' type changed from int64 to string — not allowed.",
    "Column 'user_id' was removed — not allowed."
  ]
}
```

---

## 4. Data

Read and write Parquet data. The write endpoint is the primary ingestion path; it atomically commits the snapshot, schema, stats, lineage, and partitions in one transaction.

### `POST /tables/{zone}/{entity}/data`
Write a batch of records to the table. Atomically creates a new snapshot.

**Request body**:
```json
{
  "records": [
    {"user_id": "u001", "age": 30},
    {"user_id": "u002", "age": 25}
  ],
  "partition_cols": ["date"],
  "job_name": "etl_job",
  "run_id": "run_20260329_001",
  "source_id": "external:api"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `records` | Yes | Array of row objects |
| `partition_cols` | No | Column names to partition by |
| `job_name` | No | Label for lineage tracking (default: `"api"`) |
| `run_id` | No | Idempotency/tracking key for the job run |
| `source_id` | No | Source table_id or `"external:<label>"` (default: `"external:api"`) |

**Response `201`**:
```json
{
  "snapshot_id": "snap_ghi789",
  "version": 3,
  "files_written": 1,
  "row_count": 2,
  "byte_size": 1024
}
```

**Response `422`**: Schema evolution violation (e.g., column removed or type changed).

---

### `GET /tables/{zone}/{entity}/data`
Read data from the table.

**Query parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `version` | integer | Time travel: read at this snapshot version |
| `limit` | integer | Max rows to return (default: 1000, max: 10000) |
| `offset` | integer | Row offset for pagination (default: 0) |

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "version": 3,
  "row_count": 2,
  "columns": ["user_id", "age"],
  "rows": [
    ["u001", 30],
    ["u002", 25]
  ]
}
```

> Note: For large datasets, prefer `POST /query` with SQL and explicit filters.

---

### `POST /tables/{zone}/{entity}/compact`
Merge all files from the latest snapshot into a single Parquet file. Creates a new snapshot; old snapshots remain intact for time travel.

**Response `200`**:
```json
{
  "snapshot_id": "snap_jkl012",
  "version": 4,
  "compacted_file": "warehouse/bronze/users/compacted-v4.parquet",
  "files_merged": 5,
  "row_count": 10000
}
```

---

## 5. Partitions

Partition metadata enables file-level pruning at query time.

### `GET /tables/{zone}/{entity}/partitions`
List all registered partitions for the table.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "partitions": [
    {
      "partition_id": "part_001",
      "key": "date",
      "value": "2026-01-01",
      "file_path": "warehouse/bronze/users/date=2026-01-01/part-0.parquet",
      "row_count": 5000
    }
  ]
}
```

---

### `POST /tables/{zone}/{entity}/partitions`
Register a partition entry for a specific file.

**Request body**:
```json
{
  "key": "date",
  "value": "2026-01-01",
  "file_path": "warehouse/bronze/users/date=2026-01-01/part-0.parquet",
  "row_count": 5000
}
```

**Response `201`**:
```json
{
  "partition_id": "part_001"
}
```

---

## 6. Statistics

Column-level statistics for query optimization and quality checks.

### `GET /tables/{zone}/{entity}/stats`
Get aggregate table-level column statistics.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "column_stats": [
    {
      "column_id": "col_001",
      "name": "user_id",
      "null_count": 0,
      "min_value": "u001",
      "max_value": "u999"
    },
    {
      "column_id": "col_002",
      "name": "age",
      "null_count": 12,
      "min_value": "18",
      "max_value": "85"
    }
  ]
}
```

---

### `GET /tables/{zone}/{entity}/stats/files`
Get per-file, per-column statistics.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "file_stats": [
    {
      "file_id": "file_xyz789",
      "file_path": "warehouse/bronze/users/part-0.parquet",
      "column_stats": [
        {
          "column_id": "col_001",
          "name": "user_id",
          "null_count": 0,
          "min_value": "u001",
          "max_value": "u500",
          "byte_size": 8192
        }
      ]
    }
  ]
}
```

---

## 7. Lineage

Track the data derivation graph across tables.

### `GET /tables/{zone}/{entity}/lineage`
Get lineage records where this table is either the source or the target.

**Query parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `direction` | string | `upstream` (this table as target), `downstream` (this table as source), `both` (default) |

**Response `200`**:
```json
{
  "table_id": "silver.events",
  "upstream": [
    {
      "lineage_id": "lin_001",
      "source_id": "bronze.raw_events",
      "job_name": "clean_events_job",
      "run_id": "run_20260329_001",
      "rows_read": 10000,
      "rows_written": 9500,
      "recorded_at": "2026-03-29T10:00:00Z"
    }
  ],
  "downstream": []
}
```

---

### `POST /tables/{zone}/{entity}/lineage`
Record a lineage relationship from a source table to this table.

**Request body**:
```json
{
  "source_id": "bronze.raw_events",
  "job_name": "clean_events_job",
  "run_id": "run_20260329_001",
  "rows_read": 10000,
  "rows_written": 9500
}
```

**Response `201`**:
```json
{
  "lineage_id": "lin_001"
}
```

---

## 8. Governance

Audit, quality, and retention controls grouped under a shared resource prefix.

### `GET /tables/{zone}/{entity}/audit`
Retrieve the audit log for a table.

**Query parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max entries to return (default: 100) |

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "entries": [
    {
      "entry_id": "aud_001",
      "operation": "SNAPSHOT",
      "details": {"version": 3, "row_count": 2, "byte_size": 1024},
      "recorded_at": "2026-03-29T12:00:00Z"
    },
    {
      "entry_id": "aud_002",
      "operation": "REGISTER",
      "details": {"zone": "bronze", "entity": "users"},
      "recorded_at": "2026-03-01T10:00:00Z"
    }
  ]
}
```

---

### `GET /tables/{zone}/{entity}/quality/contracts`
List all active quality contracts for a table.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "contracts": [
    {
      "contract_id": "qc_001",
      "check_type": "not_empty",
      "params": {"min_rows": 1},
      "is_active": true
    },
    {
      "contract_id": "qc_002",
      "check_type": "max_null_fraction",
      "params": {"column": "email", "max_fraction": 0.05},
      "is_active": true
    }
  ]
}
```

---

### `POST /tables/{zone}/{entity}/quality/contracts`
Add a quality contract to a table.

**Request body**:
```json
{
  "check_type": "max_null_fraction",
  "params": {
    "column": "email",
    "max_fraction": 0.05
  }
}
```

Supported `check_type` values:
| Type | Required params |
|------|----------------|
| `not_empty` | `min_rows` (integer) |
| `freshness_days` | `max_days` (integer) |
| `max_null_fraction` | `column` (string), `max_fraction` (float 0–1) |

**Response `201`**:
```json
{
  "contract_id": "qc_003"
}
```

---

### `POST /tables/{zone}/{entity}/quality/run`
Run all active quality contracts against the table's current state.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "all_passed": false,
  "results": [
    {
      "contract_id": "qc_001",
      "check_type": "not_empty",
      "passed": true,
      "details": "Row count 10000 >= min_rows 1."
    },
    {
      "contract_id": "qc_002",
      "check_type": "max_null_fraction",
      "passed": false,
      "details": "Column 'email' null fraction 0.08 exceeds max 0.05."
    }
  ]
}
```

---

### `POST /tables/{zone}/{entity}/vacuum`
Remove Parquet files and catalog entries from old snapshots beyond the retention window.

**Request body**:
```json
{
  "retain_last_n": 3,
  "dry_run": true
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `retain_last_n` | No | Number of most recent snapshots to keep (default: 1) |
| `dry_run` | No | If `true`, preview deleted paths without actually deleting (default: `true`) |

> **Default is `dry_run: true`** to prevent accidental data loss. Pass `"dry_run": false` explicitly to execute.

**Response `200`**:
```json
{
  "table_id": "bronze.users",
  "dry_run": true,
  "snapshots_removed": 2,
  "files_removed": 4,
  "paths": [
    "warehouse/bronze/users/part-0-v1.parquet",
    "warehouse/bronze/users/part-0-v2.parquet"
  ]
}
```

---

## 9. Query

Execute arbitrary SQL against one or more tables using DuckDB. Supports time travel and partition pruning.

### `POST /query`
Run a SQL query. The table is registered as a DuckDB view named `{zone}_{entity}` (e.g., `bronze_users`, `silver_events`). Multiple tables can be joined by referencing their view names in SQL.

**Request body**:
```json
{
  "sql": "SELECT user_id, COUNT(*) AS event_count FROM bronze_users GROUP BY user_id ORDER BY event_count DESC LIMIT 10",
  "context": {
    "zone": "bronze",
    "entity": "users",
    "version": 3,
    "partition_filters": {
      "date": "2026-01-01"
    }
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `sql` | Yes | SQL query string |
| `context.zone` | Yes | Zone of the primary table |
| `context.entity` | Yes | Entity name of the primary table |
| `context.version` | No | Pin to a snapshot version (time travel) |
| `context.partition_filters` | No | Key/value map for partition pruning |

**Response `200`**:
```json
{
  "columns": ["user_id", "event_count"],
  "rows": [
    ["u001", 42],
    ["u002", 38]
  ],
  "row_count": 2,
  "version_used": 3
}
```

**Response `400`**: Invalid SQL syntax.

**Response `404`**: Table referenced in query does not exist.

---

## 10. Views

Logical and materialized views registered in the catalog.

### `GET /views`
List all registered views.

**Query parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `zone` | string | Filter by zone |
| `type` | string | `view` or `materialized_view` |

**Response `200`**:
```json
{
  "views": [
    {
      "view_id": "view_001",
      "name": "daily_users",
      "zone": "gold",
      "view_type": "view",
      "sql": "SELECT DISTINCT user_id FROM bronze_users",
      "owner": "default",
      "created_at": "2026-03-10T09:00:00Z"
    }
  ]
}
```

---

### `POST /views`
Register a new view or materialized view.

**Request body**:
```json
{
  "name": "user_summary",
  "zone": "gold",
  "view_type": "materialized_view",
  "sql": "SELECT user_id, COUNT(*) AS event_count FROM bronze_users GROUP BY user_id",
  "owner": "analytics_team"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique view name |
| `zone` | Yes | Zone for the view |
| `view_type` | Yes | `"view"` or `"materialized_view"` |
| `sql` | Yes | SQL definition |
| `owner` | No | Owning team or user (default: `"default"`) |

**Response `201`**:
```json
{
  "view_id": "view_002"
}
```

---

### `GET /views/{view_id}`
Get details for a specific view.

**Response `200`**:
```json
{
  "view_id": "view_002",
  "name": "user_summary",
  "zone": "gold",
  "view_type": "materialized_view",
  "sql": "SELECT user_id, COUNT(*) AS event_count FROM bronze_users GROUP BY user_id",
  "owner": "analytics_team",
  "refresh_snapshot_id": "snap_abc123",
  "last_refreshed_at": "2026-03-20T08:00:00Z",
  "created_at": "2026-03-10T09:00:00Z"
}
```

---

### `POST /views/{view_id}/refresh`
Refresh a materialized view to point to a new result snapshot.

**Request body**:
```json
{
  "snapshot_id": "snap_newresult"
}
```

**Response `200`**:
```json
{
  "view_id": "view_002",
  "refresh_snapshot_id": "snap_newresult",
  "last_refreshed_at": "2026-03-29T12:00:00Z"
}
```

**Response `422`**: `view_type` is `"view"` (only materialized views can be refreshed).

---

## Error Format

All error responses follow a consistent shape:

```json
{
  "error": {
    "code": "SCHEMA_EVOLUTION_ERROR",
    "message": "Column 'user_id' was removed — not allowed.",
    "details": {}
  }
}
```

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| `TABLE_NOT_FOUND` | 404 | Table does not exist in catalog |
| `SNAPSHOT_NOT_FOUND` | 404 | Version does not exist |
| `VIEW_NOT_FOUND` | 404 | View ID does not exist |
| `SCHEMA_EVOLUTION_ERROR` | 422 | Backward-incompatible schema change |
| `INVALID_SQL` | 400 | SQL syntax or reference error |
| `VALIDATION_ERROR` | 422 | Request body failed validation |
| `INTERNAL_ERROR` | 500 | Unexpected server-side failure |

---

## Endpoint Summary

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tables` | List all tables |
| `GET` | `/tables/{zone}/{entity}` | Get table metadata |
| `DELETE` | `/tables/{zone}/{entity}` | Deregister a table |
| `GET` | `/tables/{zone}/{entity}/snapshots` | List all snapshots |
| `GET` | `/tables/{zone}/{entity}/snapshots/latest` | Get latest snapshot |
| `GET` | `/tables/{zone}/{entity}/snapshots/{version}` | Get snapshot at version |
| `GET` | `/tables/{zone}/{entity}/schema` | Get schema (current or versioned) |
| `POST` | `/tables/{zone}/{entity}/schema/validate` | Validate schema evolution |
| `POST` | `/tables/{zone}/{entity}/data` | Write data (creates snapshot) |
| `GET` | `/tables/{zone}/{entity}/data` | Read data (current or versioned) |
| `POST` | `/tables/{zone}/{entity}/compact` | Compact files into one |
| `GET` | `/tables/{zone}/{entity}/partitions` | List partitions |
| `POST` | `/tables/{zone}/{entity}/partitions` | Register a partition |
| `GET` | `/tables/{zone}/{entity}/stats` | Table-level column stats |
| `GET` | `/tables/{zone}/{entity}/stats/files` | File-level column stats |
| `GET` | `/tables/{zone}/{entity}/lineage` | Get lineage (upstream/downstream) |
| `POST` | `/tables/{zone}/{entity}/lineage` | Record a lineage relationship |
| `GET` | `/tables/{zone}/{entity}/audit` | Get audit log |
| `GET` | `/tables/{zone}/{entity}/quality/contracts` | List quality contracts |
| `POST` | `/tables/{zone}/{entity}/quality/contracts` | Add quality contract |
| `POST` | `/tables/{zone}/{entity}/quality/run` | Run quality checks |
| `POST` | `/tables/{zone}/{entity}/vacuum` | Vacuum old snapshots |
| `POST` | `/query` | Execute SQL query |
| `GET` | `/views` | List views |
| `POST` | `/views` | Register a view |
| `GET` | `/views/{view_id}` | Get view details |
| `POST` | `/views/{view_id}/refresh` | Refresh a materialized view |
