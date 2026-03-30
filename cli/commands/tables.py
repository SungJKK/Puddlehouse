import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_kv
from cli.utils import parse_target

app = typer.Typer(help="Table discovery and deregistration.")


@app.command("list")
def list_tables(
    ctx: typer.Context,
    zone: str = typer.Option(None, "--zone", help="Filter by zone: bronze, silver, gold"),
):
    """List all registered tables."""
    cfg = ctx.obj or load_config()
    client = LakehouseClient(cfg.api_url)
    try:
        params = {"zone": zone} if zone else {}
        data = client.get("/tables", **params)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    tables = data["tables"]
    if cfg.output == "json":
        from cli.render import render_raw_json
        render_raw_json(data)
        return

    headers = ["table_id", "zone", "entity", "row_count", "updated_at"]
    rows = [[t["table_id"], t["zone"], t["entity"], t["row_count"], t["updated_at"]] for t in tables]
    render(cfg.output, headers, rows)


@app.command("get")
def get_table(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """Show metadata for a specific table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        from cli.render import render_raw_json
        render_raw_json(data)
        return

    render_kv([
        ("Table ID",       data["table_id"]),
        ("Zone",           data["zone"]),
        ("Entity",         data["entity"]),
        ("Location",       data["location"]),
        ("Owner",          data["owner"]),
        ("Row Count",      data["row_count"]),
        ("Latest Version", data.get("latest_version", "—")),
        ("Created",        data["created_at"]),
        ("Updated",        data["updated_at"]),
    ])


@app.command("delete")
def delete_table(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    confirm: bool = typer.Option(False, "--confirm", help="Skip interactive confirmation prompt"),
):
    """Deregister a table from the catalog. Does not delete Parquet files."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    table_id = f"{zone}.{entity}"

    if not confirm:
        typer.confirm(f"Deregister table {table_id} from the catalog?", abort=True)

    client = LakehouseClient(cfg.api_url)
    try:
        client.delete(f"/tables/{zone}/{entity}")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    print_success(f"Table {table_id} deregistered.")
