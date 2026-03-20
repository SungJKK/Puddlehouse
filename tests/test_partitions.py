import hashlib
import pytest
from tests.conftest import db_connect


# ── T8: Partitions ────────────────────────────────────────────────────────────

@pytest.fixture()
def table(catalog):
    catalog.register_table("bronze", "events")
    return "bronze.events"


class TestRegisterPartition:
    def test_row_persisted_with_correct_fields(self, catalog, table):
        catalog.register_partition(table, "date", "2025-01-01", "/tmp/events/date=2025-01-01/f.parquet", 500)

        con = db_connect(catalog.catalog_path)
        row = con.execute("SELECT * FROM catalog_partitions WHERE table_id=?", (table,)).fetchone()
        con.close()

        assert row is not None
        assert row["table_id"] == table
        assert row["partition_key"] == "date"
        assert row["partition_val"] == "2025-01-01"
        assert row["file_path"] == "/tmp/events/date=2025-01-01/f.parquet"
        assert row["row_count"] == 500

    def test_partition_id_is_deterministic_md5(self, catalog, table):
        file_path = "/tmp/events/date=2025-01-01/f.parquet"
        catalog.register_partition(table, "date", "2025-01-01", file_path, 500)

        expected_id = hashlib.md5(f"{table}date2025-01-01{file_path}".encode()).hexdigest()

        con = db_connect(catalog.catalog_path)
        row = con.execute("SELECT partition_id FROM catalog_partitions WHERE table_id=?", (table,)).fetchone()
        con.close()

        assert row["partition_id"] == expected_id

    def test_idempotent_no_duplicate_on_repeat_call(self, catalog, table):
        args = (table, "date", "2025-01-01", "/tmp/events/date=2025-01-01/f.parquet", 500)
        catalog.register_partition(*args)
        catalog.register_partition(*args)

        con = db_connect(catalog.catalog_path)
        count = con.execute("SELECT COUNT(*) FROM catalog_partitions WHERE table_id=?", (table,)).fetchone()[0]
        con.close()

        assert count == 1

    def test_upsert_updates_row_count_on_repeat(self, catalog, table):
        args = (table, "date", "2025-01-01", "/tmp/events/date=2025-01-01/f.parquet")
        catalog.register_partition(*args, 100)
        catalog.register_partition(*args, 200)

        con = db_connect(catalog.catalog_path)
        row = con.execute("SELECT row_count FROM catalog_partitions WHERE table_id=?", (table,)).fetchone()
        con.close()

        assert row["row_count"] == 200

    def test_different_partition_vals_create_separate_rows(self, catalog, table):
        catalog.register_partition(table, "date", "2025-01-01", "/tmp/p1.parquet", 100)
        catalog.register_partition(table, "date", "2025-01-02", "/tmp/p2.parquet", 150)
        catalog.register_partition(table, "date", "2025-01-03", "/tmp/p3.parquet", 200)

        con = db_connect(catalog.catalog_path)
        count = con.execute("SELECT COUNT(*) FROM catalog_partitions WHERE table_id=?", (table,)).fetchone()[0]
        con.close()

        assert count == 3

    def test_different_partition_keys_create_separate_rows(self, catalog, table):
        catalog.register_partition(table, "date",   "2025-01-01", "/tmp/by_date.parquet",   100)
        catalog.register_partition(table, "country", "US",         "/tmp/by_country.parquet", 80)

        con = db_connect(catalog.catalog_path)
        count = con.execute("SELECT COUNT(*) FROM catalog_partitions WHERE table_id=?", (table,)).fetchone()[0]
        con.close()

        assert count == 2

    def test_created_at_is_populated(self, catalog, table):
        catalog.register_partition(table, "date", "2025-01-01", "/tmp/f.parquet", 10)

        con = db_connect(catalog.catalog_path)
        row = con.execute("SELECT created_at FROM catalog_partitions WHERE table_id=?", (table,)).fetchone()
        con.close()

        assert row["created_at"] is not None
