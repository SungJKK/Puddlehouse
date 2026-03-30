import typer

from cli.config import load_config
from cli.render import set_quiet
from cli.commands import audit, data, lineage, partitions, quality, query, schema, snapshots, stats, tables, vacuum, views

app = typer.Typer(
    name="lh",
    help="Lakehouse CLI — a thin client over the lakehouse REST API.",
    no_args_is_help=True,
)

# --- command groups (lh <group> <verb>) --------------------------------------

app.add_typer(tables.app,     name="tables")
app.add_typer(snapshots.app,  name="snapshots")
app.add_typer(schema.app,     name="schema")
app.add_typer(data.app,       name="data")
app.add_typer(partitions.app, name="partitions")
app.add_typer(stats.app,      name="stats")
app.add_typer(lineage.app,    name="lineage")
app.add_typer(quality.app,    name="quality")
app.add_typer(views.app,      name="views")

# --- top-level commands (lh <verb>) -----------------------------------------
# audit, vacuum, query are single commands, not groups — register directly.

app.command("audit")(audit.audit)
app.command("vacuum")(vacuum.vacuum)
app.command("query")(query.query)

# --- global callback (sets ctx.obj for all subcommands) ---------------------

@app.callback()
def main(
    ctx: typer.Context,
    api_url: str = typer.Option(None, "--api-url", envvar="LH_API_URL", help="Base URL of the lakehouse API server"),
    output: str = typer.Option(None, "--output", "-o", help="Output format: table, json, csv"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress decorative output; print only data"),
):
    ctx.ensure_object(dict)
    cfg = load_config(api_url=api_url, output=output)
    ctx.obj = cfg
    set_quiet(quiet)
