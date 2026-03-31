import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pathlib import Path

from storage.writer import write_parquet
from tests.conftest import db_connect


# ── T13: write_parquet — non-partitioned path ─────────────────────────────────

def users_df(n=10):
    from faker import Faker
    import uuid
    fake = Faker()
    return pd.DataFrame([{
        "user_id": str(uuid.uuid4()),
        "name":    fake.name(),
        "email":   fake.email(),
    } for _ in range(n)])


class TestWriteParquetUnpartitioned:
    def test_returns_list_of_file_paths(self, writer_env, tmp_path):
        paths = write_parquet(users_df(), "bronze", "users")
        assert isinstance(paths, list)
        assert len(paths) == 1

    def test_file_written_to_disk(self, writer_env, tmp_path):
        paths = write_parquet(users_df(), "bronze", "users")
        assert Path(paths[0]).exists()

    def test_file_is_valid_parquet(self, writer_env, tmp_path):
        paths = write_parquet(users_df(5), "bronze", "users")
        pf = pq.ParquetFile(paths[0])
        assert pf.metadata.num_rows == 5

    def test_file_written_under_correct_zone_entity_path(self, writer_env):
        import config as cfg
        paths = write_parquet(users_df(), "silver", "orders")
        assert "silver" in paths[0]
        assert "orders" in paths[0]

    def test_table_registered_in_catalog(self, writer_env):
        write_parquet(users_df(), "bronze", "users")
        tbl = writer_env.get_table("bronze.users")
        assert tbl is not None
        assert tbl.zone == "bronze"
        assert tbl.entity == "users"

    def test_snapshot_created_in_catalog(self, writer_env):
        write_parquet(users_df(20), "bronze", "users")
        snap = writer_env.get_latest_snapshot("bronze.users")
        assert snap is not None
        assert snap.version == 1
        assert snap.row_count == 20

    def test_snapshot_version_increments_on_second_write(self, writer_env):
        write_parquet(users_df(10), "bronze", "users")
        write_parquet(users_df(10), "bronze", "users")
        snap = writer_env.get_latest_snapshot("bronze.users")
        assert snap.version == 2

    def test_columns_registered_in_catalog(self, writer_env):
        write_parquet(users_df(), "bronze", "users")
        snap = writer_env.get_latest_snapshot("bronze.users")
        cols = writer_env.get_schema_at_version("bronze.users", snap.version)
        col_names = {c.column_name for c in cols}
        assert {"user_id", "name", "email"}.issubset(col_names)

    def test_file_registered_in_catalog_files(self, writer_env):
        write_parquet(users_df(), "bronze", "users")
        snap = writer_env.get_latest_snapshot("bronze.users")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        assert len(files) == 1
        assert Path(files[0].file_path).exists()

    def test_lineage_recorded(self, writer_env):
        write_parquet(users_df(), "bronze", "users", source_id="external:csv", job_name="ingest")
        con = db_connect(writer_env.catalog_path)
        row = con.execute("SELECT * FROM catalog_lineage WHERE target_id='bronze.users'").fetchone()
        con.close()
        assert row is not None
        assert row["source_id"] == "external:csv"
        assert row["job_name"] == "ingest"

    def test_file_column_stats_written(self, writer_env):
        write_parquet(users_df(), "bronze", "users")
        snap = writer_env.get_latest_snapshot("bronze.users")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        con = db_connect(writer_env.catalog_path)
        count = con.execute(
            "SELECT COUNT(*) FROM catalog_file_column_stats WHERE file_id=?",
            (files[0].file_id,)
        ).fetchone()[0]
        con.close()
        assert count > 0

    def test_table_level_column_stats_written(self, writer_env):
        write_parquet(users_df(), "bronze", "users")
        con = db_connect(writer_env.catalog_path)
        count = con.execute(
            "SELECT COUNT(*) FROM catalog_column_stats WHERE table_id='bronze.users'"
        ).fetchone()[0]
        con.close()
        assert count > 0

    def test_row_count_is_cumulative_across_writes(self, writer_env):
        write_parquet(users_df(10), "bronze", "users")
        write_parquet(users_df(15), "bronze", "users")
        write_parquet(users_df(5), "bronze", "users")
        snap = writer_env.get_latest_snapshot("bronze.users")
        assert snap.row_count == 30
        tbl = writer_env.get_table("bronze.users")
        assert tbl.row_count == 30

    def test_row_count_subtracts_logical_deletes(self, writer_env, tmp_path):
        # Write 10 rows, then register 3 logical deletes, then write 5 more rows.
        # The final snapshot row_count should be 10 - 3 + 5 = 12.
        write_parquet(users_df(10), "bronze", "users")

        snap = writer_env.get_latest_snapshot("bronze.users")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        data_file = files[0]

        delete_path = str(tmp_path / "delete.parquet")
        pq.write_table(pa.table({"user_id": ["x", "y", "z"], "name": ["a", "b", "c"], "email": ["", "", ""]}), delete_path)
        writer_env.record_delete(
            table_id="bronze.users",
            snapshot_id=snap.snapshot_id,
            file_id=data_file.file_id,
            delete_file_path=delete_path,
            delete_count=3,
            byte_size=100,
        )

        write_parquet(users_df(5), "bronze", "users")

        snap2 = writer_env.get_latest_snapshot("bronze.users")
        assert snap2.row_count == 12
        tbl = writer_env.get_table("bronze.users")
        assert tbl.row_count == 12
