import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from storage.writer import _read_file_stats


# ── T11: _read_file_stats ─────────────────────────────────────────────────────

def write_parquet_file(path, table: pa.Table, row_group_size: int = None):
    kwargs = {"compression": "snappy"}
    if row_group_size:
        kwargs["row_group_size"] = row_group_size
    pq.write_table(table, str(path), **kwargs)
    return str(path)


class TestReadFileStats:
    def test_returns_one_entry_per_column(self, tmp_path):
        table = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"], "c": [1.0, 2.0, 3.0]})
        path = write_parquet_file(tmp_path / "f.parquet", table)

        stats = _read_file_stats(path)
        assert len(stats) == 3
        assert {s["column_name"] for s in stats} == {"a", "b", "c"}

    def test_value_count_equals_row_count(self, tmp_path):
        table = pa.table({"amount": [10, 20, 30, 40, 50]})
        path = write_parquet_file(tmp_path / "f.parquet", table)

        stats = _read_file_stats(path)
        assert stats[0]["value_count"] == 5

    def test_null_count_reflects_actual_nulls(self, tmp_path):
        table = pa.table({"score": pa.array([1.0, None, 3.0, None, 5.0], type=pa.float64())})
        path = write_parquet_file(tmp_path / "f.parquet", table)

        stats = _read_file_stats(path)
        assert stats[0]["null_count"] == 2

    def test_zero_nulls_when_no_nulls(self, tmp_path):
        table = pa.table({"id": [1, 2, 3]})
        path = write_parquet_file(tmp_path / "f.parquet", table)

        stats = _read_file_stats(path)
        assert stats[0]["null_count"] == 0

    def test_min_max_values_as_strings(self, tmp_path):
        table = pa.table({"price": pa.array([5, 1, 9, 3], type=pa.int64())})
        path = write_parquet_file(tmp_path / "f.parquet", table)

        stats = _read_file_stats(path)
        s = stats[0]
        assert s["min_value"] == "1"
        assert s["max_value"] == "9"

    def test_column_size_bytes_is_positive(self, tmp_path):
        table = pa.table({"name": ["alice", "bob", "carol"]})
        path = write_parquet_file(tmp_path / "f.parquet", table)

        stats = _read_file_stats(path)
        assert stats[0]["column_size_bytes"] > 0

    def test_all_null_column_has_no_min_max(self, tmp_path):
        table = pa.table({"x": pa.array([None, None, None], type=pa.float64())})
        path = write_parquet_file(tmp_path / "f.parquet", table)

        stats = _read_file_stats(path)
        assert stats[0]["min_value"] is None
        assert stats[0]["max_value"] is None

    def test_stats_aggregated_across_multiple_row_groups(self, tmp_path):
        # Force 2 row groups of 3 rows each
        table = pa.table({"val": pa.array([10, 20, 30, 1, 5, 99], type=pa.int64())})
        path = write_parquet_file(tmp_path / "f.parquet", table, row_group_size=3)

        pf = pq.ParquetFile(str(path))
        assert pf.metadata.num_row_groups == 2

        stats = _read_file_stats(str(path))
        s = stats[0]

        assert s["value_count"] == 6
        assert s["min_value"] == "1"
        assert s["max_value"] == "99"

    def test_null_count_aggregated_across_multiple_row_groups(self, tmp_path):
        table = pa.table({
            "v": pa.array([1.0, None, 3.0, None, None, 6.0], type=pa.float64())
        })
        path = write_parquet_file(tmp_path / "f.parquet", table, row_group_size=3)

        stats = _read_file_stats(str(path))
        assert stats[0]["null_count"] == 3
