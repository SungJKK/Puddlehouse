import pandas as pd
import pytest

from storage.writer import write_parquet, read_parquet_at_version


# ── P2-4: Time Travel ─────────────────────────────────────────────────────────
#
# Snapshot semantics are CUMULATIVE — snapshot v2 represents the full table
# state after 2 writes (all files from v1 + v2), matching standard lakehouse
# behaviour (Iceberg, Delta Lake).

def batch(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"id": ids, "val": range(len(ids))})


class TestGetSnapshotAtVersion:
    def test_returns_none_for_missing_version(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        assert writer_env.get_snapshot_at_version("bronze.users", 99) is None

    def test_returns_correct_snapshot_for_version(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b", "c"]), "bronze", "users")

        snap1 = writer_env.get_snapshot_at_version("bronze.users", 1)
        snap2 = writer_env.get_snapshot_at_version("bronze.users", 2)

        assert snap1.version == 1
        assert snap2.version == 2

    def test_snapshot_ids_differ_across_versions(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")

        snap1 = writer_env.get_snapshot_at_version("bronze.users", 1)
        snap2 = writer_env.get_snapshot_at_version("bronze.users", 2)

        assert snap1.snapshot_id != snap2.snapshot_id


class TestReadParquetAtVersion:
    def test_raises_for_nonexistent_version(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        with pytest.raises(ValueError, match="version"):
            read_parquet_at_version("bronze", "users", 99)

    def test_v1_returns_first_batch_only(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d", "e"]), "bronze", "users")

        df = read_parquet_at_version("bronze", "users", 1)
        assert set(df["id"].tolist()) == {"a", "b"}

    def test_v2_returns_cumulative_state(self, writer_env):
        # v2 = all rows from v1 + v2 (full table state after 2 writes)
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d", "e"]), "bronze", "users")

        df = read_parquet_at_version("bronze", "users", 2)
        assert set(df["id"].tolist()) == {"a", "b", "c", "d", "e"}
        assert len(df) == 5

    def test_row_counts_are_cumulative(self, writer_env):
        write_parquet(batch(["a"]),       "bronze", "users")   # v1: 1 row
        write_parquet(batch(["b", "c"]),  "bronze", "users")   # v2: 3 rows cumulative
        write_parquet(batch(["d", "e", "f"]), "bronze", "users")  # v3: 6 rows cumulative

        assert len(read_parquet_at_version("bronze", "users", 1)) == 1
        assert len(read_parquet_at_version("bronze", "users", 2)) == 3
        assert len(read_parquet_at_version("bronze", "users", 3)) == 6

    def test_older_version_unaffected_by_newer_write(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        v1_before = set(read_parquet_at_version("bronze", "users", 1)["id"].tolist())

        write_parquet(batch(["b", "c", "d"]), "bronze", "users")
        write_parquet(batch(["e"]), "bronze", "users")

        v1_after = set(read_parquet_at_version("bronze", "users", 1)["id"].tolist())
        assert v1_after == v1_before

    def test_returns_dataframe(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        assert isinstance(read_parquet_at_version("bronze", "users", 1), pd.DataFrame)

    def test_schema_preserved_at_version(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        df = read_parquet_at_version("bronze", "users", 1)
        assert "id"  in df.columns
        assert "val" in df.columns

    def test_filters_applied_within_version(self, writer_env):
        df1 = pd.DataFrame({"date": ["2025-01-01", "2025-01-01"], "val": [1, 2]})
        df2 = pd.DataFrame({"date": ["2025-01-02", "2025-01-02"], "val": [3, 4]})

        write_parquet(df1, "bronze", "events", partition_cols=["date"])
        write_parquet(df2, "bronze", "events", partition_cols=["date"])

        # At v1, only Jan-01 files exist — filter returns those 2 rows
        result = read_parquet_at_version(
            "bronze", "events", 1, filters=[("date", "=", "2025-01-01")]
        )
        assert len(result) == 2
        assert set(result["date"].tolist()) == {"2025-01-01"}
