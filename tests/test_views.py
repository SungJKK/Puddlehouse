import time
import pytest
from tests.conftest import db_connect


# ── T6: Views ─────────────────────────────────────────────────────────────────

SQL = "SELECT user_id, COUNT(*) AS events FROM bronze.events GROUP BY user_id"


class TestRegisterView:
    def test_returns_valid_uuid(self, catalog):
        view_id = catalog.register_view("user_event_counts", "gold", "view", SQL)
        assert isinstance(view_id, str) and len(view_id) == 36

    def test_row_persisted_with_correct_fields(self, catalog):
        view_id = catalog.register_view("user_event_counts", "gold", "view", SQL, owner="analyst")

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT * FROM catalog_views WHERE view_id=?", (view_id,)
        ).fetchone()
        con.close()

        assert row is not None
        assert row["view_name"] == "user_event_counts"
        assert row["zone"] == "gold"
        assert row["view_type"] == "view"
        assert row["sql"] == SQL
        assert row["owner"] == "analyst"
        assert row["is_active"] == 1

    def test_materialized_view_type_stored(self, catalog):
        view_id = catalog.register_view("mv_daily_orders", "gold", "materialized_view", SQL)

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT view_type FROM catalog_views WHERE view_id=?", (view_id,)
        ).fetchone()
        con.close()

        assert row["view_type"] == "materialized_view"

    def test_default_owner_is_system(self, catalog):
        view_id = catalog.register_view("v_users", "silver", "view", SQL)

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT owner FROM catalog_views WHERE view_id=?", (view_id,)
        ).fetchone()
        con.close()

        assert row["owner"] == "system"

    def test_multiple_views_registered_independently(self, catalog):
        id1 = catalog.register_view("view_a", "gold", "view", SQL)
        id2 = catalog.register_view("view_b", "gold", "view", SQL)

        assert id1 != id2

        con = db_connect(catalog.catalog_path)
        count = con.execute("SELECT COUNT(*) FROM catalog_views").fetchone()[0]
        con.close()

        assert count == 2

    def test_refresh_fields_null_on_initial_register(self, catalog):
        view_id = catalog.register_view("mv_sales", "gold", "materialized_view", SQL)

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT last_refreshed_at, refresh_snapshot_id FROM catalog_views WHERE view_id=?",
            (view_id,)
        ).fetchone()
        con.close()

        assert row["last_refreshed_at"] is None
        assert row["refresh_snapshot_id"] is None


class TestRefreshMaterializedView:
    @pytest.fixture()
    def mv_and_snapshot(self, catalog):
        """A materialized view and a snapshot to point it at."""
        catalog.register_table("gold", "orders")
        snapshot_id, _, _ = catalog.create_snapshot(
            "gold.orders",
            files=[{"file_path": "/tmp/orders.parquet", "row_count": 50, "byte_size": 512}],
            row_count=50,
            byte_size=512,
        )
        view_id = catalog.register_view("mv_orders", "gold", "materialized_view", SQL)
        return {"view_id": view_id, "snapshot_id": snapshot_id}

    def test_refresh_sets_snapshot_id(self, catalog, mv_and_snapshot):
        catalog.refresh_materialized_view(
            mv_and_snapshot["view_id"], mv_and_snapshot["snapshot_id"]
        )

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT refresh_snapshot_id FROM catalog_views WHERE view_id=?",
            (mv_and_snapshot["view_id"],)
        ).fetchone()
        con.close()

        assert row["refresh_snapshot_id"] == mv_and_snapshot["snapshot_id"]

    def test_refresh_sets_last_refreshed_at(self, catalog, mv_and_snapshot):
        catalog.refresh_materialized_view(
            mv_and_snapshot["view_id"], mv_and_snapshot["snapshot_id"]
        )

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT last_refreshed_at FROM catalog_views WHERE view_id=?",
            (mv_and_snapshot["view_id"],)
        ).fetchone()
        con.close()

        assert row["last_refreshed_at"] is not None

    def test_refresh_updates_updated_at(self, catalog, mv_and_snapshot):
        con = db_connect(catalog.catalog_path)
        before = con.execute(
            "SELECT updated_at FROM catalog_views WHERE view_id=?",
            (mv_and_snapshot["view_id"],)
        ).fetchone()["updated_at"]
        con.close()

        time.sleep(0.05)
        catalog.refresh_materialized_view(
            mv_and_snapshot["view_id"], mv_and_snapshot["snapshot_id"]
        )

        con = db_connect(catalog.catalog_path)
        after = con.execute(
            "SELECT updated_at FROM catalog_views WHERE view_id=?",
            (mv_and_snapshot["view_id"],)
        ).fetchone()["updated_at"]
        con.close()

        assert after > before

    def test_second_refresh_overwrites_first(self, catalog):
        catalog.register_table("gold", "users")
        sid1, _, _ = catalog.create_snapshot(
            "gold.users",
            [{"file_path": "/tmp/u1.parquet", "row_count": 10, "byte_size": 100}],
            10, 100,
        )
        sid2, _, _ = catalog.create_snapshot(
            "gold.users",
            [{"file_path": "/tmp/u2.parquet", "row_count": 20, "byte_size": 200}],
            20, 200,
        )
        view_id = catalog.register_view("mv_users", "gold", "materialized_view", SQL)

        catalog.refresh_materialized_view(view_id, sid1)
        catalog.refresh_materialized_view(view_id, sid2)

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT refresh_snapshot_id FROM catalog_views WHERE view_id=?", (view_id,)
        ).fetchone()
        con.close()

        assert row["refresh_snapshot_id"] == sid2
