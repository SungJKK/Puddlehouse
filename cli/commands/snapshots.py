import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, render, render_kv, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Snapshot listing and time travel.")


@app.command("list")
def list_snapshots(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """List all snapshots for a table, oldest to newest."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/snapshots")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["version", "snapshot_id", "row_count", "byte_size", "created_at"]
    rows = [
        [s["version"], s["snapshot_id"], s["row_count"], s["byte_size"], s["created_at"]]
        for s in data["snapshots"]
    ]
    render(cfg.output, headers, rows)


@app.command("latest")
def latest_snapshot(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """Show the most recent snapshot and its files."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/snapshots/latest")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    render_kv([
        ("Snapshot",  data["snapshot_id"]),
        ("Version",   data["version"]),
        ("Row Count", data["row_count"]),
        ("Size",      data["byte_size"]),
        ("Created",   data["created_at"]),
    ])
    typer.echo("")
    headers = ["file_id", "path", "row_count", "byte_size"]
    rows = [[f["file_id"], f["path"], f["row_count"], f["byte_size"]] for f in data["files"]]
    render(cfg.output, headers, rows)


@app.command("get")
def get_snapshot(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    version: int = typer.Option(..., "--version", help="Snapshot version number"),
):
    """Show a specific snapshot by version."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/snapshots/{version}")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    render_kv([
        ("Snapshot",  data["snapshot_id"]),
        ("Version",   data["version"]),
        ("Row Count", data["row_count"]),
        ("Size",      data["byte_size"]),
        ("Created",   data["created_at"]),
    ])
    typer.echo("")
    headers = ["file_id", "path", "row_count", "byte_size"]
    rows = [[f["file_id"], f["path"], f["row_count"], f["byte_size"]] for f in data["files"]]
    render(cfg.output, headers, rows)
