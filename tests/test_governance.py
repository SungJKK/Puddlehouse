import pandas as pd
import pytest
from pathlib import Path

from storage.writer import write_parquet
from tests.conftest import db_connect


def batch(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"id": ids, "val": range(len(ids))})


# ── P5-1: Audit Log ───────────────────────────────────────────────────────────


class TestAuditLog:
    def test_returns_entries_after_write(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        entries = writer_env.get_audit_log("bronze.users")
        assert len(entries) > 0

    def test_entries_have_correct_fields(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        entry = writer_env.get_audit_log("bronze.users")[0]
        assert entry.log_id is not None
        assert entry.operation is not None
        assert entry.table_id == "bronze.users"

    def test_filter_by_table_id(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "orders")
        entries = writer_env.get_audit_log("bronze.users")
        assert all(e.table_id == "bronze.users" for e in entries if e.table_id)

    def test_returns_empty_for_unknown_table(self, writer_env):
        entries = writer_env.get_audit_log("bronze.ghost")
        assert entries == []

    def test_limit_is_respected(self, writer_env):
        for _ in range(5):
            write_parquet(batch(["a"]), "bronze", "users")
        entries = writer_env.get_audit_log("bronze.users", limit=2)
        assert len(entries) <= 2

    def test_global_audit_log_without_filter(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "orders")
        entries = writer_env.get_audit_log()
        assert len(entries) > 0

    def test_entries_ordered_newest_first(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")
        entries = writer_env.get_audit_log("bronze.users")
        timestamps = [e.created_at for e in entries if e.created_at]
        assert timestamps == sorted(timestamps, reverse=True)


# ── P5-2: Vacuum ──────────────────────────────────────────────────────────────


class TestVacuum:
    def test_dry_run_returns_paths_without_deleting(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")

        paths = writer_env.vacuum("bronze.users", retain_last_n=1, dry_run=True)
        assert len(paths) == 1
        assert Path(paths[0]).exists()  # file still on disk

    def test_vacuum_deletes_file_from_disk(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")

        paths = writer_env.vacuum("bronze.users", retain_last_n=1)
        assert len(paths) == 1
        assert not Path(paths[0]).exists()

    def test_vacuum_removes_catalog_files_entry(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")

        paths = writer_env.vacuum("bronze.users", retain_last_n=1)

        con = db_connect(writer_env.catalog_path)
        row = con.execute(
            "SELECT file_id FROM catalog_files WHERE file_path=?", (paths[0],)
        ).fetchone()
        con.close()
        assert row is None

    def test_vacuum_retains_recent_files(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")

        snap_v2 = writer_env.get_latest_snapshot("bronze.users")
        v2_files = writer_env.get_snapshot_files(snap_v2.snapshot_id)

        writer_env.vacuum("bronze.users", retain_last_n=1)

        # v2 file must still exist on disk
        for f in v2_files:
            assert Path(f.file_path).exists()

    def test_vacuum_returns_empty_when_nothing_to_expire(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        # Only 1 snapshot and retain_last_n=1 — nothing to delete
        paths = writer_env.vacuum("bronze.users", retain_last_n=1)
        assert paths == []

    def test_vacuum_returns_empty_for_table_with_no_snapshots(self, writer_env):
        writer_env.register_table("bronze", "empty")
        paths = writer_env.vacuum("bronze.empty", retain_last_n=1)
        assert paths == []

    def test_retain_last_2_keeps_two_snapshots(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")  # v1
        write_parquet(batch(["b"]), "bronze", "users")  # v2
        write_parquet(batch(["c"]), "bronze", "users")  # v3

        paths = writer_env.vacuum("bronze.users", retain_last_n=2)
        assert len(paths) == 1  # only v1 expired

        snap_v1_files = db_connect(writer_env.catalog_path).execute(
            "SELECT file_path FROM catalog_files cf "
            "JOIN catalog_snapshots cs ON cf.snapshot_id = cs.snapshot_id "
            "WHERE cs.table_id='bronze.users' AND cs.version=1"
        ).fetchall()
        for row in snap_v1_files:
            assert not Path(row["file_path"]).exists()

    def test_vacuum_logs_to_audit_trail(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        write_parquet(batch(["b"]), "bronze", "users")
        writer_env.vacuum("bronze.users", retain_last_n=1)

        entries = writer_env.get_audit_log("bronze.users")
        ops = [e.operation for e in entries]
        assert "VACUUM" in ops


# ── P5-3: Quality Contracts ───────────────────────────────────────────────────


class TestAddQualityContract:
    def test_returns_contract_id(self, writer_env):
        contract_id = writer_env.add_quality_contract(
            "bronze.users", "not_empty"
        )
        assert isinstance(contract_id, str) and len(contract_id) == 36

    def test_invalid_check_type_raises(self, writer_env):
        with pytest.raises(ValueError, match="Unknown check_type"):
            writer_env.add_quality_contract("bronze.users", "made_up_check")


class TestNotEmptyContract:
    def test_passes_when_table_has_rows(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        writer_env.add_quality_contract("bronze.users", "not_empty")
        results = writer_env.run_quality_checks("bronze.users")
        assert results[0]["passed"] is True

    def test_fails_when_table_is_empty(self, writer_env):
        # Register table but write 0 rows — simulate via snapshot with row_count=0
        writer_env.register_table("bronze", "users")
        con = db_connect(writer_env.catalog_path)
        import uuid
        con.execute(
            "INSERT INTO catalog_snapshots (snapshot_id, table_id, version, row_count) VALUES (?,?,?,?)",
            (str(uuid.uuid4()), "bronze.users", 1, 0)
        )
        con.commit()
        con.close()
        writer_env.add_quality_contract("bronze.users", "not_empty")
        results = writer_env.run_quality_checks("bronze.users")
        assert results[0]["passed"] is False

    def test_custom_min_rows(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")  # 1 row
        writer_env.add_quality_contract("bronze.users", "not_empty", {"min_rows": 5})
        results = writer_env.run_quality_checks("bronze.users")
        assert results[0]["passed"] is False


class TestFreshnessDaysContract:
    def test_passes_for_recent_write(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        writer_env.add_quality_contract("bronze.users", "freshness_days", {"max_days": 7})
        results = writer_env.run_quality_checks("bronze.users")
        assert results[0]["passed"] is True

    def test_fails_for_stale_snapshot(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        # Backdate the snapshot to simulate staleness
        con = db_connect(writer_env.catalog_path)
        con.execute(
            "UPDATE catalog_snapshots SET created_at='2020-01-01 00:00:00' "
            "WHERE table_id='bronze.users'"
        )
        con.commit()
        con.close()
        writer_env.add_quality_contract("bronze.users", "freshness_days", {"max_days": 7})
        results = writer_env.run_quality_checks("bronze.users")
        assert results[0]["passed"] is False

    def test_details_include_age_and_max(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        writer_env.add_quality_contract("bronze.users", "freshness_days", {"max_days": 30})
        results = writer_env.run_quality_checks("bronze.users")
        assert "age_days" in results[0]["details"]
        assert "max_days" in results[0]["details"]


class TestMaxNullFractionContract:
    def test_passes_when_no_nulls(self, writer_env):
        write_parquet(pd.DataFrame({"id": ["a", "b"], "val": [1, 2]}), "bronze", "users")
        writer_env.add_quality_contract(
            "bronze.users", "max_null_fraction", {"column": "id", "max_fraction": 0.0}
        )
        results = writer_env.run_quality_checks("bronze.users")
        assert results[0]["passed"] is True

    def test_fails_for_unknown_column(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        writer_env.add_quality_contract(
            "bronze.users", "max_null_fraction", {"column": "nonexistent", "max_fraction": 0.1}
        )
        results = writer_env.run_quality_checks("bronze.users")
        assert results[0]["passed"] is False
        assert "not found" in results[0]["details"]


class TestRunQualityChecks:
    def test_returns_empty_when_no_contracts(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        results = writer_env.run_quality_checks("bronze.users")
        assert results == []

    def test_multiple_contracts_all_evaluated(self, writer_env):
        write_parquet(batch(["a", "b"]), "bronze", "users")
        writer_env.add_quality_contract("bronze.users", "not_empty")
        writer_env.add_quality_contract("bronze.users", "freshness_days", {"max_days": 7})
        results = writer_env.run_quality_checks("bronze.users")
        assert len(results) == 2

    def test_result_has_required_keys(self, writer_env):
        write_parquet(batch(["a"]), "bronze", "users")
        writer_env.add_quality_contract("bronze.users", "not_empty")
        result = writer_env.run_quality_checks("bronze.users")[0]
        assert "contract_id" in result
        assert "check_type" in result
        assert "passed" in result
        assert "details" in result
