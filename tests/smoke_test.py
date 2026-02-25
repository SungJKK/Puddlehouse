from rich.console import Console
from rich.table   import Table
import duckdb

from scripts.init_lakehouse    import init_lakehouse
from scripts.init_catalog      import init_catalog
from scripts.generate_data     import generate_users, generate_events, generate_orders
from scripts.clean_up          import clean_main
from catalog.manager           import CatalogManager
from storage.writer            import write_parquet, read_parquet
from config                    import config

console = Console()

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
            COUNT(*)        AS event_count,
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

    # 7. Clean files
    if clean_up:
        console.print("Cleaning up data...")
        clean_main()
        console.print("  ✓ Done")


if __name__ == "__main__":
    run_smoke_test(clean_up=False)
