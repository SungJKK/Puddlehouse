import pandas as pd
import pytest
from pathlib import Path

from storage.writer import write_parquet
from tests.conftest import db_connect


# ── T14: write_parquet — partitioned path ─────────────────────────────────────

def events_df():
    return pd.DataFrame([
        {"event_id": "e1", "date": "2025-01-01", "amount": 10.0},
        {"event_id": "e2", "date": "2025-01-01", "amount": 20.0},
        {"event_id": "e3", "date": "2025-01-02", "amount": 30.0},
        {"event_id": "e4", "date": "2025-01-03", "amount": 40.0},
    ])


class TestWriteParquetPartitioned:
    def test_returns_multiple_file_paths(self, writer_env):
        paths = write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        # 3 distinct date values → 3 files
        assert len(paths) == 3

    def test_all_files_exist_on_disk(self, writer_env):
        paths = write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        for p in paths:
            assert Path(p).exists()

    def test_files_nested_under_partition_directories(self, writer_env):
        paths = write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        # Each file should live inside a date=<value>/ directory
        assert all("date=" in p for p in paths)

    def test_snapshot_covers_all_partition_files(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        snap = writer_env.get_latest_snapshot("bronze.events")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        assert len(files) == 3

    def test_partitions_registered_in_catalog(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        con = db_connect(writer_env.catalog_path)
        rows = con.execute(
            "SELECT * FROM catalog_partitions WHERE table_id='bronze.events'"
        ).fetchall()
        con.close()
        assert len(rows) == 3

    def test_partition_key_stored_correctly(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        con = db_connect(writer_env.catalog_path)
        keys = {r["partition_key"] for r in con.execute(
            "SELECT partition_key FROM catalog_partitions WHERE table_id='bronze.events'"
        ).fetchall()}
        con.close()
        assert keys == {"date"}

    def test_partition_values_stored_correctly(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        con = db_connect(writer_env.catalog_path)
        vals = {r["partition_val"] for r in con.execute(
            "SELECT partition_val FROM catalog_partitions WHERE table_id='bronze.events'"
        ).fetchall()}
        con.close()
        assert vals == {"2025-01-01", "2025-01-02", "2025-01-03"}

    def test_snapshot_row_count_equals_total_rows(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        snap = writer_env.get_latest_snapshot("bronze.events")
        assert snap.row_count == 4

    def test_table_registered_in_catalog(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        tbl = writer_env.get_table("bronze.events")
        assert tbl is not None

    def test_second_write_appends_new_snapshot(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        snap = writer_env.get_latest_snapshot("bronze.events")
        assert snap.version == 2
