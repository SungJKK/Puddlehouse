import typer

from cli.client import ApiError, LakehouseClient
from cli.config import load_config
from cli.render import print_error, print_success, render, render_raw_json
from cli.utils import parse_target

app = typer.Typer(help="Retention and cleanup.")


@app.command("vacuum")
def vacuum(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Table in zone/entity format (e.g. bronze/users)"),
    retain_last_n: int = typer.Option(1, "--retain-last-n", help="Number of most recent snapshots to keep"),
    execute: bool = typer.Option(False, "--execute", help="Actually delete files. Without this flag, runs as dry-run."),
):
    """Remove old snapshots and files beyond the retention window. Dry-run by default."""
    cfg = ctx.obj or load_config()
    zone, entity = parse_target(target)
    client = LakehouseClient(cfg.api_url)
    try:
        data = client.post(
            f"/tables/{zone}/{entity}/vacuum",
            body={"retain_last_n": retain_last_n, "dry_run": not execute},
        )
    except ApiError as e:
        print_error(str(e))
        raise typer.Exit(1)

    if cfg.output == "json":
        render_raw_json(data)
        return

    if data["dry_run"]:
        print_success("DRY RUN — no files deleted.")
        print_success(f"Snapshots to remove: {data['snapshots_removed']}")
        print_success(f"Files to remove:     {data['files_removed']}")
        if data.get("paths"):
            typer.echo("")
            render(cfg.output, ["path"], [[p] for p in data["paths"]])
        print_success("\nRe-run with --execute to delete.")
    else:
        print_success("Vacuum complete.")
        print_success(f"Snapshots removed: {data['snapshots_removed']}")
        print_success(f"Files removed:     {data['files_removed']}")
