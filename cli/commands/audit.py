import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Audit log.")


@app.command("audit")
def audit(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    limit: int = typer.Option(100, "--limit", help="Max entries to show"),
):
    """Show the audit log for a table."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.get(f"/tables/{zone}/{entity}/audit", limit=limit)
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    headers = ["recorded_at", "operation", "details"]
    rows = [
        [e["recorded_at"], e["operation"], str(e.get("details", ""))]
        for e in data["entries"]
    ]
    render(cfg.output, headers, rows)
