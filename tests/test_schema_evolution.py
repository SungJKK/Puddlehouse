import pytest
from tests.conftest import db_connect


# ── T2: Schema Evolution ──────────────────────────────────────────────────────

@pytest.fixture()
def table(catalog):
    """A registered table ready for column operations."""
    catalog.register_table("bronze", "users")
    return "bronze.users"


class TestRegisterColumns:
    def test_initial_registration_returns_name_id_map(self, catalog, table):
        schema = [{"name": "user_id", "type": "utf8"}, {"name": "email", "type": "utf8"}]
        col_map = catalog.register_columns(table, version=1, schema=schema)

        assert set(col_map.keys()) == {"user_id", "email"}
        assert all(isinstance(v, str) and len(v) == 36 for v in col_map.values())  # UUIDs

    def test_column_order_preserved(self, catalog, table):
        schema = [
            {"name": "a", "type": "int64"},
            {"name": "b", "type": "utf8"},
            {"name": "c", "type": "float64"},
        ]
        catalog.register_columns(table, version=1, schema=schema)
        cols = catalog.get_schema_at_version(table, version=1)

        assert [c.column_name for c in cols] == ["a", "b", "c"]
        assert [c.column_order for c in cols] == [0, 1, 2]

    def test_idempotent_no_duplicate_columns(self, catalog, table):
        schema = [{"name": "user_id", "type": "utf8"}]
        catalog.register_columns(table, version=1, schema=schema)
        catalog.register_columns(table, version=1, schema=schema)

        cols = catalog.get_schema_at_version(table, version=1)
        assert len(cols) == 1

    def test_new_column_added_in_later_version(self, catalog, table):
        v1_schema = [{"name": "user_id", "type": "utf8"}]
        v2_schema = [{"name": "user_id", "type": "utf8"}, {"name": "email", "type": "utf8"}]

        catalog.register_columns(table, version=1, schema=v1_schema)
        catalog.register_columns(table, version=2, schema=v2_schema)

        v1_cols = catalog.get_schema_at_version(table, version=1)
        v2_cols = catalog.get_schema_at_version(table, version=2)

        assert [c.column_name for c in v1_cols] == ["user_id"]
        assert {c.column_name for c in v2_cols} == {"user_id", "email"}

    def test_dropped_column_not_visible_after_its_version(self, catalog, table):
        v1_schema = [{"name": "user_id", "type": "utf8"}, {"name": "legacy", "type": "utf8"}]
        v2_schema = [{"name": "user_id", "type": "utf8"}]  # "legacy" removed

        catalog.register_columns(table, version=1, schema=v1_schema)
        catalog.register_columns(table, version=2, schema=v2_schema)

        v1_cols = {c.column_name for c in catalog.get_schema_at_version(table, version=1)}
        v2_cols = {c.column_name for c in catalog.get_schema_at_version(table, version=2)}

        assert "legacy" in v1_cols
        assert "legacy" not in v2_cols

    def test_dropped_column_has_dropped_at_version_set(self, catalog, table):
        v1_schema = [{"name": "user_id", "type": "utf8"}, {"name": "legacy", "type": "utf8"}]
        v2_schema = [{"name": "user_id", "type": "utf8"}]

        catalog.register_columns(table, version=1, schema=v1_schema)
        catalog.register_columns(table, version=2, schema=v2_schema)

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT dropped_at_version FROM catalog_columns "
            "WHERE table_id=? AND column_name='legacy'",
            (table,)
        ).fetchone()
        con.close()

        assert row is not None
        assert row[0] == 2

    def test_add_and_drop_in_sequence(self, catalog, table):
        catalog.register_columns(table, version=1, schema=[
            {"name": "id", "type": "int64"},
            {"name": "name", "type": "utf8"},
        ])
        catalog.register_columns(table, version=2, schema=[
            {"name": "id", "type": "int64"},
            {"name": "name", "type": "utf8"},
            {"name": "score", "type": "float64"},
        ])
        catalog.register_columns(table, version=3, schema=[
            {"name": "id", "type": "int64"},
            {"name": "score", "type": "float64"},  # "name" dropped
        ])

        assert {c.column_name for c in catalog.get_schema_at_version(table, 1)} == {"id", "name"}
        assert {c.column_name for c in catalog.get_schema_at_version(table, 2)} == {"id", "name", "score"}
        assert {c.column_name for c in catalog.get_schema_at_version(table, 3)} == {"id", "score"}


class TestGetSchemaAtVersion:
    def test_returns_empty_list_for_unknown_version(self, catalog, table):
        cols = catalog.get_schema_at_version(table, version=99)
        assert cols == []

    def test_column_added_at_v2_not_visible_at_v1(self, catalog, table):
        catalog.register_columns(table, version=1, schema=[{"name": "id", "type": "int64"}])
        catalog.register_columns(table, version=2, schema=[
            {"name": "id", "type": "int64"},
            {"name": "extra", "type": "utf8"},
        ])

        v1_names = {c.column_name for c in catalog.get_schema_at_version(table, 1)}
        assert "extra" not in v1_names

    def test_column_type_stored_correctly(self, catalog, table):
        catalog.register_columns(table, version=1, schema=[
            {"name": "amount", "type": "float64"},
        ])
        cols = catalog.get_schema_at_version(table, 1)

        assert cols[0].column_type == "float64"
