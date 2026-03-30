import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Partition registration and listing.")


@app.command("list")
def list_partitions(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """List all partition entries for a table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/partitions")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["key", "value", "file_path", "row_count"]
    rows = [[p["key"], p["value"], p["file_path"], p["row_count"]] for p in data["partitions"]]
    render(cfg.output, headers, rows)


@app.command("add")
def add_partition(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    key: str = typer.Option(..., "--key", help="Partition key (e.g. date)"),
    value: str = typer.Option(..., "--value", help="Partition value (e.g. 2026-01-01)"),
    file_path: str = typer.Option(..., "--file-path", help="Path to the Parquet file for this partition"),
    row_count: int = typer.Option(..., "--row-count", help="Number of rows in the file"),
):
    """Register a partition entry for a specific file."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(
            f"/tables/{zone}/{entity}/partitions",
            body={"key": key, "value": value, "file_path": file_path, "row_count": row_count},
        )
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    print_success(f"Partition registered. ID: {data['partition_id']}")
