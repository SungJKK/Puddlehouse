import json

import typer
from rich.console import Console

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Quality contracts and checks.")
contracts_app = typer.Typer(help="Manage quality contracts.")
app.add_typer(contracts_app, name="contracts")

_console = Console()


@contracts_app.command("list")
def contracts_list(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """List all quality contracts for a table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/quality/contracts")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["contract_id", "check_type", "params", "is_active"]
    rows = [
        [
            c["contract_id"],
            c["check_type"],
            ", ".join(f"{k}={v}" for k, v in c["params"].items()),
            "yes" if c["is_active"] else "no",
        ]
        for c in data["contracts"]
    ]
    render(cfg.output, headers, rows)


@contracts_app.command("add")
def contracts_add(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    check_type: str = typer.Option(..., "--check-type", help="not_empty, freshness_days, or max_null_fraction"),
    params: str = typer.Option(..., "--params", help='JSON params string (e.g. \'{"min_rows": 1}\')'),
):
    """Add a quality contract to a table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)

    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON for --params: {e}")
        raise typer.Exit(1)

    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(
            f"/tables/{zone}/{entity}/quality/contracts",
            body={"check_type": check_type, "params": params_dict},
        )
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    print_success(f"Quality contract added. ID: {data['contract_id']}")


@app.command("run")
def run_quality(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
):
    """Run all active quality contracts for a table. Exits 1 if any check fails."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(f"/tables/{zone}/{entity}/quality/run")
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["passed", "contract_id", "check_type", "details"]
    rows = [
        ["✓" if r["passed"] else "✗", r["contract_id"], r["check_type"], r.get("details", "")]
        for r in data["results"]
    ]
    render(cfg.output, headers, rows)

    if data["all_passed"]:
        print_success("\nAll checks passed.")
    else:
        failed = sum(1 for r in data["results"] if not r["passed"])
        total = len(data["results"])
        print_error(f"\n{failed} of {total} checks failed.")
        raise typer.Exit(1)
