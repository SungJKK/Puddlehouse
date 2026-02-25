import sqlite3, json, uuid, hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from config import config
from catalog.models import TableMeta, Snapshot, Partition, LineageRecord

class CatalogManager:
    def __init__(self, catalog_path: Path = None):
        self.catalog_path = catalog_path or config.catalog_path

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.catalog_path)
        con.row_factory = sqlite3.Row    # access columns by name
        return con

    # ── Table Registration ────────────────────────────────────────────

    def register_table(self, zone: str, entity: str, schema: list[dict] = None) -> str:
        """
        Register a new table or update an existing one.
        Returns table_id.
        """
        table_id    = f"{zone}.{entity}"
        location    = str(config.data_root / zone / entity)
        schema_json = json.dumps(schema) if schema else None
        now         = datetime.now(timezone.utc).isoformat()

        with self._connect() as con:
            existing = con.execute(
                "SELECT table_id FROM catalog_tables WHERE table_id = ?", (table_id,)
            ).fetchone()

            if existing:
                con.execute("""
                    UPDATE catalog_tables
                    SET schema_json=?, updated_at=?
                    WHERE table_id=?
                """, (schema_json, now, table_id))
            else:
                con.execute("""
                    INSERT INTO catalog_tables
                    (table_id, name, zone, entity, location, schema_json)
                    VALUES (?,?,?,?,?,?)
                """, (table_id, f"{zone}_{entity}", zone, entity, location, schema_json))

            self._audit(con, "REGISTER", table_id, {"schema": schema})
        return table_id

    # ── Snapshots (lightweight time travel) ──────────────────────────

    def create_snapshot(self, table_id: str, parquet_files: list[str],
                        row_count: int, byte_size: int) -> str:
        """
        Write a manifest file listing all parquet files for this version.
        Returns snapshot_id.
        """
        snapshot_id = str(uuid.uuid4())

        # Get next version number
        with self._connect() as con:
            result = con.execute(
                "SELECT MAX(version) FROM catalog_snapshots WHERE table_id=?", (table_id,)
            ).fetchone()
            version = (result[0] or 0) + 1

            # Write manifest file to disk
            manifest = {
                "snapshot_id": snapshot_id,
                "table_id":    table_id,
                "version":     version,
                "files":       parquet_files,
                "row_count":   row_count,
                "byte_size":   byte_size,
                "created_at":  datetime.now(timezone.utc).isoformat(),
            }
            manifest_path = config.meta_path / f"{table_id.replace('.','_')}_v{version}.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2))

            con.execute("""
                INSERT INTO catalog_snapshots
                (snapshot_id, table_id, version, manifest_path, row_count, byte_size)
                VALUES (?,?,?,?,?,?)
            """, (snapshot_id, table_id, version, str(manifest_path), row_count, byte_size))

            # Update row count on parent table
            con.execute(
                "UPDATE catalog_tables SET row_count=?, updated_at=? WHERE table_id=?",
                (row_count, datetime.now(timezone.utc).isoformat(), table_id)
            )
            self._audit(con, "SNAPSHOT", table_id, {"version": version, "rows": row_count})

        return snapshot_id

    # ── Lineage ───────────────────────────────────────────────────────

    def record_lineage(self, source_id: str, target_id: str,
                       job_name: str, run_id: str,
                       rows_read: int, rows_written: int):
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
                           file_path: str, row_count: int):
        partition_id = hashlib.md5(f"{table_id}{key}{val}{file_path}".encode()).hexdigest()
        with self._connect() as con:
            con.execute("""
                INSERT OR REPLACE INTO catalog_partitions
                (partition_id, table_id, partition_key, partition_val, file_path, row_count)
                VALUES (?,?,?,?,?,?)
            """, (partition_id, table_id, key, val, file_path, row_count))

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

    # ── Internal ──────────────────────────────────────────────────────

    def _audit(self, con: sqlite3.Connection, operation: str,
               table_id: str, details: dict):
        con.execute("""
            INSERT INTO catalog_audit_log (log_id, operation, table_id, details)
            VALUES (?,?,?,?)
        """, (str(uuid.uuid4()), operation, table_id, json.dumps(details)))
