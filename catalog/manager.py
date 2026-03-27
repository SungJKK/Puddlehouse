import sqlite3, json, uuid, hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from config import config
from catalog.models import TableMeta, Column, Snapshot, CatalogFile, DeleteFile, View, Partition, LineageRecord


class CatalogManager:
    def __init__(self, catalog_path: Path = None):
        self.catalog_path = catalog_path or config.catalog_path

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.catalog_path)
        con.row_factory = sqlite3.Row
        return con

    # ── Table Registration ────────────────────────────────────────────

    def register_table(self, zone: str, entity: str) -> str:
        """Register a new table or touch updated_at on an existing one. Returns table_id."""
        table_id = f"{zone}.{entity}"
        location = str(config.data_root / zone / entity)
        now      = datetime.now(timezone.utc).isoformat()

        with self._connect() as con:
            existing = con.execute(
                "SELECT table_id FROM catalog_tables WHERE table_id = ?", (table_id,)
            ).fetchone()

            if existing:
                con.execute(
                    "UPDATE catalog_tables SET updated_at=? WHERE table_id=?",
                    (now, table_id)
                )
            else:
                con.execute("""
                    INSERT INTO catalog_tables (table_id, name, zone, entity, location)
                    VALUES (?,?,?,?,?)
                """, (table_id, f"{zone}_{entity}", zone, entity, location))

            self._audit(con, "REGISTER", table_id, {})
        return table_id

    # ── Column Registration (schema evolution) ────────────────────────

    def register_columns(self, table_id: str, version: int,
                         schema: list[dict]) -> dict[str, str]:
        """
        Upsert column definitions for this version.
        schema: [{"name": str, "type": str}]
        Returns {column_name: column_id} for the active schema.
        """
        with self._connect() as con:
            existing = {
                row["column_name"]: row
                for row in con.execute(
                    "SELECT * FROM catalog_columns WHERE table_id=? AND dropped_at_version IS NULL",
                    (table_id,)
                ).fetchall()
            }
            incoming_names = {col["name"] for col in schema}

            # Drop columns that are no longer in the schema
            for name, row in existing.items():
                if name not in incoming_names:
                    con.execute(
                        "UPDATE catalog_columns SET dropped_at_version=? WHERE column_id=?",
                        (version, row["column_id"])
                    )

            # Add new columns
            for order, col in enumerate(schema):
                if col["name"] not in existing:
                    col_id = str(uuid.uuid4())
                    con.execute("""
                        INSERT INTO catalog_columns
                        (column_id, table_id, column_name, column_type, column_order, added_at_version)
                        VALUES (?,?,?,?,?,?)
                    """, (col_id, table_id, col["name"], col["type"], order, version))

            # Return full active name→id map
            rows = con.execute(
                "SELECT column_id, column_name FROM catalog_columns "
                "WHERE table_id=? AND dropped_at_version IS NULL",
                (table_id,)
            ).fetchall()
            return {row["column_name"]: row["column_id"] for row in rows}

    # ── Snapshots ────────────────────────────────────────────────────

    def create_snapshot(self, table_id: str, files: list[dict],
                        row_count: int, byte_size: int) -> tuple[str, int, dict[str, str]]:
        """
        Commit a new snapshot and register its files in catalog_files.
        files: [{"file_path": str, "row_count": int, "byte_size": int}]
        Returns (snapshot_id, version, {file_path: file_id}).
        """
        snapshot_id = str(uuid.uuid4())

        with self._connect() as con:
            result = con.execute(
                "SELECT MAX(version) FROM catalog_snapshots WHERE table_id=?", (table_id,)
            ).fetchone()
            version = (result[0] or 0) + 1

            con.execute("""
                INSERT INTO catalog_snapshots (snapshot_id, table_id, version, row_count, byte_size)
                VALUES (?,?,?,?,?)
            """, (snapshot_id, table_id, version, row_count, byte_size))

            file_id_map: dict[str, str] = {}
            for f in files:
                file_id = str(uuid.uuid4())
                con.execute("""
                    INSERT INTO catalog_files (file_id, snapshot_id, table_id, file_path, row_count, byte_size)
                    VALUES (?,?,?,?,?,?)
                """, (file_id, snapshot_id, table_id, f["file_path"], f["row_count"], f["byte_size"]))
                file_id_map[f["file_path"]] = file_id

            con.execute(
                "UPDATE catalog_tables SET row_count=?, updated_at=? WHERE table_id=?",
                (row_count, datetime.now(timezone.utc).isoformat(), table_id)
            )
            self._audit(con, "SNAPSHOT", table_id, {"version": version, "rows": row_count})

        return snapshot_id, version, file_id_map

    # ── Column Statistics ─────────────────────────────────────────────

    def write_file_column_stats(self, file_id: str, table_id: str,
                                stats: list[dict]) -> None:
        """
        Write per-file, per-column stats. Called once per file after commit.
        stats: [{"column_id": str, "value_count": int, "null_count": int,
                 "min_value": str, "max_value": str, "column_size_bytes": int}]
        """
        with self._connect() as con:
            for s in stats:
                con.execute("""
                    INSERT OR REPLACE INTO catalog_file_column_stats
                    (file_id, table_id, column_id, value_count, null_count,
                     min_value, max_value, column_size_bytes)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (file_id, table_id, s["column_id"], s.get("value_count"),
                      s.get("null_count", 0), s.get("min_value"), s.get("max_value"),
                      s.get("column_size_bytes")))

    def upsert_column_stats(self, table_id: str, stats: list[dict]) -> None:
        """
        Update aggregate per-column stats for the table.
        stats: [{"column_id": str, "null_count": int, "min_value": str, "max_value": str}]
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as con:
            for s in stats:
                con.execute("""
                    INSERT OR REPLACE INTO catalog_column_stats
                    (table_id, column_id, null_count, min_value, max_value, updated_at)
                    VALUES (?,?,?,?,?,?)
                """, (table_id, s["column_id"], s.get("null_count", 0),
                      s.get("min_value"), s.get("max_value"), now))

    # ── Logical Deletes ───────────────────────────────────────────────

    def record_delete(self, table_id: str, snapshot_id: str, file_id: str,
                      delete_file_path: str, delete_count: int, byte_size: int) -> str:
        """Register a logical delete file targeting a specific data file. Returns delete_file_id."""
        delete_file_id = str(uuid.uuid4())
        with self._connect() as con:
            con.execute("""
                INSERT INTO catalog_delete_files
                (delete_file_id, table_id, snapshot_id, file_id, delete_file_path, delete_count, byte_size)
                VALUES (?,?,?,?,?,?,?)
            """, (delete_file_id, table_id, snapshot_id, file_id,
                  delete_file_path, delete_count, byte_size))
            self._audit(con, "DELETE", table_id,
                        {"file_id": file_id, "delete_count": delete_count})
        return delete_file_id

    # ── Views ────────────────────────────────────────────────────────

    def register_view(self, view_name: str, zone: str, view_type: str,
                      sql: str, owner: str = "system") -> str:
        """Register a view or materialized view. Returns view_id."""
        view_id = str(uuid.uuid4())
        with self._connect() as con:
            con.execute("""
                INSERT INTO catalog_views (view_id, view_name, zone, view_type, sql, owner)
                VALUES (?,?,?,?,?,?)
            """, (view_id, view_name, zone, view_type, sql, owner))
            self._audit(con, "VIEW", None,
                        {"view_name": view_name, "view_type": view_type})
        return view_id

    def refresh_materialized_view(self, view_id: str, snapshot_id: str) -> None:
        """Update a materialized view to point at a new result snapshot."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as con:
            con.execute("""
                UPDATE catalog_views
                SET refresh_snapshot_id=?, last_refreshed_at=?, updated_at=?
                WHERE view_id=?
            """, (snapshot_id, now, now, view_id))

    # ── Lineage ───────────────────────────────────────────────────────

    def record_lineage(self, source_id: str, target_id: str,
                       job_name: str, run_id: str,
                       rows_read: int, rows_written: int) -> None:
        lineage_id = str(uuid.uuid4())
        with self._connect() as con:
            con.execute("""
                INSERT INTO catalog_lineage
                (lineage_id, source_id, target_id, job_name, run_id, rows_read, rows_written)
                VALUES (?,?,?,?,?,?,?)
            """, (lineage_id, source_id, target_id, job_name, run_id, rows_read, rows_written))
            self._audit(con, "LINEAGE", target_id, {"source": source_id, "job": job_name})

    # ── Partitions ────────────────────────────────────────────────────

    def register_partition(self, table_id: str, key: str, val: str,
                           file_path: str, row_count: int) -> None:
        partition_id = hashlib.md5(f"{table_id}{key}{val}{file_path}".encode()).hexdigest()
        with self._connect() as con:
            con.execute("""
                INSERT OR REPLACE INTO catalog_partitions
                (partition_id, table_id, partition_key, partition_val, file_path, row_count)
                VALUES (?,?,?,?,?,?)
            """, (partition_id, table_id, key, val, file_path, row_count))

    # ── Atomic Write Commit ───────────────────────────────────────────

    def commit_write(
        self,
        zone: str,
        entity: str,
        files_meta: list[dict],
        row_count: int,
        byte_size: int,
        schema: list[dict],
        file_col_stats: dict[str, list[dict]],
        table_col_stats: list[dict],
        source_id: str,
        job_name: str,
        run_id: str,
        partitions: list[dict] = None,
    ) -> tuple[str, int, dict[str, str]]:
        """
        Atomically commit an entire write to the catalog in one SQLite transaction.

        file_col_stats:  {file_path: [{column_name, value_count, null_count,
                                       min_value, max_value, column_size_bytes}]}
        table_col_stats: [{column_name, null_count, min_value, max_value}]
        partitions:      [{"key": str, "val": str, "file_path": str, "row_count": int}]

        Returns (snapshot_id, version, {file_path: file_id}).
        """
        table_id    = f"{zone}.{entity}"
        location    = str(config.data_root / zone / entity)
        now         = datetime.now(timezone.utc).isoformat()
        snapshot_id = str(uuid.uuid4())

        with self._connect() as con:
            # 1. Register table (upsert)
            existing = con.execute(
                "SELECT table_id FROM catalog_tables WHERE table_id=?", (table_id,)
            ).fetchone()
            if existing:
                con.execute(
                    "UPDATE catalog_tables SET updated_at=? WHERE table_id=?", (now, table_id)
                )
            else:
                con.execute(
                    "INSERT INTO catalog_tables (table_id, name, zone, entity, location) VALUES (?,?,?,?,?)",
                    (table_id, f"{zone}_{entity}", zone, entity, location),
                )
            self._audit(con, "REGISTER", table_id, {})

            # 2. Create snapshot
            result  = con.execute(
                "SELECT MAX(version) FROM catalog_snapshots WHERE table_id=?", (table_id,)
            ).fetchone()
            version = (result[0] or 0) + 1

            con.execute(
                "INSERT INTO catalog_snapshots (snapshot_id, table_id, version, row_count, byte_size) VALUES (?,?,?,?,?)",
                (snapshot_id, table_id, version, row_count, byte_size),
            )

            file_id_map: dict[str, str] = {}
            for f in files_meta:
                file_id = str(uuid.uuid4())
                con.execute(
                    "INSERT INTO catalog_files (file_id, snapshot_id, table_id, file_path, row_count, byte_size) VALUES (?,?,?,?,?,?)",
                    (file_id, snapshot_id, table_id, f["file_path"], f["row_count"], f["byte_size"]),
                )
                file_id_map[f["file_path"]] = file_id

            con.execute(
                "UPDATE catalog_tables SET row_count=?, updated_at=? WHERE table_id=?",
                (row_count, now, table_id),
            )
            self._audit(con, "SNAPSHOT", table_id, {"version": version, "rows": row_count})

            # 3. Register columns → resolve name→id map
            existing_cols = {
                row["column_name"]: row
                for row in con.execute(
                    "SELECT * FROM catalog_columns WHERE table_id=? AND dropped_at_version IS NULL",
                    (table_id,),
                ).fetchall()
            }
            incoming_names = {col["name"] for col in schema}

            for name, row in existing_cols.items():
                if name not in incoming_names:
                    con.execute(
                        "UPDATE catalog_columns SET dropped_at_version=? WHERE column_id=?",
                        (version, row["column_id"]),
                    )

            for order, col in enumerate(schema):
                if col["name"] not in existing_cols:
                    con.execute(
                        "INSERT INTO catalog_columns (column_id, table_id, column_name, column_type, column_order, added_at_version) VALUES (?,?,?,?,?,?)",
                        (str(uuid.uuid4()), table_id, col["name"], col["type"], order, version),
                    )

            col_name_to_id = {
                row["column_name"]: row["column_id"]
                for row in con.execute(
                    "SELECT column_id, column_name FROM catalog_columns WHERE table_id=? AND dropped_at_version IS NULL",
                    (table_id,),
                ).fetchall()
            }

            # 4. Per-file column stats
            for file_path, stats in (file_col_stats or {}).items():
                fid = file_id_map.get(file_path)
                if not fid:
                    continue
                for s in stats:
                    cid = col_name_to_id.get(s["column_name"])
                    if not cid:
                        continue
                    con.execute(
                        "INSERT OR REPLACE INTO catalog_file_column_stats "
                        "(file_id, table_id, column_id, value_count, null_count, min_value, max_value, column_size_bytes) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (fid, table_id, cid, s.get("value_count"), s.get("null_count", 0),
                         s.get("min_value"), s.get("max_value"), s.get("column_size_bytes")),
                    )

            # 5. Aggregate table-level column stats
            for s in (table_col_stats or []):
                cid = col_name_to_id.get(s["column_name"])
                if not cid:
                    continue
                con.execute(
                    "INSERT OR REPLACE INTO catalog_column_stats "
                    "(table_id, column_id, null_count, min_value, max_value, updated_at) VALUES (?,?,?,?,?,?)",
                    (table_id, cid, s.get("null_count", 0), s.get("min_value"), s.get("max_value"), now),
                )

            # 6. Lineage
            con.execute(
                "INSERT INTO catalog_lineage (lineage_id, source_id, target_id, job_name, run_id, rows_read, rows_written) VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), source_id, table_id, job_name, run_id, 0, row_count),
            )
            self._audit(con, "LINEAGE", table_id, {"source": source_id, "job": job_name})

            # 7. Partitions
            for p in (partitions or []):
                pid = hashlib.md5(
                    f"{table_id}{p['key']}{p['val']}{p['file_path']}".encode()
                ).hexdigest()
                con.execute(
                    "INSERT OR REPLACE INTO catalog_partitions "
                    "(partition_id, table_id, partition_key, partition_val, file_path, row_count) VALUES (?,?,?,?,?,?)",
                    (pid, table_id, p["key"], p["val"], p["file_path"], p["row_count"]),
                )

        return snapshot_id, version, file_id_map

    # ── Reads / Discovery ─────────────────────────────────────────────

    def get_table(self, table_id: str) -> Optional[TableMeta]:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM catalog_tables WHERE table_id=?", (table_id,)
            ).fetchone()
            return TableMeta.from_row(row) if row else None

    def get_latest_snapshot(self, table_id: str) -> Optional[Snapshot]:
        with self._connect() as con:
            row = con.execute("""
                SELECT * FROM catalog_snapshots
                WHERE table_id=?
                ORDER BY version DESC LIMIT 1
            """, (table_id,)).fetchone()
            return Snapshot.from_row(row) if row else None

    def list_snapshots(self, table_id: str) -> list[Snapshot]:
        """Return all snapshots for a table ordered by version ascending."""
        with self._connect() as con:
            rows = con.execute("""
                SELECT * FROM catalog_snapshots
                WHERE table_id=?
                ORDER BY version ASC
            """, (table_id,)).fetchall()
            return [Snapshot.from_row(r) for r in rows]

    def get_snapshot_at_version(self, table_id: str, version: int) -> Optional[Snapshot]:
        """Return the snapshot for a specific version, or None if it doesn't exist."""
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM catalog_snapshots WHERE table_id=? AND version=?",
                (table_id, version),
            ).fetchone()
            return Snapshot.from_row(row) if row else None

    def list_tables(self, zone: str = None) -> list[TableMeta]:
        with self._connect() as con:
            if zone:
                rows = con.execute(
                    "SELECT * FROM catalog_tables WHERE zone=? AND is_active=1", (zone,)
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM catalog_tables WHERE is_active=1"
                ).fetchall()
            return [TableMeta.from_row(r) for r in rows]

    def get_schema_at_version(self, table_id: str, version: int) -> list[Column]:
        """Return the active column definitions at a given snapshot version."""
        with self._connect() as con:
            rows = con.execute("""
                SELECT * FROM catalog_columns
                WHERE table_id=?
                  AND added_at_version <= ?
                  AND (dropped_at_version IS NULL OR dropped_at_version > ?)
                ORDER BY column_order
            """, (table_id, version, version)).fetchall()
            return [Column.from_row(r) for r in rows]

    def get_snapshot_files(self, snapshot_id: str) -> list[CatalogFile]:
        """Return all data files belonging to a snapshot."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM catalog_files WHERE snapshot_id=?", (snapshot_id,)
            ).fetchall()
            return [CatalogFile.from_row(r) for r in rows]

    def get_table_files_at_version(self, table_id: str, version: int) -> list[CatalogFile]:
        """
        Return all files that make up the full table state at a given version.
        This includes files from all snapshots with version <= the given version,
        reflecting the cumulative (append) nature of the table format.
        """
        with self._connect() as con:
            rows = con.execute("""
                SELECT cf.* FROM catalog_files cf
                JOIN catalog_snapshots cs ON cf.snapshot_id = cs.snapshot_id
                WHERE cf.table_id = ?
                  AND cs.version <= ?
                ORDER BY cs.version ASC
            """, (table_id, version)).fetchall()
            return [CatalogFile.from_row(r) for r in rows]

    # ── Internal ──────────────────────────────────────────────────────

    def _audit(self, con: sqlite3.Connection, operation: str,
               table_id: Optional[str], details: dict) -> None:
        con.execute("""
            INSERT INTO catalog_audit_log (log_id, operation, table_id, details)
            VALUES (?,?,?,?)
        """, (str(uuid.uuid4()), operation, table_id, json.dumps(details)))
