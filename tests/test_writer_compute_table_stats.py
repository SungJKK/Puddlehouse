import pyarrow as pa
import pytest

from storage.writer import _compute_table_stats


# ── T12: _compute_table_stats ─────────────────────────────────────────────────

COL_MAP = {
    "amount":  "uuid-amount",
    "user_id": "uuid-user",
    "score":   "uuid-score",
}


class TestComputeTableStats:
    def test_returns_one_entry_per_mapped_column(self):
        table = pa.table({"amount": [1, 2, 3], "user_id": ["a", "b", "c"]})
        col_map = {"amount": "uuid-amount", "user_id": "uuid-user"}

        result = _compute_table_stats(table, col_map)
        assert len(result) == 2

    def test_column_id_taken_from_map(self):
        table = pa.table({"amount": [1, 2, 3]})
        result = _compute_table_stats(table, {"amount": "uuid-amount"})

        assert result[0]["column_id"] == "uuid-amount"

    def test_unmapped_columns_excluded(self):
        table = pa.table({"amount": [1, 2, 3], "ignored": [4, 5, 6]})
        result = _compute_table_stats(table, {"amount": "uuid-amount"})

        assert len(result) == 1
        assert result[0]["column_id"] == "uuid-amount"

    def test_empty_col_map_returns_empty_list(self):
        table = pa.table({"amount": [1, 2, 3]})
        assert _compute_table_stats(table, {}) == []

    def test_null_count_zero_when_no_nulls(self):
        table = pa.table({"amount": pa.array([1, 2, 3], type=pa.int64())})
        result = _compute_table_stats(table, {"amount": "uuid-amount"})

        assert result[0]["null_count"] == 0

    def test_null_count_reflects_actual_nulls(self):
        table = pa.table({"score": pa.array([1.0, None, 3.0, None], type=pa.float64())})
        result = _compute_table_stats(table, {"score": "uuid-score"})

        assert result[0]["null_count"] == 2

    def test_min_max_correct_for_integers(self):
        table = pa.table({"amount": pa.array([5, 1, 9, 3], type=pa.int64())})
        result = _compute_table_stats(table, {"amount": "uuid-amount"})

        assert result[0]["min_value"] == "1"
        assert result[0]["max_value"] == "9"

    def test_min_max_correct_for_strings(self):
        table = pa.table({"user_id": pa.array(["charlie", "alice", "bob"])})
        result = _compute_table_stats(table, {"user_id": "uuid-user"})

        assert result[0]["min_value"] == "alice"
        assert result[0]["max_value"] == "charlie"

    def test_min_max_none_for_all_null_column(self):
        table = pa.table({"score": pa.array([None, None, None], type=pa.float64())})
        result = _compute_table_stats(table, {"score": "uuid-score"})

        assert result[0]["min_value"] is None
        assert result[0]["max_value"] is None

    def test_min_max_none_for_empty_table(self):
        table = pa.table({"amount": pa.array([], type=pa.int64())})
        result = _compute_table_stats(table, {"amount": "uuid-amount"})

        assert result[0]["min_value"] is None
        assert result[0]["max_value"] is None

    def test_multiple_columns_computed_independently(self):
        table = pa.table({
            "amount":  pa.array([10, 20, 30], type=pa.int64()),
            "user_id": pa.array(["b", "a", "c"]),
        })
        col_map = {"amount": "uuid-amount", "user_id": "uuid-user"}
        result = {r["column_id"]: r for r in _compute_table_stats(table, col_map)}

        assert result["uuid-amount"]["min_value"] == "10"
        assert result["uuid-amount"]["max_value"] == "30"
        assert result["uuid-user"]["min_value"] == "a"
        assert result["uuid-user"]["max_value"] == "c"
