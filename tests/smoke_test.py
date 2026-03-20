import duckdb
import pytest
from rich.console import Console
from rich.table import Table

from scripts.init_lakehouse import init_lakehouse
from scripts.init_catalog import init_catalog
from scripts.generate_data import generate_users, generate_events, generate_orders
from scripts.clean_up import clean_main
from catalog.manager import CatalogManager
from storage.writer import write_parquet, read_parquet
from config import config

console = Console()


# ── Manual runner (python -m tests.smoke_test) ────────────────────────────────

def run_smoke_test(clean_up: bool = False):
    console.rule("[bold blue]Phase 1 Smoke Test")

    # 1. Initialize
    console.print("[1/6] Initializing lakehouse structure...")
    init_lakehouse(reset=True)
    init_catalog()
    console.print("  ✓ Folders and catalog created")

    # 2. Generate fake data
    console.print("[2/6] Generating fake data...")
    users  = generate_users(100)
    events = generate_events(users, 1000)
    orders = generate_orders(users, 200)
    console.print(f"  ✓ {len(users)} users, {len(events)} events, {len(orders)} orders")

    # 3. Write to bronze
    console.print("[3/6] Writing to bronze...")
    write_parquet(users,  "bronze", "users",  job_name="smoke_test")
    write_parquet(events, "bronze", "events", partition_cols=["date"], job_name="smoke_test")
    write_parquet(orders, "bronze", "orders", partition_cols=["date"], job_name="smoke_test")
    console.print("  ✓ Bronze parquet files written")

    # 4. Verify catalog
    console.print("[4/6] Verifying catalog...")
    mgr    = CatalogManager()
    tables = mgr.list_tables()
    t      = Table("table_id", "zone", "rows", "location")
    for tbl in tables:
        t.add_row(tbl.table_id, tbl.zone, str(tbl.row_count), tbl.location)
    console.print(t)

    # 5. Query with DuckDB
    console.print("[5/6] Querying with DuckDB...")
    con = duckdb.connect()
    results = con.execute(f"""
        SELECT
            event_type,
            COUNT(*)              AS event_count,
            ROUND(AVG(amount), 2) AS avg_amount
        FROM read_parquet('{config.bronze_path}/events/**/*.parquet')
        GROUP BY event_type
        ORDER BY event_count DESC
    """).df()
    console.print(results.to_string())

    # 6. Verify snapshot
    console.print("[6/6] Verifying snapshots...")
    snap = mgr.get_latest_snapshot("bronze.events")
    console.print(f"  ✓ Snapshot v{snap.version} — {snap.row_count} rows — {snap.byte_size} bytes")

    console.rule("[bold green] Phase 1 PASSED")

    if clean_up:
        console.print("Cleaning up data...")
        clean_main()
        console.print("  ✓ Done")


# ── Pytest integration test ───────────────────────────────────────────────────

