import json
from pathlib import Path

import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Schema inspection and evolution validation.")


@app.command("get")
def get_schema(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    version: int = typer.Option(None, "--version", help="Show schema at this snapshot version"),
):
    """Show the schema for a table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        params = {"version": version} if version is not None else {}
        data = client.get(f"/tables/{zone}/{entity}/schema", **params)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["position", "name", "type", "added_version", "dropped_version"]
    rows = [
        [c["position"], c["name"], c["type"], c["added_version"], c["dropped_version"] or "—"]
        for c in data["columns"]
    ]
    render(cfg.output, headers, rows)


@app.command("validate")
def validate_schema(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    file: Path = typer.Option(..., "--file", help="Path to JSON file with proposed schema"),
):
    """Check whether a proposed schema is backward-compatible. Does not modify anything."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)

    try:
        schema = json.loads(file.read_text())
    except Exception as e:
        print_error(f"Failed to read schema file: {e}")
        raise typer.Exit(1)

    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(f"/tables/{zone}/{entity}/schema/validate", body={"schema": schema})
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    if data["valid"]:
        print_success("Schema is backward-compatible.")
        if data.get("added_columns"):
            print_success(f"Added columns: {', '.join(data['added_columns'])}")
    else:
        for err in data.get("errors", []):
            print_error(f"  - {err}")
        raise typer.Exit(1)
