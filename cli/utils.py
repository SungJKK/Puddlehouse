import typer


def parse_target(target: str) -> tuple[str, str]:
    """Parse a 'zone/entity' argument into (zone, entity)."""
    parts = target.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        typer.echo("Error: target must be in the format zone/entity (e.g. bronze/users)", err=True)
        raise typer.Exit(1)
    return parts[0], parts[1]
