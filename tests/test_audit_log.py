import json
import pytest
from tests.conftest import db_connect


# ── T10: Audit Log ────────────────────────────────────────────────────────────

def audit_rows(catalog, operation=None):
    con = db_connect(catalog.catalog_path)
    if operation:
        rows = con.execute(
            "SELECT * FROM catalog_audit_log WHERE operation=?", (operation,)
        ).fetchall()
    else:
        rows = con.execute("SELECT * FROM catalog_audit_log").fetchall()
    con.close()
    return rows


class TestAuditLogRegister:
    def test_register_creates_audit_entry(self, catalog):
        catalog.register_table("bronze", "users")
        rows = audit_rows(catalog, "REGISTER")
        assert len(rows) == 1

    def test_register_entry_has_correct_table_id(self, catalog):
        catalog.register_table("bronze", "users")
        row = audit_rows(catalog, "REGISTER")[0]
        assert row["table_id"] == "bronze.users"

    def test_register_entry_has_valid_uuid_log_id(self, catalog):
        catalog.register_table("bronze", "users")
        row = audit_rows(catalog, "REGISTER")[0]
        assert len(row["log_id"]) == 36

    def test_re_register_appends_second_entry(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "users")
        rows = audit_rows(catalog, "REGISTER")
        assert len(rows) == 2


class TestAuditLogSnapshot:
    def test_snapshot_creates_audit_entry(self, catalog):
        catalog.register_table("bronze", "events")
        catalog.create_snapshot(
            "bronze.events",
            [{"file_path": "/tmp/f.parquet", "row_count": 10, "byte_size": 100}],
            10, 100,
        )
        rows = audit_rows(catalog, "SNAPSHOT")
        assert len(rows) == 1

    def test_snapshot_entry_details_contain_version_and_rows(self, catalog):
        catalog.register_table("bronze", "events")
        catalog.create_snapshot(
            "bronze.events",
            [{"file_path": "/tmp/f.parquet", "row_count": 42, "byte_size": 512}],
            42, 512,
        )
        row = audit_rows(catalog, "SNAPSHOT")[0]
        details = json.loads(row["details"])

        assert details["version"] == 1
        assert details["rows"] == 42

    def test_snapshot_entry_has_correct_table_id(self, catalog):
        catalog.register_table("bronze", "events")
        catalog.create_snapshot(
            "bronze.events",
            [{"file_path": "/tmp/f.parquet", "row_count": 10, "byte_size": 100}],
            10, 100,
        )
        row = audit_rows(catalog, "SNAPSHOT")[0]
        assert row["table_id"] == "bronze.events"


class TestAuditLogDelete:
    def test_delete_creates_audit_entry(self, catalog):
        catalog.register_table("bronze", "events")
        sid, _, fmap = catalog.create_snapshot(
            "bronze.events",
            [{"file_path": "/tmp/f.parquet", "row_count": 10, "byte_size": 100}],
            10, 100,
        )
        catalog.record_delete("bronze.events", sid, fmap["/tmp/f.parquet"], "/tmp/d.parquet", 3, 32)
        rows = audit_rows(catalog, "DELETE")
        assert len(rows) == 1

    def test_delete_entry_details_contain_file_and_count(self, catalog):
        catalog.register_table("bronze", "events")
        sid, _, fmap = catalog.create_snapshot(
            "bronze.events",
            [{"file_path": "/tmp/f.parquet", "row_count": 10, "byte_size": 100}],
            10, 100,
        )
        file_id = fmap["/tmp/f.parquet"]
        catalog.record_delete("bronze.events", sid, file_id, "/tmp/d.parquet", 5, 64)

        row = audit_rows(catalog, "DELETE")[0]
        details = json.loads(row["details"])

        assert details["file_id"] == file_id
        assert details["delete_count"] == 5


class TestAuditLogLineage:
    def test_lineage_creates_audit_entry(self, catalog):
        catalog.register_table("bronze", "events")
        catalog.register_table("silver", "events")
        catalog.record_lineage("bronze.events", "silver.events", "job", "r1", 100, 90)

        rows = audit_rows(catalog, "LINEAGE")
        assert len(rows) == 1

    def test_lineage_entry_details_contain_source_and_job(self, catalog):
        catalog.register_table("bronze", "events")
        catalog.register_table("silver", "events")
        catalog.record_lineage("bronze.events", "silver.events", "etl_job", "r1", 100, 90)

        row = audit_rows(catalog, "LINEAGE")[0]
        details = json.loads(row["details"])

        assert details["source"] == "bronze.events"
        assert details["job"] == "etl_job"

    def test_lineage_entry_table_id_is_target(self, catalog):
        catalog.register_table("bronze", "events")
        catalog.register_table("silver", "events")
        catalog.record_lineage("bronze.events", "silver.events", "job", "r1", 100, 90)

        row = audit_rows(catalog, "LINEAGE")[0]
        assert row["table_id"] == "silver.events"


class TestAuditLogView:
    def test_view_creates_audit_entry(self, catalog):
        catalog.register_view("v_users", "gold", "view", "SELECT 1")
        rows = audit_rows(catalog, "VIEW")
        assert len(rows) == 1

    def test_view_entry_details_contain_name_and_type(self, catalog):
        catalog.register_view("mv_orders", "gold", "materialized_view", "SELECT 1")
        row = audit_rows(catalog, "VIEW")[0]
        details = json.loads(row["details"])

        assert details["view_name"] == "mv_orders"
        assert details["view_type"] == "materialized_view"

    def test_view_entry_table_id_is_null(self, catalog):
        catalog.register_view("v_users", "gold", "view", "SELECT 1")
        row = audit_rows(catalog, "VIEW")[0]
        assert row["table_id"] is None


class TestAuditLogGeneral:
    def test_all_operations_accumulate_independently(self, catalog):
        catalog.register_table("bronze", "events")
        sid, _, fmap = catalog.create_snapshot(
            "bronze.events",
            [{"file_path": "/tmp/f.parquet", "row_count": 10, "byte_size": 100}],
            10, 100,
        )
        catalog.record_delete("bronze.events", sid, fmap["/tmp/f.parquet"], "/tmp/d.parquet", 1, 16)
        catalog.register_table("silver", "events")
        catalog.record_lineage("bronze.events", "silver.events", "job", "r1", 10, 9)
        catalog.register_view("v_events", "gold", "view", "SELECT 1")

        all_rows = audit_rows(catalog)
        ops = [r["operation"] for r in all_rows]

        assert ops.count("REGISTER") == 2
        assert ops.count("SNAPSHOT") == 1
        assert ops.count("DELETE") == 1
        assert ops.count("LINEAGE") == 1
        assert ops.count("VIEW") == 1
