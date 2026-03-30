import pytest
from tests.conftest import db_connect


# ── T7: Lineage ───────────────────────────────────────────────────────────────

@pytest.fixture()
def tables(catalog):
    catalog.register_table("bronze", "events")
    catalog.register_table("silver", "events")
    return {"source": "bronze.events", "target": "silver.events"}


class TestRecordLineage:
    def test_row_persisted(self, catalog, tables):
        catalog.record_lineage(
            source_id=tables["source"],
            target_id=tables["target"],
            job_name="bronze_to_silver",
            run_id="run-001",
            rows_read=1000,
            rows_written=980,
        )

        con = db_connect(catalog.catalog_path)
        count = con.execute("SELECT COUNT(*) FROM catalog_lineage").fetchone()[0]
        con.close()

        assert count == 1

    def test_correct_fields_stored(self, catalog, tables):
        catalog.record_lineage(
            source_id=tables["source"],
            target_id=tables["target"],
            job_name="bronze_to_silver",
            run_id="run-001",
            rows_read=1000,
            rows_written=980,
        )

        con = db_connect(catalog.catalog_path)
        row = con.execute("SELECT * FROM catalog_lineage").fetchone()
        con.close()

        assert row["source_id"] == tables["source"]
        assert row["target_id"] == tables["target"]
        assert row["job_name"] == "bronze_to_silver"
        assert row["run_id"] == "run-001"
        assert row["rows_read"] == 1000
        assert row["rows_written"] == 980

    def test_lineage_id_is_unique_uuid(self, catalog, tables):
        catalog.record_lineage(tables["source"], tables["target"], "job", "r1", 10, 10)
        catalog.record_lineage(tables["source"], tables["target"], "job", "r2", 10, 10)

        con = db_connect(catalog.catalog_path)
        ids = [r["lineage_id"] for r in con.execute("SELECT lineage_id FROM catalog_lineage").fetchall()]
        con.close()

        assert len(ids) == 2
        assert ids[0] != ids[1]
        assert all(len(lid) == 36 for lid in ids)

    def test_external_source_label_accepted(self, catalog, tables):
        catalog.record_lineage(
            source_id="external:s3://raw-bucket/events/",
            target_id=tables["target"],
            job_name="ingest",
            run_id="run-ext",
            rows_read=500,
            rows_written=500,
        )

        con = db_connect(catalog.catalog_path)
        row = con.execute("SELECT source_id FROM catalog_lineage").fetchone()
        con.close()

        assert row["source_id"] == "external:s3://raw-bucket/events/"

    def test_multiple_runs_accumulate(self, catalog, tables):
        for i in range(3):
            catalog.record_lineage(
                tables["source"], tables["target"], "daily_job", f"run-{i}", 100, 100
            )

        con = db_connect(catalog.catalog_path)
        count = con.execute("SELECT COUNT(*) FROM catalog_lineage").fetchone()[0]
        con.close()

        assert count == 3

    def test_created_at_is_populated(self, catalog, tables):
        catalog.record_lineage(tables["source"], tables["target"], "job", "r1", 0, 0)

        con = db_connect(catalog.catalog_path)
        row = con.execute("SELECT created_at FROM catalog_lineage").fetchone()
        con.close()

        assert row["created_at"] is not None
