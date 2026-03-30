from pathlib import Path
from typing import Annotated

import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Execute SQL queries via DuckDB.")


@app.command("query")
def query(
    ctx: typer.Context,
    table: str = typer.Option(..., "--table", help="Primary table to query (zone/entity)"),
    sql: str = typer.Option(None, "--sql", help="SQL query string"),
    file: Path = typer.Option(None, "--file", help="Path to a .sql file"),
    version: int = typer.Option(None, "--version", help="Pin to a snapshot version (time travel)"),
    partition: Annotated[list[str], typer.Option("--partition", help="Partition filter as key=value (repeatable)")] = [],
):
    """Execute arbitrary SQL against table data using DuckDB.

    SQL is provided via --sql or --file. The table is registered as a DuckDB
    view named {zone}_{entity} (e.g. bronze_users).
    """
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

    zone, entity = parse_target(table)

    context: dict = {"zone": zone, "entity": entity}
    if version is not None:
        context["version"] = version
    if partition:
        filters: dict = {}
        for p in partition:
            if "=" not in p:
                print_error(f"Invalid partition filter '{p}': must be key=value")
                raise typer.Exit(1)
            k, v = p.split("=", 1)
            filters[k] = v
        context["partition_filters"] = filters

    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post("/query", body={"sql": sql, "context": context})
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    render(cfg.output, data["columns"], data["rows"])
