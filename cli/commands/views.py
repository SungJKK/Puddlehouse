from pathlib import Path

import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_kv, render_raw_json

app = typer.Typer(help="View and materialized view management.")


@app.command("list")
def list_views(
    ctx: typer.Context,
    zone: str = typer.Option(None, "--zone", help="Filter by zone: bronze, silver, gold"),
    type: str = typer.Option(None, "--type", help="Filter by type: view or materialized_view"),
):
    """List all registered views."""
    cfg = ctx.obj or load_config()
    client = LakehouseClient(cfg.api_url)

    params: dict = {}
    if zone:
        params["zone"] = zone
    if type:
        params["type"] = type

    try:
        data = client.get("/views", **params)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["view_id", "name", "zone", "view_type", "owner", "last_refreshed_at"]
    rows = [
        [v["view_id"], v["name"], v["zone"], v["view_type"], v["owner"], v["last_refreshed_at"] or "—"]
        for v in data["views"]
    ]
    render(cfg.output, headers, rows)


@app.command("get")
def get_view(
    ctx: typer.Context,
    view_id: str = typer.Argument(..., help="View ID (e.g. view_001)"),
):
    """Show details for a specific view."""
    cfg = ctx.obj or load_config()
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/views/{view_id}")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    render_kv([
        ("View ID",        data["view_id"]),
        ("Name",           data["name"]),
        ("Zone",           data["zone"]),
        ("Type",           data["view_type"]),
        ("Owner",          data["owner"]),
        ("Last Refreshed", data["last_refreshed_at"] or "—"),
        ("Snapshot",       data["refresh_snapshot_id"] or "—"),
        ("Created",        data["created_at"]),
    ])
    typer.echo(f"\nSQL:\n  {data['sql']}")


@app.command("create")
def create_view(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Unique view name"),
    zone: str = typer.Option(..., "--zone", help="Zone: bronze, silver, gold"),
    type: str = typer.Option(..., "--type", help="view or materialized_view"),
    sql: str = typer.Option(None, "--sql", help="SQL definition string"),
    file: Path = typer.Option(None, "--file", help="Path to a .sql file"),
    owner: str = typer.Option("default", "--owner", help="Owning team or user"),
):
    """Register a new view or materialized view."""
    cfg = ctx.obj or load_config()

    if not sql and not file:
        print_error("One of --sql or --file is required.")
        raise typer.Exit(1)
    if sql and file:
        print_error("Provide only one of --sql or --file, not both.")
        raise typer.Exit(1)

    if file:
        if not file.exists():
            print_error(f"SQL file not found: {file}")
            raise typer.Exit(1)
        sql = file.read_text()

    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post("/views", body={"name": name, "zone": zone, "view_type": type, "sql": sql, "owner": owner})
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    print_success(f"View registered. ID: {data['view_id']}")


@app.command("refresh")
def refresh_view(
    ctx: typer.Context,
    view_id: str = typer.Argument(..., help="View ID to refresh"),
    snapshot_id: str = typer.Option(..., "--snapshot-id", help="Snapshot ID of the new materialized result"),
):
    """Refresh a materialized view to point to a new result snapshot."""
    cfg = ctx.obj or load_config()
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(f"/views/{view_id}/refresh", body={"snapshot_id": snapshot_id})
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    print_success("Materialized view refreshed.")
    render_kv([
        ("View",      data["view_id"]),
        ("Snapshot",  data["refresh_snapshot_id"]),
        ("Refreshed", data["last_refreshed_at"]),
    ])
