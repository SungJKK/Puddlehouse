import pandas as pd
import pytest
from pathlib import Path

from storage.writer import write_parquet, compact, read_parquet_at_version
from tests.conftest import db_connect


# ── P2-6: Compaction ──────────────────────────────────────────────────────────

def batch(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"id": ids, "val": range(len(ids))})


class TestCompactErrors:
    def test_raises_when_no_snapshots(self, writer_env):
        with pytest.raises(ValueError, match="No snapshots"):
            compact("bronze", "users")

    def test_raises_for_unregistered_table(self, writer_env):
        with pytest.raises(ValueError):
            compact("bronze", "nonexistent")


class TestCompactOutput:
    def test_returns_file_path_string(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        result = compact("bronze", "users")
        assert isinstance(result, str)

    def test_compacted_file_exists_on_disk(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        path = compact("bronze", "users")
        assert Path(path).exists()

    def test_compacted_filename_contains_compacted(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        path = compact("bronze", "users")
        assert "compacted" in Path(path).name


class TestCompactSnapshot:
    def test_creates_new_snapshot(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")

        snaps_before = writer_env.list_snapshots("bronze.users")
        compact("bronze", "users")
        snaps_after = writer_env.list_snapshots("bronze.users")

        assert len(snaps_after) == len(snaps_before) + 1

    def test_new_snapshot_is_latest(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")
        compact("bronze", "users")

        snap = writer_env.get_latest_snapshot("bronze.users")
        assert snap.version == 3

    def test_compacted_snapshot_has_single_file(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")
        write_parquet(batch(["c"]), "bronze", "users")

        compact("bronze", "users")

        snap  = writer_env.get_latest_snapshot("bronze.users")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        assert len(files) == 1

    def test_compacted_snapshot_row_count_equals_total(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d", "e"]), "bronze", "users")
        compact("bronze", "users")

        snap = writer_env.get_latest_snapshot("bronze.users")
        assert snap.row_count == 5

    def test_compacted_file_registered_in_catalog_files(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        compacted_path = compact("bronze", "users")

        snap  = writer_env.get_latest_snapshot("bronze.users")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        assert files[0].file_path == compacted_path

    def test_lineage_job_name_is_compact(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        compact("bronze", "users")

        con = db_connect(writer_env.catalog_path)
        row = con.execute(
            "SELECT job_name FROM catalog_lineage WHERE job_name='compact'"
        ).fetchone()
        con.close()
        assert row is not None


class TestCompactPreservesData:
    def test_compacted_snapshot_contains_all_rows(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d"]), "bronze", "users")
        compact("bronze", "users")

        snap = writer_env.get_latest_snapshot("bronze.users")
        df   = read_parquet_at_version("bronze", "users", snap.version)
        assert set(df["id"].tolist()) == {"a", "b", "c", "d"}

    def test_old_snapshots_still_readable_after_compact(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c", "d"]), "bronze", "users")
        compact("bronze", "users")

        v1 = read_parquet_at_version("bronze", "users", 1)
        v2 = read_parquet_at_version("bronze", "users", 2)

        # Cumulative semantics: v1 = first batch, v2 = first + second batch
        assert set(v1["id"].tolist()) == {"a", "b"}
        assert set(v2["id"].tolist()) == {"a", "b", "c", "d"}

    def test_old_files_still_on_disk_after_compact(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        snap_v1 = writer_env.get_latest_snapshot("bronze.users")
        v1_files = writer_env.get_snapshot_files(snap_v1.snapshot_id)

        compact("bronze", "users")

        for f in v1_files:
            assert Path(f.file_path).exists()

    def test_compact_then_compact_again(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        write_parquet(batch(["c"]), "bronze", "users")
        compact("bronze", "users")
        compact("bronze", "users")

        snap  = writer_env.get_latest_snapshot("bronze.users")
        files = writer_env.get_snapshot_files(snap.snapshot_id)
        df    = read_parquet_at_version("bronze", "users", snap.version)

        assert len(files) == 1
        assert set(df["id"].tolist()) == {"a", "b", "c"}
