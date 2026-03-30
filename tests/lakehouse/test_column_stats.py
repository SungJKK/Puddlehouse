import pytest
from tests.conftest import db_connect


# ── T5: Column Stats ──────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(catalog):
    """Table with one snapshot, two columns, and the file_id + column_ids ready to use."""
    catalog.register_table("bronze", "events")
    table_id = "bronze.events"

    snapshot_id, version, file_id_map = catalog.create_snapshot(
        table_id,
        files=[{"file_path": "/tmp/events.parquet", "row_count": 100, "byte_size": 1024}],
        row_count=100,
        byte_size=1024,
    )
    col_map = catalog.register_columns(table_id, version, [
        {"name": "amount", "type": "float64"},
        {"name": "user_id", "type": "utf8"},
    ])
    file_id = file_id_map["/tmp/events.parquet"]

    return {
        "table_id": table_id,
        "snapshot_id": snapshot_id,
        "file_id": file_id,
        "col_map": col_map,      # {"amount": uuid, "user_id": uuid}
    }


class TestWriteFileColumnStats:
    def test_rows_persisted_for_each_column(self, catalog, seeded):
        stats = [
            {"column_id": seeded["col_map"]["amount"],  "value_count": 100, "null_count": 2,
             "min_value": "0.5", "max_value": "499.9", "column_size_bytes": 400},
            {"column_id": seeded["col_map"]["user_id"], "value_count": 100, "null_count": 0,
             "min_value": "aaa", "max_value": "zzz",   "column_size_bytes": 800},
        ]
        catalog.write_file_column_stats(seeded["file_id"], seeded["table_id"], stats)

        con = db_connect(catalog.catalog_path)
        rows = con.execute(
            "SELECT * FROM catalog_file_column_stats WHERE file_id=?",
            (seeded["file_id"],)
        ).fetchall()
        con.close()

        assert len(rows) == 2

    def test_correct_values_stored(self, catalog, seeded):
        col_id = seeded["col_map"]["amount"]
        catalog.write_file_column_stats(seeded["file_id"], seeded["table_id"], [
            {"column_id": col_id, "value_count": 50, "null_count": 5,
             "min_value": "1.0", "max_value": "9.9", "column_size_bytes": 200},
        ])

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT * FROM catalog_file_column_stats WHERE file_id=? AND column_id=?",
            (seeded["file_id"], col_id)
        ).fetchone()
        con.close()

        assert row["value_count"] == 50
        assert row["null_count"] == 5
        assert row["min_value"] == "1.0"
        assert row["max_value"] == "9.9"
        assert row["column_size_bytes"] == 200

    def test_upsert_replaces_existing_row(self, catalog, seeded):
        col_id = seeded["col_map"]["amount"]
        base = {"column_id": col_id, "value_count": 100, "null_count": 0,
                "min_value": "1.0", "max_value": "5.0", "column_size_bytes": 100}

        catalog.write_file_column_stats(seeded["file_id"], seeded["table_id"], [base])
        catalog.write_file_column_stats(seeded["file_id"], seeded["table_id"], [
            {**base, "min_value": "0.1", "max_value": "99.9"}
        ])

        con = db_connect(catalog.catalog_path)
        count = con.execute(
            "SELECT COUNT(*) FROM catalog_file_column_stats WHERE file_id=? AND column_id=?",
            (seeded["file_id"], col_id)
        ).fetchone()[0]
        row = con.execute(
            "SELECT min_value, max_value FROM catalog_file_column_stats WHERE file_id=? AND column_id=?",
            (seeded["file_id"], col_id)
        ).fetchone()
        con.close()

        assert count == 1
        assert row["min_value"] == "0.1"
        assert row["max_value"] == "99.9"

    def test_table_id_denormalized_correctly(self, catalog, seeded):
        col_id = seeded["col_map"]["user_id"]
        catalog.write_file_column_stats(seeded["file_id"], seeded["table_id"], [
            {"column_id": col_id, "value_count": 100, "null_count": 0,
             "min_value": None, "max_value": None, "column_size_bytes": 50},
        ])

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT table_id FROM catalog_file_column_stats WHERE file_id=? AND column_id=?",
            (seeded["file_id"], col_id)
        ).fetchone()
        con.close()

        assert row["table_id"] == seeded["table_id"]


class TestUpsertColumnStats:
    def test_rows_persisted_for_each_column(self, catalog, seeded):
        stats = [
            {"column_id": seeded["col_map"]["amount"],  "null_count": 3,
             "min_value": "0.0", "max_value": "500.0"},
            {"column_id": seeded["col_map"]["user_id"], "null_count": 0,
             "min_value": "abc", "max_value": "xyz"},
        ]
        catalog.upsert_column_stats(seeded["table_id"], stats)

        con = db_connect(catalog.catalog_path)
        count = con.execute(
            "SELECT COUNT(*) FROM catalog_column_stats WHERE table_id=?",
            (seeded["table_id"],)
        ).fetchone()[0]
        con.close()

        assert count == 2

    def test_correct_values_stored(self, catalog, seeded):
        col_id = seeded["col_map"]["amount"]
        catalog.upsert_column_stats(seeded["table_id"], [
            {"column_id": col_id, "null_count": 7, "min_value": "2.5", "max_value": "8.0"},
        ])

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT * FROM catalog_column_stats WHERE table_id=? AND column_id=?",
            (seeded["table_id"], col_id)
        ).fetchone()
        con.close()

        assert row["null_count"] == 7
        assert row["min_value"] == "2.5"
        assert row["max_value"] == "8.0"

    def test_upsert_overwrites_previous_stats(self, catalog, seeded):
        col_id = seeded["col_map"]["amount"]
        catalog.upsert_column_stats(seeded["table_id"], [
            {"column_id": col_id, "null_count": 1, "min_value": "1.0", "max_value": "10.0"},
        ])
        catalog.upsert_column_stats(seeded["table_id"], [
            {"column_id": col_id, "null_count": 5, "min_value": "0.0", "max_value": "99.0"},
        ])

        con = db_connect(catalog.catalog_path)
        rows = con.execute(
            "SELECT * FROM catalog_column_stats WHERE table_id=? AND column_id=?",
            (seeded["table_id"], col_id)
        ).fetchall()
        con.close()

        assert len(rows) == 1
        assert rows[0]["null_count"] == 5
        assert rows[0]["min_value"] == "0.0"
        assert rows[0]["max_value"] == "99.0"

    def test_updated_at_refreshed_on_upsert(self, catalog, seeded):
        import time
        col_id = seeded["col_map"]["amount"]
        catalog.upsert_column_stats(seeded["table_id"], [
            {"column_id": col_id, "null_count": 0, "min_value": "1.0", "max_value": "2.0"},
        ])

        con = db_connect(catalog.catalog_path)
        before = con.execute(
            "SELECT updated_at FROM catalog_column_stats WHERE table_id=? AND column_id=?",
            (seeded["table_id"], col_id)
        ).fetchone()["updated_at"]
        con.close()

        time.sleep(0.05)
        catalog.upsert_column_stats(seeded["table_id"], [
            {"column_id": col_id, "null_count": 0, "min_value": "1.0", "max_value": "2.0"},
        ])

        con = db_connect(catalog.catalog_path)
        after = con.execute(
            "SELECT updated_at FROM catalog_column_stats WHERE table_id=? AND column_id=?",
            (seeded["table_id"], col_id)
        ).fetchone()["updated_at"]
        con.close()

        assert after > before
