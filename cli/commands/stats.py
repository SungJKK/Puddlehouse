import typer
from rich.console import Console

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Column statistics.")
_console = Console()


@app.command("table")
def table_stats(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """Show aggregate table-level column statistics."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/stats")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["name", "null_count", "min_value", "max_value"]
    rows = [
        [s["name"], s["null_count"], s["min_value"] or "—", s["max_value"] or "—"]
        for s in data["column_stats"]
    ]
    render(cfg.output, headers, rows)


@app.command("files")
def file_stats(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """Show per-file, per-column statistics."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/stats/files")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    for file_entry in data["file_stats"]:
        _console.print(f"\n[bold]FILE:[/bold] {file_entry['file_path']} ({file_entry['file_id']})")
        headers = ["name", "null_count", "min_value", "max_value"]
        rows = [
            [s["name"], s["null_count"], s["min_value"] or "—", s["max_value"] or "—"]
            for s in file_entry["column_stats"]
        ]
        render(cfg.output, headers, rows)
