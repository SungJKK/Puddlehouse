import pandas as pd
import pytest

from storage.writer import write_parquet, read_parquet


# ── T15: read_parquet ─────────────────────────────────────────────────────────

def events_df():
    return pd.DataFrame([
        {"event_id": "e1", "date": "2025-01-01", "amount": 10.0},
        {"event_id": "e2", "date": "2025-01-01", "amount": 20.0},
        {"event_id": "e3", "date": "2025-01-02", "amount": 30.0},
        {"event_id": "e4", "date": "2025-01-03", "amount": 40.0},
    ])


class TestReadParquet:
    def test_raises_file_not_found_for_missing_path(self, writer_env):
        with pytest.raises(FileNotFoundError):
            read_parquet("bronze", "nonexistent")

    def test_returns_dataframe(self, writer_env):
        write_parquet(events_df(), "bronze", "events")
        result = read_parquet("bronze", "events")
        assert isinstance(result, pd.DataFrame)

    def test_row_count_matches_written_data(self, writer_env):
        write_parquet(events_df(), "bronze", "events")
        result = read_parquet("bronze", "events")
        assert len(result) == 4

    def test_columns_match_written_schema(self, writer_env):
        write_parquet(events_df(), "bronze", "events")
        result = read_parquet("bronze", "events")
        assert set(result.columns) >= {"event_id", "date", "amount"}

    def test_data_values_round_trip_correctly(self, writer_env):
        write_parquet(events_df(), "bronze", "events")
        result = read_parquet("bronze", "events")
        assert set(result["event_id"].tolist()) == {"e1", "e2", "e3", "e4"}

    def test_multiple_writes_all_read_back(self, writer_env):
        write_parquet(events_df(), "bronze", "events")
        write_parquet(events_df(), "bronze", "events")
        result = read_parquet("bronze", "events")
        assert len(result) == 8

    def test_filter_applied_to_partitioned_data(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        result = read_parquet("bronze", "events", filters=[("date", "=", "2025-01-01")])
        assert len(result) == 2
        assert set(result["date"].tolist()) == {"2025-01-01"}

    def test_filter_excludes_non_matching_rows(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        result = read_parquet("bronze", "events", filters=[("date", "=", "2025-01-03")])
        assert len(result) == 1
        assert result["event_id"].iloc[0] == "e4"

    def test_filter_returning_no_rows_gives_empty_dataframe(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        result = read_parquet("bronze", "events", filters=[("date", "=", "1999-01-01")])
        assert len(result) == 0

    def test_no_filter_reads_all_partitions(self, writer_env):
        write_parquet(events_df(), "bronze", "events", partition_cols=["date"])
        result = read_parquet("bronze", "events")
        assert len(result) == 4
