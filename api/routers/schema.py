from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from catalog.manager import CatalogManager, SchemaEvolutionError
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["schema"])


class ColumnSpec(BaseModel):
    name: str
    type: str


class ValidateSchemaRequest(BaseModel):
    schema_: list[ColumnSpec] = Field(alias="schema")

    model_config = {"populate_by_name": True}


@router.get("/{zone}/{entity}/schema")
def get_schema(
    zone: str,
    entity: str,
    version: int = Query(None, description="Snapshot version; defaults to latest"),
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"

    if version is None:
        latest = catalog.get_latest_snapshot(table_id)
        if not latest:
            raise KeyError(table_id)
        version = latest.version

    columns = catalog.get_schema_at_version(table_id, version)
    return {
        "table_id": table_id,
        "version": version,
        "columns": [
            {
                "column_id": c.column_id,
                "name": c.column_name,
                "type": c.column_type,
                "position": c.column_order,
                "added_version": c.added_at_version,
                "dropped_version": c.dropped_at_version,
            }
            for c in columns
        ],
    }


@router.post("/{zone}/{entity}/schema/validate")
def validate_schema(
    zone: str,
    entity: str,
    body: ValidateSchemaRequest,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    proposed = [{"name": c.name, "type": c.type} for c in body.schema_]

    # Determine added columns by comparing against current active schema
    latest = catalog.get_latest_snapshot(table_id)
    current_version = latest.version if latest else 0
    current_cols = {
        c.column_name
        for c in catalog.get_schema_at_version(table_id, current_version)
    }
    added = [c["name"] for c in proposed if c["name"] not in current_cols]

    try:
        catalog.validate_schema_evolution(table_id, proposed)
    except SchemaEvolutionError as e:
        return {
            "valid": False,
            "errors": e.errors,
        }

    return {
        "valid": True,
        "added_columns": added,
        "message": "Schema is backward-compatible.",
    }
