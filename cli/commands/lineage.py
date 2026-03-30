import typer
from rich.console import Console

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Data lineage tracking.")
_console = Console()


@app.command("get")
def get_lineage(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. silver/events)"),
    direction: str = typer.Option("both", "--direction", help="upstream, downstream, or both"),
):
    """Show upstream and/or downstream lineage for a table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/lineage", direction=direction)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    table_id = data["table_id"]
    headers = ["source_id", "job_name", "run_id", "rows_read", "rows_written", "recorded_at"]

    if direction in ("upstream", "both") and data.get("upstream"):
        _console.print(f"\n[bold]Upstream of {table_id}:[/bold]")
        rows = [
            [r["source_id"], r["job_name"], r["run_id"], r["rows_read"], r["rows_written"], r["recorded_at"]]
            for r in data["upstream"]
        ]
        render(cfg.output, headers, rows)

    if direction in ("downstream", "both") and data.get("downstream"):
        _console.print(f"\n[bold]Downstream of {table_id}:[/bold]")
        rows = [
            [r["source_id"], r["job_name"], r["run_id"], r["rows_read"], r["rows_written"], r["recorded_at"]]
            for r in data["downstream"]
        ]
        render(cfg.output, headers, rows)


@app.command("record")
def record_lineage(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Target table in zone/entity format (e.g. silver/events)"),
    source: str = typer.Option(..., "--source", help="Source table_id or external:<label>"),
    job_name: str = typer.Option(None, "--job-name", help="Name of the transformation job"),
    run_id: str = typer.Option(None, "--run-id", help="Unique identifier for this job run"),
    rows_read: int = typer.Option(None, "--rows-read", help="Number of rows read from source"),
    rows_written: int = typer.Option(None, "--rows-written", help="Number of rows written to target"),
):
    """Record a lineage relationship: source table produced this table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)

    body: dict = {"source_id": source}
    if job_name:
        body["job_name"] = job_name
    if run_id:
        body["run_id"] = run_id
    if rows_read is not None:
        body["rows_read"] = rows_read
    if rows_written is not None:
        body["rows_written"] = rows_written

    try:
        data = client.post(f"/tables/{zone}/{entity}/lineage", body=body)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    print_success(f"Lineage recorded. ID: {data['lineage_id']}")
