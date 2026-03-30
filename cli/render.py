import csv
import json
import sys  # still used by _render_csv (csv.writer writes to sys.stdout)
from typing import Any

from rich.console import Console
from rich.table import Table

_console = Console()
_err_console = Console(stderr=True)
_quiet = False


def set_quiet(quiet: bool) -> None:
    global _quiet
    _quiet = quiet


def render(output: str, headers: list[str], rows: list[list[Any]]) -> None:
    """Render tabular data in the requested output format."""
    if output == "json":
        _render_json(headers, rows)
    elif output == "csv":
        _render_csv(headers, rows)
    else:
        _render_table(headers, rows)


def render_raw_json(data: Any) -> None:
    """Pretty-print a raw API response dict as JSON."""
    _console.print_json(json.dumps(data))


def render_kv(pairs: list[tuple[str, Any]]) -> None:
    """Print a vertical key-value block (used for single-record detail views)."""
    if _quiet:
        return
    for key, value in pairs:
        _console.print(f"[bold]{key}:[/bold]  {value}")


def print_success(message: str) -> None:
    if _quiet:
        return
    _console.print(message)


def print_error(message: str) -> None:
    _err_console.print(f"[red]{message}[/red]")


# --- private helpers ---------------------------------------------------------

def _render_table(headers: list[str], rows: list[list[Any]]) -> None:
    table = Table(show_header=True, header_style="bold")
    for h in headers:
        table.add_column(h.upper())
    for row in rows:
        table.add_row(*[str(v) if v is not None else "—" for v in row])
    _console.print(table)


def _render_csv(headers: list[str], rows: list[list[Any]]) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])


def _render_json(headers: list[str], rows: list[list[Any]]) -> None:
    records = [dict(zip(headers, row)) for row in rows]
    print(json.dumps(records, indent=2, default=str))
