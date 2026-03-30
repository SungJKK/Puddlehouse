import pyarrow as pa
import pytest

from storage.writer import _compute_table_stats


# ── T12: _compute_table_stats ─────────────────────────────────────────────────

class TestComputeTableStats:
    def test_returns_one_entry_per_column(self):
        table = pa.table({"amount": [1, 2, 3], "user_id": ["a", "b", "c"]})
        result = _compute_table_stats(table)
        assert len(result) == 2

    def test_column_name_in_result(self):
        table = pa.table({"amount": [1, 2, 3]})
        result = _compute_table_stats(table)
        assert result[0]["column_name"] == "amount"

    def test_all_columns_included(self):
        table = pa.table({"a": [1], "b": ["x"], "c": [1.0]})
        names = {r["column_name"] for r in _compute_table_stats(table)}
        assert names == {"a", "b", "c"}

    def test_empty_table_returns_empty_list(self):
        table = pa.table({})
        assert _compute_table_stats(table) == []

    def test_null_count_zero_when_no_nulls(self):
        table = pa.table({"amount": pa.array([1, 2, 3], type=pa.int64())})
        result = _compute_table_stats(table)
        assert result[0]["null_count"] == 0

    def test_null_count_reflects_actual_nulls(self):
        table = pa.table({"score": pa.array([1.0, None, 3.0, None], type=pa.float64())})
        result = _compute_table_stats(table)
        assert result[0]["null_count"] == 2

    def test_min_max_correct_for_integers(self):
        table = pa.table({"amount": pa.array([5, 1, 9, 3], type=pa.int64())})
        result = _compute_table_stats(table)
        assert result[0]["min_value"] == "1"
        assert result[0]["max_value"] == "9"

    def test_min_max_correct_for_strings(self):
        table = pa.table({"user_id": pa.array(["charlie", "alice", "bob"])})
        result = _compute_table_stats(table)
        assert result[0]["min_value"] == "alice"
        assert result[0]["max_value"] == "charlie"

    def test_min_max_none_for_all_null_column(self):
        table = pa.table({"score": pa.array([None, None, None], type=pa.float64())})
        result = _compute_table_stats(table)
        assert result[0]["min_value"] is None
        assert result[0]["max_value"] is None

    def test_min_max_none_for_empty_column(self):
        table = pa.table({"amount": pa.array([], type=pa.int64())})
        result = _compute_table_stats(table)
        assert result[0]["min_value"] is None
        assert result[0]["max_value"] is None

    def test_multiple_columns_computed_independently(self):
        table = pa.table({
            "amount":  pa.array([10, 20, 30], type=pa.int64()),
            "user_id": pa.array(["b", "a", "c"]),
        })
        result = {r["column_name"]: r for r in _compute_table_stats(table)}

        assert result["amount"]["min_value"] == "10"
        assert result["amount"]["max_value"] == "30"
        assert result["user_id"]["min_value"] == "a"
        assert result["user_id"]["max_value"] == "c"