def test_smoke_pipeline(writer_env):
    """
    End-to-end smoke test. Uses an isolated tmp catalog + warehouse via
    writer_env, so it never touches the real warehouse directory.
    """
    import config as cfg_module
    mgr = writer_env  # writer_env IS the CatalogManager for the tmp catalog

    # ── 1. Init folder structure ──────────────────────────────────────────────
    init_lakehouse()  # uses monkeypatched config.data_root → tmp warehouse

    assert cfg_module.config.bronze_path.exists()
    assert cfg_module.config.silver_path.exists()
    assert cfg_module.config.gold_path.exists()

    # ── 2. Generate fake data ─────────────────────────────────────────────────
    users  = generate_users(50)
    events = generate_events(users, 200)
    orders = generate_orders(users, 80)

    assert len(users)  == 50
    assert len(events) == 200
    assert len(orders) == 80

    # ── 3. Write to bronze ────────────────────────────────────────────────────
    write_parquet(users,  "bronze", "users",  job_name="smoke_test")
    write_parquet(events, "bronze", "events", partition_cols=["date"], job_name="smoke_test")
    write_parquet(orders, "bronze", "orders", partition_cols=["date"], job_name="smoke_test")

    # ── 4. Catalog: all three tables registered ───────────────────────────────
    tables = mgr.list_tables(zone="bronze")
    table_ids = {t.table_id for t in tables}

    assert len(tables) == 3
    assert "bronze.users"  in table_ids
    assert "bronze.events" in table_ids
    assert "bronze.orders" in table_ids
    assert all(t.zone == "bronze" for t in tables)

    # ── 5. Catalog: row counts match generated data ───────────────────────────
    users_tbl  = mgr.get_table("bronze.users")
    events_tbl = mgr.get_table("bronze.events")
    orders_tbl = mgr.get_table("bronze.orders")

    assert users_tbl.row_count  == 50
    assert events_tbl.row_count == 200
    assert orders_tbl.row_count == 80

    # ── 6. Catalog: snapshots at version 1 with correct row counts ────────────
    for table_id, expected_rows in [
        ("bronze.users",  50),
        ("bronze.events", 200),
        ("bronze.orders", 80),
    ]:
        snap = mgr.get_latest_snapshot(table_id)
        assert snap is not None,            f"No snapshot for {table_id}"
        assert snap.version == 1,           f"Expected v1 for {table_id}, got v{snap.version}"
        assert snap.row_count == expected_rows, \
            f"Expected {expected_rows} rows for {table_id}, got {snap.row_count}"
        assert snap.byte_size > 0,          f"byte_size should be positive for {table_id}"

    # ── 7. Catalog: snapshot files exist for each table ───────────────────────
    for table_id in ("bronze.users", "bronze.events", "bronze.orders"):
        snap  = mgr.get_latest_snapshot(table_id)
        files = mgr.get_snapshot_files(snap.snapshot_id)
        assert len(files) > 0, f"No files registered for {table_id}"
        for f in files:
            from pathlib import Path
            assert Path(f.file_path).exists(), f"Missing file on disk: {f.file_path}"

    # ── 8. Catalog: columns registered for each table ────────────────────────
    for table_id, expected_cols in [
        ("bronze.users",  {"user_id", "name", "email", "country", "created_at"}),
        ("bronze.events", {"event_id", "user_id", "event_type", "amount"}),
        ("bronze.orders", {"order_id", "user_id", "total", "status"}),
    ]:
        snap = mgr.get_latest_snapshot(table_id)
        cols = {c.column_name for c in mgr.get_schema_at_version(table_id, snap.version)}
        assert expected_cols.issubset(cols), \
            f"{table_id} missing columns: {expected_cols - cols}"

    # ── 9. Catalog: partitions registered for partitioned tables ─────────────
    from tests.conftest import db_connect
    con = db_connect(mgr.catalog_path)
    for table_id in ("bronze.events", "bronze.orders"):
        count = con.execute(
            "SELECT COUNT(*) FROM catalog_partitions WHERE table_id=?", (table_id,)
        ).fetchone()[0]
        assert count > 0, f"No partitions registered for {table_id}"
    con.close()

    # ── 10. Catalog: lineage recorded for all writes ──────────────────────────
    con = db_connect(mgr.catalog_path)
    for table_id in ("bronze.users", "bronze.events", "bronze.orders"):
        row = con.execute(
            "SELECT * FROM catalog_lineage WHERE target_id=? AND job_name='smoke_test'",
            (table_id,)
        ).fetchone()
        assert row is not None, f"No lineage entry for {table_id}"
    con.close()

    # ── 11. read_parquet round-trips data correctly ───────────────────────────
    users_back = read_parquet("bronze", "users")
    assert len(users_back) == 50
    assert "user_id" in users_back.columns

    # ── 12. DuckDB can query the partitioned events data ─────────────────────
    ddb = duckdb.connect()
    results = ddb.execute(f"""
        SELECT
            event_type,
            COUNT(*)              AS event_count,
            ROUND(AVG(amount), 2) AS avg_amount
        FROM read_parquet('{cfg_module.config.bronze_path}/events/**/*.parquet')
        GROUP BY event_type
        ORDER BY event_count DESC
    """).df()

    assert len(results) > 0
    assert set(results.columns) == {"event_type", "event_count", "avg_amount"}
    assert results["event_count"].sum() == 200


if __name__ == "__main__":
    run_smoke_test(clean_up=False)
