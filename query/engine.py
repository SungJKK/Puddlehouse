import duckdb
import pandas as pd
from catalog.manager import CatalogManager
from config import config

catalog = CatalogManager()


class QueryEngine:
    def __init__(self, catalog: CatalogManager = None):
        self._catalog = catalog or globals()["catalog"]
        self._con = duckdb.connect()

    def query(
        self,
        sql: str,
        zone: str,
        entity: str,
        version: int = None,
        partition_filters: dict[str, str] = None,
    ) -> pd.DataFrame:
        """
        Execute SQL against the catalog-resolved file set for zone/entity.

        The table is available in SQL as '{zone}_{entity}' (e.g. 'bronze_users').

        version:           if set, pins file resolution to this snapshot version (time travel).
        partition_filters: {partition_key: partition_val} — prunes the file list to only
                           files whose partition values match all given filters.

        Raises ValueError if the table has no snapshots or the requested version doesn't exist.
        """
        table_id  = f"{zone}.{entity}"
        view_name = f"{zone}_{entity}"

        file_paths = self._resolve_files(table_id, version, partition_filters)
        self._con.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet({file_paths!r})"
        )
        return self._con.execute(sql).df()

    # ── Internal ──────────────────────────────────────────────────────

    def _resolve_files(
        self,
        table_id: str,
        version: int = None,
        partition_filters: dict[str, str] = None,
    ) -> list[str]:
        if version is not None:
            snap = self._catalog.get_snapshot_at_version(table_id, version)
            if snap is None:
                raise ValueError(f"No snapshot at version {version} for {table_id}")
            v = version
        else:
            snap = self._catalog.get_latest_snapshot(table_id)
            if snap is None:
                raise ValueError(f"No snapshots found for {table_id}")
            v = snap.version

        files = self._catalog.get_table_files_at_version(table_id, v)
        if not files:
            raise ValueError(f"No files found for {table_id} at version {v}")

        # Deduplicate preserving order — a file can appear in multiple snapshots
        # if the partitioned writer re-registers existing files on each write.
        seen: set[str] = set()
        file_paths: list[str] = []
        for f in files:
            if f.file_path not in seen:
                seen.add(f.file_path)
                file_paths.append(f.file_path)

        if partition_filters:
            file_paths = self._prune_by_partitions(table_id, file_paths, partition_filters)

        return file_paths

    def _prune_by_partitions(
        self,
        table_id: str,
        file_paths: list[str],
        partition_filters: dict[str, str],
    ) -> list[str]:
        """
        Prune file_paths using catalog_partitions.
        Files that are partitioned but do NOT match all filters are excluded.
        Files with no partition records are always included (cannot be pruned).
        """
        exclusions: set[str] = set()

        for key, val in partition_filters.items():
            with self._catalog._connect() as con:
                all_rows = con.execute(
                    "SELECT DISTINCT file_path FROM catalog_partitions "
                    "WHERE table_id=? AND partition_key=?",
                    (table_id, key),
                ).fetchall()
                match_rows = con.execute(
                    "SELECT DISTINCT file_path FROM catalog_partitions "
                    "WHERE table_id=? AND partition_key=? AND partition_val=?",
                    (table_id, key, str(val)),
                ).fetchall()

            partitioned = {row["file_path"] for row in all_rows}
            matched     = {row["file_path"] for row in match_rows}

            # Files that are partitioned by this key but don't match the value are excluded
            exclusions.update(partitioned - matched)

        return [p for p in file_paths if p not in exclusions]
