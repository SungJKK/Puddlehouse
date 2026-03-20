import pytest
from tests.conftest import db_connect


# ── T9: Reads / Discovery ─────────────────────────────────────────────────────

class TestGetTable:
    def test_returns_none_for_unknown_table(self, catalog):
        assert catalog.get_table("bronze.nonexistent") is None

    def test_returns_table_meta_for_known_table(self, catalog):
        catalog.register_table("bronze", "users")
        tbl = catalog.get_table("bronze.users")

        assert tbl is not None
        assert tbl.table_id == "bronze.users"

    def test_returned_fields_match_registered_values(self, catalog):
        catalog.register_table("silver", "orders")
        tbl = catalog.get_table("silver.orders")

        assert tbl.zone == "silver"
        assert tbl.entity == "orders"
        assert tbl.name == "silver_orders"
        assert tbl.is_active == 1
        assert tbl.row_count == 0
        assert tbl.location is not None


class TestListTables:
    def test_returns_empty_when_no_tables(self, catalog):
        assert catalog.list_tables() == []

    def test_returns_all_active_tables(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "events")
        catalog.register_table("silver", "orders")

        tables = catalog.list_tables()
        assert len(tables) == 3

    def test_zone_filter_returns_only_matching_zone(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "events")
        catalog.register_table("silver", "orders")

        bronze = catalog.list_tables(zone="bronze")
        silver = catalog.list_tables(zone="silver")

        assert len(bronze) == 2
        assert all(t.zone == "bronze" for t in bronze)
        assert len(silver) == 1
        assert silver[0].zone == "silver"

    def test_zone_filter_returns_empty_for_unknown_zone(self, catalog):
        catalog.register_table("bronze", "users")
        assert catalog.list_tables(zone="gold") == []

    def test_inactive_tables_excluded(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "events")

        # soft-delete one table directly
        con = db_connect(catalog.catalog_path)
        con.execute("UPDATE catalog_tables SET is_active=0 WHERE table_id='bronze.events'")
        con.commit()
        con.close()

        tables = catalog.list_tables()
        assert len(tables) == 1
        assert tables[0].table_id == "bronze.users"

    def test_inactive_tables_excluded_with_zone_filter(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "events")

        con = db_connect(catalog.catalog_path)
        con.execute("UPDATE catalog_tables SET is_active=0 WHERE table_id='bronze.events'")
        con.commit()
        con.close()

        tables = catalog.list_tables(zone="bronze")
        assert len(tables) == 1
        assert tables[0].table_id == "bronze.users"

    def test_returns_table_meta_objects(self, catalog):
        from catalog.models import TableMeta
        catalog.register_table("bronze", "users")

        tables = catalog.list_tables()
        assert all(isinstance(t, TableMeta) for t in tables)
