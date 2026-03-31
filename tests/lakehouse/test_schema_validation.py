import pandas as pd
import pytest

from catalog.manager import SchemaEvolutionError
from storage.writer import write_parquet


# ── P4-3: Schema Evolution Validation ────────────────────────────────────────


def make_df(**cols) -> pd.DataFrame:
    """Helper: create a one-row DataFrame with given column name → value."""
    return pd.DataFrame({k: [v] for k, v in cols.items()})


class TestFirstWrite:
    def test_first_write_always_succeeds(self, writer_env):
        # Any schema is valid on first write — nothing to validate against
        df = make_df(id="a", val=1, score=0.5)
        write_parquet(df, "bronze", "users")  # must not raise

    def test_second_write_with_same_schema_succeeds(self, writer_env):
        df = make_df(id="a", val=1)
        write_parquet(df, "bronze", "users")
        write_parquet(make_df(id="b", val=2), "bronze", "users")  # must not raise


class TestAllowedEvolution:
    def test_add_new_column_is_allowed(self, writer_env):
        write_parquet(make_df(id="a", val=1), "bronze", "users")
        # Add 'score' column — valid evolution
        write_parquet(make_df(id="b", val=2, score=0.9), "bronze", "users")

    def test_add_multiple_columns_is_allowed(self, writer_env):
        write_parquet(make_df(id="a"), "bronze", "users")
        write_parquet(make_df(id="b", val=1, score=0.5, flag=True), "bronze", "users")

    def test_different_tables_are_validated_independently(self, writer_env):
        write_parquet(make_df(id="a", val=1), "bronze", "users")
        write_parquet(make_df(id="a", val=1), "bronze", "orders")
        # Removing 'val' from users should fail, but orders is independent
        with pytest.raises(SchemaEvolutionError):
            write_parquet(make_df(id="b"), "bronze", "users")
        # orders still writable without val
        write_parquet(make_df(id="b", val=2), "bronze", "orders")


class TestDisallowedEvolution:
    def test_remove_column_raises(self, writer_env):
        write_parquet(make_df(id="a", val=1), "bronze", "users")
        with pytest.raises(SchemaEvolutionError, match="was removed"):
            write_parquet(make_df(id="b"), "bronze", "users")

    def test_remove_column_error_names_the_column(self, writer_env):
        write_parquet(make_df(id="a", val=1), "bronze", "users")
        with pytest.raises(SchemaEvolutionError, match="val"):
            write_parquet(make_df(id="b"), "bronze", "users")

    def test_remove_multiple_columns_lists_all_in_error(self, writer_env):
        write_parquet(make_df(id="a", val=1, score=0.5), "bronze", "users")
        with pytest.raises(SchemaEvolutionError) as exc_info:
            write_parquet(make_df(id="b"), "bronze", "users")
        msg = str(exc_info.value)
        assert "val" in msg
        assert "score" in msg

    def test_type_change_raises(self, writer_env):
        df1 = pd.DataFrame({"id": ["a"], "val": [1]})       # val: int64
        df2 = pd.DataFrame({"id": ["b"], "val": [1.5]})     # val: float64
        write_parquet(df1, "bronze", "users")
        with pytest.raises(SchemaEvolutionError, match="type changed"):
            write_parquet(df2, "bronze", "users")

    def test_type_change_error_names_the_column(self, writer_env):
        df1 = pd.DataFrame({"id": ["a"], "val": [1]})
        df2 = pd.DataFrame({"id": ["b"], "val": [1.5]})
        write_parquet(df1, "bronze", "users")
        with pytest.raises(SchemaEvolutionError, match="val"):
            write_parquet(df2, "bronze", "users")

    def test_rename_raises_as_remove_and_add(self, writer_env):
        write_parquet(make_df(id="a", val=1), "bronze", "users")
        # Renaming 'val' → 'value' looks like removing 'val' and adding 'value'
        with pytest.raises(SchemaEvolutionError, match="was removed"):
            write_parquet(make_df(id="b", value=2), "bronze", "users")


class TestErrorGranularity:
    def test_each_removed_column_is_a_separate_error(self, writer_env):
        write_parquet(make_df(id="a", val=1, score=0.5), "bronze", "users")
        with pytest.raises(SchemaEvolutionError) as exc_info:
            write_parquet(make_df(id="b"), "bronze", "users")
        errors = exc_info.value.errors
        assert len(errors) == 2
        assert any("val" in e for e in errors)
        assert any("score" in e for e in errors)

    def test_all_violations_reported_in_one_raise(self, writer_env):
        # Remove one column AND change a type — both should appear
        df1 = pd.DataFrame({"id": ["a"], "val": [1], "score": [0.5]})
        df2 = pd.DataFrame({"id": ["b"], "val": [1.5]})   # score removed, val type changed
        write_parquet(df1, "bronze", "users")
        with pytest.raises(SchemaEvolutionError) as exc_info:
            write_parquet(df2, "bronze", "users")
        errors = exc_info.value.errors
        assert any("score" in e and "removed" in e for e in errors)
        assert any("val" in e and "type changed" in e for e in errors)


class TestValidationDoesNotBlockCompaction:
    def test_compact_bypasses_schema_validation(self, writer_env):
        from storage.writer import compact
        write_parquet(make_df(id="a", val=1), "bronze", "users")
        write_parquet(make_df(id="b", val=2), "bronze", "users")
        # compact re-writes existing data with same schema — must not raise
        compact("bronze", "users")
