from pathlib import Path

import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_kv, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Read, write, and compact table data.")


@app.command("read")
def read_data(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    version: int = typer.Option(None, "--version", help="Time travel: read at this snapshot version"),
    limit: int = typer.Option(1000, "--limit", help="Max rows to return"),
    offset: int = typer.Option(0, "--offset", help="Row offset for pagination"),
):
    """Read data from a table and print to stdout."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)

    params: dict = {"limit": limit, "offset": offset}
    if version is not None:
        params["version"] = version

    try:
        data = client.get(f"/tables/{zone}/{entity}/data", **params)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    render(cfg.output, data["columns"], data["rows"])


@app.command("write")
def write_data(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    file: Path = typer.Option(..., "--file", help="Path to a local Parquet file to ingest"),
    partition_cols: str = typer.Option(None, "--partition-cols", help="Comma-separated partition column names"),
    job_name: str = typer.Option("cli", "--job-name", help="Label for lineage tracking"),
    run_id: str = typer.Option(None, "--run-id", help="Idempotency/tracking key for this job run"),
    source_id: str = typer.Option("external:cli", "--source-id", help="Source table_id or external:<label>"),
):
    """Write data to a table from a local Parquet file. Creates a new snapshot atomically."""
    import pyarrow.parquet as pq

    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)

    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)
    if file.suffix.lower() != ".parquet":
        print_error("Only .parquet files are supported. See README for CSV/JSON plans.")
        raise typer.Exit(1)

    try:
        table = pq.read_table(file)
        records = table.to_pylist()
    except Exception as e:
        print_error(f"Failed to read Parquet file: {e}")
        raise typer.Exit(1)

    body: dict = {
        "records": records,
        "job_name": job_name,
        "source_id": source_id,
    }
    if partition_cols:
        body["partition_cols"] = [c.strip() for c in partition_cols.split(",")]
    if run_id:
        body["run_id"] = run_id

    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(f"/tables/{zone}/{entity}/data", body=body)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    print_success("Snapshot created.")
    render_kv([
        ("Version",   data["version"]),
        ("Files",     data["files_written"]),
        ("Row Count", data["row_count"]),
        ("Size",      data["byte_size"]),
    ])


@app.command("compact")
def compact_data(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """Merge all files in the latest snapshot into a single Parquet file."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(f"/tables/{zone}/{entity}/compact")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    print_success("Compaction complete.")
    render_kv([
        ("Version",      data["version"]),
        ("Files Merged", data["files_merged"]),
        ("Output File",  data["compacted_file"]),
        ("Row Count",    data["row_count"]),
    ])
