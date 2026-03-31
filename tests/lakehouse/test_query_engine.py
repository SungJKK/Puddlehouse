import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from storage.writer import write_parquet
from query.engine import QueryEngine


def batch(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"id": ids, "val": range(len(ids))})


@pytest.fixture()
def engine(writer_env):
    return QueryEngine(catalog=writer_env)


# ── P3-4: QueryEngine ─────────────────────────────────────────────────────────


class TestQueryBasic:
    def test_returns_dataframe(self, engine, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        result = engine.query("SELECT * FROM bronze_users", "bronze", "users")
        assert isinstance(result, pd.DataFrame)

    def test_returns_all_rows(self, engine, writer_env):
        write_parquet(batch(["a", "b", "c"]), "bronze", "users")
        result = engine.query("SELECT * FROM bronze_users", "bronze", "users")
        assert len(result) == 3

    def test_returns_correct_columns(self, engine, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        result = engine.query("SELECT * FROM bronze_users", "bronze", "users")
        assert "id" in result.columns
        assert "val" in result.columns

    def test_column_selection(self, engine, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        result = engine.query("SELECT id FROM bronze_users", "bronze", "users")
        assert list(result.columns) == ["id"]

    def test_where_clause_filters_rows(self, engine, writer_env):
        write_parquet(batch(["a", "b", "c"]), "bronze", "users")
        result = engine.query(
            "SELECT * FROM bronze_users WHERE id = 'a'", "bronze", "users"
        )
        assert len(result) == 1
        assert result["id"].iloc[0] == "a"

    def test_aggregate_count(self, engine, writer_env):
        write_parquet(batch(["a", "b", "c"]), "bronze", "users")
        result = engine.query(
            "SELECT COUNT(*) AS n FROM bronze_users", "bronze", "users"
        )
        assert result["n"].iloc[0] == 3

    def test_aggregate_sum(self, engine, writer_env):
        write_parquet(batch(["a", "b", "c"]), "bronze", "users")
        result = engine.query(
            "SELECT SUM(val) AS total FROM bronze_users", "bronze", "users"
        )
        assert result["total"].iloc[0] == 0 + 1 + 2

    def test_multiple_writes_cumulative(self, engine, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d"]), "bronze", "users")
        result = engine.query("SELECT * FROM bronze_users", "bronze", "users")
        assert set(result["id"].tolist()) == {"a", "b", "c", "d"}


class TestQueryErrors:
    def test_raises_for_no_snapshots(self, engine, writer_env):
        # Register a table but never write any data
        writer_env.register_table("bronze", "empty")
        with pytest.raises(ValueError, match="No snapshots"):
            engine.query("SELECT * FROM bronze_empty", "bronze", "empty")

    def test_raises_for_unregistered_table(self, engine, writer_env):
        with pytest.raises(ValueError):
            engine.query("SELECT * FROM bronze_ghost", "bronze", "ghost")

    def test_raises_for_nonexistent_version(self, engine, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        with pytest.raises(ValueError, match="version"):
            engine.query(
                "SELECT * FROM bronze_users", "bronze", "users", version=99
            )


class TestQueryTimeTravel:
    def test_version_1_returns_first_batch_only(self, engine, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d"]), "bronze", "users")
        result = engine.query(
            "SELECT * FROM bronze_users", "bronze", "users", version=1
        )
        assert set(result["id"].tolist()) == {"a", "b"}

    def test_version_2_is_cumulative(self, engine, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d"]), "bronze", "users")
        result = engine.query(
            "SELECT * FROM bronze_users", "bronze", "users", version=2
        )
        assert set(result["id"].tolist()) == {"a", "b", "c", "d"}

    def test_older_version_unaffected_by_newer_writes(self, engine, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        v1_result = engine.query(
            "SELECT * FROM bronze_users", "bronze", "users", version=1
        )

        write_parquet(batch(["b", "c", "d"]), "bronze", "users")
        write_parquet(batch(["e"]), "bronze", "users")

        v1_after = engine.query(
            "SELECT * FROM bronze_users", "bronze", "users", version=1
        )
        assert set(v1_after["id"].tolist()) == set(v1_result["id"].tolist())

    def test_latest_version_when_version_not_specified(self, engine, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")
        write_parquet(batch(["c"]), "bronze", "users")
        result = engine.query("SELECT * FROM bronze_users", "bronze", "users")
        assert set(result["id"].tolist()) == {"a", "b", "c"}


class TestQueryPartitionPruning:
    def test_partition_filter_returns_matching_rows(self, engine, writer_env):
        df1 = pd.DataFrame({"date": ["2025-01-01", "2025-01-01"], "val": [1, 2]})
        df2 = pd.DataFrame({"date": ["2025-01-02", "2025-01-02"], "val": [3, 4]})
        write_parquet(df1, "bronze", "events", partition_cols=["date"])
        write_parquet(df2, "bronze", "events", partition_cols=["date"])

        result = engine.query(
            "SELECT * FROM bronze_events",
            "bronze",
            "events",
            partition_filters={"date": "2025-01-01"},
        )
        # date column may come back as Timestamp; compare as string prefix
        dates = {str(d)[:10] for d in result["date"].tolist()}
        assert dates == {"2025-01-01"}

    def test_partition_filter_excludes_nonmatching_partitions(self, engine, writer_env):
        df1 = pd.DataFrame({"date": ["2025-01-01"], "val": [1]})
        df2 = pd.DataFrame({"date": ["2025-01-02"], "val": [2]})
        write_parquet(df1, "bronze", "events", partition_cols=["date"])
        write_parquet(df2, "bronze", "events", partition_cols=["date"])

        result = engine.query(
            "SELECT * FROM bronze_events",
            "bronze",
            "events",
            partition_filters={"date": "2025-01-01"},
        )
        assert len(result) == 1
        assert result["val"].iloc[0] == 1
        assert str(result["date"].iloc[0])[:10] == "2025-01-01"

    def test_unpartitioned_files_pass_through(self, engine, writer_env):
        # Write without partition_cols — no catalog_partitions records created
        # Querying with a partition filter should still return the data
        write_parquet(batch(["a", "b"]), "bronze", "users")
        result = engine.query(
            "SELECT * FROM bronze_users",
            "bronze",
            "users",
            partition_filters={"date": "2025-01-01"},
        )
        assert len(result) == 2


class TestQueryLogicalDeletes:
    def test_deleted_rows_excluded_from_query(self, engine, writer_env, tmp_path):
        # Write 3 rows
        write_parquet(batch(["a", "b", "c"]), "bronze", "users")

        # Get the file_id for the written file
        snap = writer_env.get_latest_snapshot("bronze.users")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        assert len(files) == 1
        data_file = files[0]

        # Write a delete file containing the row to remove (id="b", val=1)
        delete_path = str(tmp_path / "delete.parquet")
        pq.write_table(
            pa.table({"id": ["b"], "val": [1]}),
            delete_path,
        )

        # Register the delete file in the catalog
        writer_env.record_delete(
            table_id="bronze.users",
            snapshot_id=snap.snapshot_id,
            file_id=data_file.file_id,
            delete_file_path=delete_path,
            delete_count=1,
            byte_size=100,
        )

        result = engine.query("SELECT * FROM bronze_users", "bronze", "users")
        assert set(result["id"].tolist()) == {"a", "c"}
        assert "b" not in result["id"].tolist()

    def test_non_deleted_files_unaffected(self, engine, writer_env, tmp_path):
        # Two writes → two files; delete only from the first file
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d"]), "bronze", "users")

        # Get file_id for the first snapshot's file
        snaps = writer_env.list_snapshots("bronze.users")
        files_v1 = writer_env.get_snapshot_files(snaps[0].snapshot_id)
        data_file = files_v1[0]

        delete_path = str(tmp_path / "delete.parquet")
        pq.write_table(pa.table({"id": ["a"], "val": [0]}), delete_path)

        writer_env.record_delete(
            table_id="bronze.users",
            snapshot_id=snaps[0].snapshot_id,
            file_id=data_file.file_id,
            delete_file_path=delete_path,
            delete_count=1,
            byte_size=100,
        )

        result = engine.query("SELECT * FROM bronze_users", "bronze", "users")
        assert set(result["id"].tolist()) == {"b", "c", "d"}
        assert "a" not in result["id"].tolist()
