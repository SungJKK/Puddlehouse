import time
from tests.conftest import db_connect


# ── T1: Table Registration ────────────────────────────────────────────────────

class TestRegisterTable:
    def test_returns_correct_table_id(self, catalog):
        table_id = catalog.register_table("bronze", "users")
        assert table_id == "bronze.users"

    def test_row_has_correct_fields(self, catalog, tmp_path):
        catalog.register_table("silver", "orders")
        tbl = catalog.get_table("silver.orders")

        assert tbl is not None
        assert tbl.table_id == "silver.orders"
        assert tbl.zone == "silver"
        assert tbl.entity == "orders"
        assert tbl.is_active == 1
        assert tbl.row_count == 0

    def test_location_contains_zone_and_entity(self, catalog):
        catalog.register_table("gold", "events")
        tbl = catalog.get_table("gold.events")

        assert "gold" in tbl.location
        assert "events" in tbl.location

    def test_idempotent_no_duplicate_row(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "users")

        con = db_connect(catalog.catalog_path)
        count = con.execute(
            "SELECT COUNT(*) FROM catalog_tables WHERE table_id='bronze.users'"
        ).fetchone()[0]
        con.close()

        assert count == 1

    def test_re_register_touches_updated_at(self, catalog):
        catalog.register_table("bronze", "users")
        before = catalog.get_table("bronze.users").updated_at

        time.sleep(0.05)
        catalog.register_table("bronze", "users")
        after = catalog.get_table("bronze.users").updated_at

        assert after > before

    def test_multiple_distinct_tables_coexist(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "orders")
        catalog.register_table("silver", "users")

        con = db_connect(catalog.catalog_path)
        count = con.execute("SELECT COUNT(*) FROM catalog_tables").fetchone()[0]
        con.close()

        assert count == 3
