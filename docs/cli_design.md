# Lakehouse CLI Design

The CLI (`lh`) is a thin client over the REST API. Every command translates to one or more API calls — no direct catalog or storage access occurs from the CLI itself.

**Command pattern**: `lh <group> <verb> [target] [flags]`

---

## Global Flags

These flags apply to every command.

| Flag | Default | Description |
|------|---------|-------------|
| `--api-url` | `http://localhost:8000/api/v1` | Base URL of the lakehouse API server |
| `--output`, `-o` | `table` | Output format: `table`, `json`, `csv` |
| `--quiet`, `-q` | false | Suppress decorative output; print only data |
| `--help`, `-h` | — | Show help for the command |

The `--api-url` can also be set via the environment variable `LH_API_URL`.

---

## Command Groups

| Group | Description |
|-------|-------------|
| [`lh tables`](#tables) | Table discovery and deregistration |
| [`lh snapshots`](#snapshots) | Snapshot listing and time travel |
| [`lh schema`](#schema) | Schema inspection and evolution validation |
| [`lh data`](#data) | Read, write, and compact data |
| [`lh partitions`](#partitions) | Partition registration and listing |
| [`lh stats`](#stats) | Column statistics |
| [`lh lineage`](#lineage) | Data lineage tracking |
| [`lh audit`](#audit) | Audit log |
| [`lh quality`](#quality) | Quality contracts and checks |
| [`lh vacuum`](#vacuum) | Retention and cleanup |
| [`lh query`](#query) | Execute SQL queries |
| [`lh views`](#views) | View and materialized view management |

---

## Tables

Manage table registration and discovery.

### `lh tables list`
List all registered tables.

```
lh tables list [--zone <zone>]
```

| Flag | Description |
|------|-------------|
| `--zone` | Filter by zone: `bronze`, `silver`, `gold` |

**Example**:
```
$ lh tables list --zone bronze

TABLE ID          ZONE    ENTITY   ROW COUNT   UPDATED
bronze.users      bronze  users    10,000      2026-03-29 12:00
bronze.events     bronze  events   250,000     2026-03-28 09:30
```

---

### `lh tables get`
Show metadata for a specific table.

```
lh tables get <zone>/<entity>
```

**Example**:
```
$ lh tables get bronze/users

Table ID:       bronze.users
Zone:           bronze
Entity:         users
Location:       warehouse/bronze/users
Owner:          default
Row Count:      10,000
Latest Version: 5
Created:        2026-03-01 10:00
Updated:        2026-03-29 12:00
```

---

### `lh tables delete`
Deregister a table from the catalog. Does not delete Parquet files.

```
lh tables delete <zone>/<entity> [--confirm]
```

| Flag | Description |
|------|-------------|
| `--confirm` | Skip interactive confirmation prompt |

**Example**:
```
$ lh tables delete bronze/users
Deregister table bronze.users from the catalog? (y/N): y
Table bronze.users deregistered.
```

---

## Snapshots

Inspect the version history of a table.

### `lh snapshots list`
List all snapshots for a table, oldest to newest.

```
lh snapshots list <zone>/<entity>
```

**Example**:
```
$ lh snapshots list bronze/users

VERSION   SNAPSHOT ID    ROW COUNT   SIZE       CREATED
1         snap_abc123    1,000       200 KB     2026-03-01 10:00
2         snap_def456    2,000       400 KB     2026-03-05 14:30
3         snap_ghi789    10,000      1.9 MB     2026-03-29 12:00
```

---

### `lh snapshots latest`
Show the most recent snapshot and its files.

```
lh snapshots latest <zone>/<entity>
```

**Example**:
```
$ lh snapshots latest bronze/users

Snapshot:  snap_ghi789
Version:   3
Row Count: 10,000
Size:      1.9 MB
Created:   2026-03-29 12:00

FILES:
FILE ID        PATH                                   ROWS    SIZE
file_xyz789    warehouse/bronze/users/part-0.parquet  10,000  1.9 MB
```

---

### `lh snapshots get`
Show a specific snapshot by version.

```
lh snapshots get <zone>/<entity> --version <n>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--version` | Yes | Snapshot version number |

**Example**:
```
$ lh snapshots get bronze/users --version 2
```

---

## Schema

Inspect column schemas and validate evolution.

### `lh schema get`
Show the schema for a table. Defaults to the current version.

```
lh schema get <zone>/<entity> [--version <n>]
```

| Flag | Description |
|------|-------------|
| `--version` | Show schema as it existed at this snapshot version |

**Example**:
```
$ lh schema get bronze/users

Table:   bronze.users
Version: 5

POSITION  NAME      TYPE    ADDED   DROPPED
0         user_id   string  v1      —
1         age       int64   v1      —
2         email     string  v2      —
```

---

### `lh schema validate`
Check whether a proposed schema is backward-compatible. Does not modify anything.

```
lh schema validate <zone>/<entity> --file <schema.json>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--file` | Yes | Path to a JSON file containing the proposed schema |

The schema file is an array of `{"name": "...", "type": "..."}` objects:
```json
[
  {"name": "user_id", "type": "string"},
  {"name": "age", "type": "int64"},
  {"name": "email", "type": "string"}
]
```

**Example (compatible)**:
```
$ lh schema validate bronze/users --file new_schema.json
Schema is backward-compatible.
Added columns: email
```

**Example (incompatible)**:
```
$ lh schema validate bronze/users --file new_schema.json
Schema validation failed:
  - Column 'age' type changed from int64 to string — not allowed.
  - Column 'user_id' was removed — not allowed.
```

Exit code is `1` on validation failure.

---

## Data

Read and write Parquet data.

### `lh data write`
Write data to a table from a local file. Creates a new snapshot atomically.

```
lh data write <zone>/<entity> --file <path> [flags]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--file` | Yes | Path to a local `.parquet` file to ingest (CSV and JSON not yet supported) |
| `--partition-cols` | No | Comma-separated column names to partition by (e.g., `date,region`) |
| `--job-name` | No | Label for lineage tracking (default: `"cli"`) |
| `--run-id` | No | Idempotency/tracking key for the job run |
| `--source-id` | No | Source table_id or `external:<label>` (default: `"external:cli"`) |

**Example**:
```
$ lh data write bronze/users --file users.parquet --partition-cols date --job-name daily_ingest

Snapshot created.
Version:    4
Files:      2
Row Count:  5,000
Size:       980 KB
```

---

### `lh data read`
Read data from a table and print to stdout.

```
lh data read <zone>/<entity> [--version <n>] [--limit <n>] [--offset <n>]
```

| Flag | Description |
|------|-------------|
| `--version` | Time travel: read at this snapshot version |
| `--limit` | Max rows to return (default: 1000) |
| `--offset` | Row offset for pagination (default: 0) |

For large tables, prefer `lh query` with an explicit SQL filter.

**Example**:
```
$ lh data read bronze/users --version 2 --limit 5 -o csv

user_id,age,email
u001,30,a@x.com
u002,25,b@x.com
```

---

### `lh data compact`
Merge all files in the latest snapshot into a single Parquet file. Creates a new snapshot; old snapshots are preserved.

```
lh data compact <zone>/<entity>
```

**Example**:
```
$ lh data compact bronze/users

Compaction complete.
Version:        6
Files Merged:   5
Output File:    warehouse/bronze/users/compacted-v6.parquet
Row Count:      10,000
```

---

## Partitions

### `lh partitions list`
List all partition entries for a table.

```
lh partitions list <zone>/<entity>
```

**Example**:
```
$ lh partitions list bronze/users

KEY    VALUE        FILE                                            ROWS
date   2026-01-01   warehouse/bronze/users/date=2026-01-01/...    5,000
date   2026-01-02   warehouse/bronze/users/date=2026-01-02/...    4,800
```

---

### `lh partitions add`
Register a partition entry for a specific file.

```
lh partitions add <zone>/<entity> --key <key> --value <value> --file-path <path> --row-count <n>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--key` | Yes | Partition key (e.g., `date`) |
| `--value` | Yes | Partition value (e.g., `2026-01-01`) |
| `--file-path` | Yes | Path to the Parquet file for this partition |
| `--row-count` | Yes | Number of rows in the file |

**Example**:
```
$ lh partitions add bronze/users \
    --key date --value 2026-01-01 \
    --file-path warehouse/bronze/users/date=2026-01-01/part-0.parquet \
    --row-count 5000

Partition registered. ID: part_003
```

---

## Stats

Inspect column statistics.

### `lh stats table`
Show aggregate table-level column statistics.

```
lh stats table <zone>/<entity>
```

**Example**:
```
$ lh stats table bronze/users

Table: bronze.users

COLUMN    NULL COUNT   MIN      MAX
user_id   0            u001     u999
age       12           18       85
email     800          —        —
```

---

### `lh stats files`
Show per-file, per-column statistics.

```
lh stats files <zone>/<entity>
```

**Example**:
```
$ lh stats files bronze/users

FILE: warehouse/bronze/users/part-0.parquet (file_xyz789)
  COLUMN    NULL COUNT   MIN    MAX     SIZE
  user_id   0            u001   u500    8 KB
  age       5            18     75      4 KB
```

---

## Lineage

Track data derivation across tables.

### `lh lineage get`
Show upstream and downstream lineage for a table.

```
lh lineage get <zone>/<entity> [--direction <upstream|downstream|both>]
```

| Flag | Description |
|------|-------------|
| `--direction` | `upstream`, `downstream`, or `both` (default: `both`) |

**Example**:
```
$ lh lineage get silver/events --direction upstream

Upstream of silver.events:

SOURCE               JOB                  RUN ID              ROWS IN    ROWS OUT   AT
bronze.raw_events    clean_events_job     run_20260329_001    10,000     9,500      2026-03-29 10:00
```

---

### `lh lineage record`
Record a lineage relationship: a source table produced this table.

```
lh lineage record <zone>/<entity> --source <source_id> [flags]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--source` | Yes | Source table_id (e.g., `bronze.raw_events`) or `external:<label>` |
| `--job-name` | No | Name of the job that performed the transformation |
| `--run-id` | No | Unique identifier for this job run |
| `--rows-read` | No | Number of rows read from the source |
| `--rows-written` | No | Number of rows written to this table |

**Example**:
```
$ lh lineage record silver/events \
    --source bronze.raw_events \
    --job-name clean_events_job \
    --run-id run_20260329_001 \
    --rows-read 10000 \
    --rows-written 9500

Lineage recorded. ID: lin_007
```

---

## Audit

### `lh audit`
Show the audit log for a table.

```
lh audit <zone>/<entity> [--limit <n>]
```

| Flag | Description |
|------|-------------|
| `--limit` | Max entries to show (default: 100) |

**Example**:
```
$ lh audit bronze/users --limit 5

AT                    OPERATION   DETAILS
2026-03-29 12:00:00   SNAPSHOT    version=3, rows=2, bytes=1024
2026-03-15 08:30:00   LINEAGE     source=external:api, rows_written=10000
2026-03-10 10:00:00   SNAPSHOT    version=2, rows=1000, bytes=204800
2026-03-05 09:00:00   SNAPSHOT    version=1, rows=1000, bytes=204800
2026-03-01 10:00:00   REGISTER    zone=bronze, entity=users
```

---

## Quality

Manage and run data quality contracts.

### `lh quality contracts list`
List all quality contracts for a table.

```
lh quality contracts list <zone>/<entity>
```

**Example**:
```
$ lh quality contracts list bronze/users

ID        CHECK TYPE           PARAMS                                    ACTIVE
qc_001    not_empty            min_rows=1                                yes
qc_002    max_null_fraction    column=email, max_fraction=0.05           yes
qc_003    freshness_days       max_days=7                                yes
```

---

### `lh quality contracts add`
Add a quality contract to a table.

```
lh quality contracts add <zone>/<entity> --check-type <type> --params <json>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--check-type` | Yes | `not_empty`, `freshness_days`, or `max_null_fraction` |
| `--params` | Yes | JSON string of check parameters |

**Supported check types and params**:

| Check Type | Params |
|------------|--------|
| `not_empty` | `{"min_rows": 1}` |
| `freshness_days` | `{"max_days": 7}` |
| `max_null_fraction` | `{"column": "email", "max_fraction": 0.05}` |

**Example**:
```
$ lh quality contracts add bronze/users \
    --check-type max_null_fraction \
    --params '{"column": "email", "max_fraction": 0.05}'

Quality contract added. ID: qc_004
```

---

### `lh quality run`
Run all active quality contracts for a table and print results.

```
lh quality run <zone>/<entity>
```

Exit code is `1` if any contract fails.

**Example (all pass)**:
```
$ lh quality run bronze/users

PASSED  ID       CHECK TYPE           DETAILS
  ✓     qc_001   not_empty            Row count 10000 >= min_rows 1.
  ✓     qc_002   max_null_fraction    Column 'email' null fraction 0.02 <= 0.05.
  ✓     qc_003   freshness_days       Latest snapshot is 0 days old.

All checks passed.
```

**Example (failure)**:
```
$ lh quality run bronze/users

PASSED  ID       CHECK TYPE           DETAILS
  ✓     qc_001   not_empty            Row count 10000 >= min_rows 1.
  ✗     qc_002   max_null_fraction    Column 'email' null fraction 0.08 exceeds max 0.05.

1 of 2 checks failed.
```

---

## Vacuum

Remove old snapshots and their Parquet files beyond the retention window.

### `lh vacuum`

```
lh vacuum <zone>/<entity> [--retain-last-n <n>] [--execute]
```

| Flag | Description |
|------|-------------|
| `--retain-last-n` | Number of most recent snapshots to keep (default: 1) |
| `--execute` | Actually delete files and catalog entries. Without this flag, runs in dry-run mode. |

**Default is dry-run** — always preview first, then re-run with `--execute` to commit.

**Example (dry run)**:
```
$ lh vacuum bronze/users --retain-last-n 3

DRY RUN — no files deleted.
Snapshots to remove: 2
Files to remove:     4

PATH
warehouse/bronze/users/part-0-v1.parquet
warehouse/bronze/users/part-0-v2.parquet
warehouse/bronze/users/part-1-v1.parquet
warehouse/bronze/users/part-1-v2.parquet

Re-run with --execute to delete.
```

**Example (execute)**:
```
$ lh vacuum bronze/users --retain-last-n 3 --execute

Vacuum complete.
Snapshots removed: 2
Files removed:     4
```

---

## Query

Execute arbitrary SQL against table data using DuckDB.

### `lh query`

```
lh query --table <zone>/<entity> [flags]
```

SQL is provided either inline via `--sql` or from a file via `--file`. The table is registered as a DuckDB view named `{zone}_{entity}` (e.g., `bronze_users`).

| Flag | Required | Description |
|------|----------|-------------|
| `--table` | Yes | Primary table to query (`zone/entity`) |
| `--sql` | Yes* | SQL query string |
| `--file` | Yes* | Path to a `.sql` file (*one of `--sql` or `--file` required) |
| `--version` | No | Pin to a snapshot version (time travel) |
| `--partition` | No | Partition filter as `key=value`; repeatable |

**Example (inline SQL)**:
```
$ lh query --table bronze/users \
    --sql "SELECT age, COUNT(*) AS cnt FROM bronze_users GROUP BY age ORDER BY cnt DESC LIMIT 5"

AGE   CNT
30    142
25    138
28    131
32    120
27    119
```

**Example (SQL file with time travel)**:
```
$ lh query --table bronze/users --file analysis.sql --version 3
```

**Example (partition pruning)**:
```
$ lh query --table bronze/events \
    --sql "SELECT COUNT(*) FROM bronze_events" \
    --partition date=2026-01-01 \
    --partition region=US
```

**Example (pipe to file)**:
```
$ lh query --table bronze/users \
    --sql "SELECT * FROM bronze_users" \
    -o csv > output.csv
```

---

## Views

Manage logical and materialized views.

### `lh views list`
List all registered views.

```
lh views list [--zone <zone>] [--type <view|materialized_view>]
```

**Example**:
```
$ lh views list --zone gold

VIEW ID    NAME           ZONE   TYPE                 OWNER            LAST REFRESHED
view_001   daily_users    gold   view                 default          —
view_002   user_summary   gold   materialized_view    analytics_team   2026-03-20 08:00
```

---

### `lh views get`
Show details for a specific view.

```
lh views get <view_id>
```

**Example**:
```
$ lh views get view_002

View ID:        view_002
Name:           user_summary
Zone:           gold
Type:           materialized_view
Owner:          analytics_team
Last Refreshed: 2026-03-20 08:00
Snapshot:       snap_abc123
Created:        2026-03-10 09:00

SQL:
  SELECT user_id, COUNT(*) AS event_count
  FROM bronze_users
  GROUP BY user_id
```

---

### `lh views create`
Register a new view or materialized view.

```
lh views create --name <name> --zone <zone> --type <type> [--sql <sql> | --file <path>] [--owner <owner>]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | Yes | Unique view name |
| `--zone` | Yes | Zone for the view: `bronze`, `silver`, `gold` |
| `--type` | Yes | `view` or `materialized_view` |
| `--sql` | Yes* | SQL definition string |
| `--file` | Yes* | Path to a `.sql` file (*one of `--sql` or `--file` required) |
| `--owner` | No | Owning team or user (default: `"default"`) |

**Example**:
```
$ lh views create \
    --name user_summary \
    --zone gold \
    --type materialized_view \
    --file user_summary.sql \
    --owner analytics_team

View registered. ID: view_003
```

---

### `lh views refresh`
Refresh a materialized view to point to a new result snapshot.

```
lh views refresh <view_id> --snapshot-id <snapshot_id>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--snapshot-id` | Yes | Snapshot ID of the new materialized result |

**Example**:
```
$ lh views refresh view_002 --snapshot-id snap_newresult

Materialized view refreshed.
View:       view_002
Snapshot:   snap_newresult
Refreshed:  2026-03-29 12:30:00
```

---

## Output Formats

All commands support `--output` / `-o` with three formats:

| Format | Description |
|--------|-------------|
| `table` | Human-readable aligned table (default) |
| `json` | Raw JSON matching the API response body |
| `csv` | Comma-separated values, suitable for piping |

**Example**:
```
$ lh snapshots list bronze/users -o json
{
  "table_id": "bronze.users",
  "snapshots": [...]
}
```

---

## Configuration File

Global defaults can be set in `~/.lh/config.toml` to avoid repeating flags:

```toml
api_url = "http://localhost:8000/api/v1"
output  = "table"
```

Precedence (highest to lowest): command-line flag → environment variable (`LH_API_URL`) → config file → built-in default.

---

## Command Summary

```
lh tables list                        List all tables
lh tables get <zone>/<entity>         Get table metadata
lh tables delete <zone>/<entity>      Deregister a table

lh snapshots list <zone>/<entity>     List all snapshots
lh snapshots latest <zone>/<entity>   Show latest snapshot and files
lh snapshots get <zone>/<entity>      Get snapshot at --version N

lh schema get <zone>/<entity>         Show schema (current or --version N)
lh schema validate <zone>/<entity>    Validate schema from --file

lh data write <zone>/<entity>         Write data from --file
lh data read <zone>/<entity>          Read data (current or --version N)
lh data compact <zone>/<entity>       Compact files into one

lh partitions list <zone>/<entity>    List partition entries
lh partitions add <zone>/<entity>     Register a partition

lh stats table <zone>/<entity>        Table-level column stats
lh stats files <zone>/<entity>        File-level column stats

lh lineage get <zone>/<entity>        Show upstream/downstream lineage
lh lineage record <zone>/<entity>     Record a lineage relationship

lh audit <zone>/<entity>              Show audit log

lh quality contracts list <zone>/<entity>   List quality contracts
lh quality contracts add <zone>/<entity>    Add a quality contract
lh quality run <zone>/<entity>              Run all quality checks

lh vacuum <zone>/<entity>             Preview or execute vacuum

lh query                              Execute a SQL query

lh views list                         List views
lh views get <view_id>                Show view details
lh views create                       Register a view
lh views refresh <view_id>            Refresh a materialized view
```
