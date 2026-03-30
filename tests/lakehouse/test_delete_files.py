import pytest
from tests.conftest import db_connect


# ── T4: Delete Files ──────────────────────────────────────────────────────────

@pytest.fixture()
def committed(catalog):
    """A table with one snapshot and one file — the minimum needed to record a delete."""
    catalog.register_table("bronze", "events")
    table_id = "bronze.events"
    snapshot_id, _, file_id_map = catalog.create_snapshot(
        table_id,
        files=[{"file_path": "/tmp/events.parquet", "row_count": 500, "byte_size": 4096}],
        row_count=500,
        byte_size=4096,
    )
    file_id = file_id_map["/tmp/events.parquet"]
    return {"table_id": table_id, "snapshot_id": snapshot_id, "file_id": file_id}


class TestRecordDelete:
    def test_returns_valid_uuid(self, catalog, committed):
        delete_file_id = catalog.record_delete(
            table_id=committed["table_id"],
            snapshot_id=committed["snapshot_id"],
            file_id=committed["file_id"],
            delete_file_path="/tmp/deletes/d1.parquet",
            delete_count=10,
            byte_size=256,
        )
        assert isinstance(delete_file_id, str) and len(delete_file_id) == 36

    def test_row_persisted_with_correct_fields(self, catalog, committed):
        delete_file_id = catalog.record_delete(
            table_id=committed["table_id"],
            snapshot_id=committed["snapshot_id"],
            file_id=committed["file_id"],
            delete_file_path="/tmp/deletes/d1.parquet",
            delete_count=10,
            byte_size=256,
        )

        con = db_connect(catalog.catalog_path)
        row = con.execute(
            "SELECT * FROM catalog_delete_files WHERE delete_file_id=?",
            (delete_file_id,)
        ).fetchone()
        con.close()

        assert row is not None
        assert row["table_id"] == committed["table_id"]
        assert row["snapshot_id"] == committed["snapshot_id"]
        assert row["file_id"] == committed["file_id"]
        assert row["delete_file_path"] == "/tmp/deletes/d1.parquet"
        assert row["delete_count"] == 10
        assert row["byte_size"] == 256

    def test_multiple_deletes_against_same_file(self, catalog, committed):
        id1 = catalog.record_delete(
            committed["table_id"], committed["snapshot_id"], committed["file_id"],
            "/tmp/deletes/d1.parquet", delete_count=5, byte_size=128,
        )
        id2 = catalog.record_delete(
            committed["table_id"], committed["snapshot_id"], committed["file_id"],
            "/tmp/deletes/d2.parquet", delete_count=3, byte_size=64,
        )

        assert id1 != id2

        con = db_connect(catalog.catalog_path)
        count = con.execute(
            "SELECT COUNT(*) FROM catalog_delete_files WHERE file_id=?",
            (committed["file_id"],)
        ).fetchone()[0]
        con.close()

        assert count == 2

    def test_delete_ids_are_unique(self, catalog, committed):
        ids = [
            catalog.record_delete(
                committed["table_id"], committed["snapshot_id"], committed["file_id"],
                f"/tmp/deletes/d{i}.parquet", delete_count=1, byte_size=32,
            )
            for i in range(5)
        ]
        assert len(ids) == len(set(ids))
