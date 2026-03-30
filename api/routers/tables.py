from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from catalog.manager import CatalogManager
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("")
def list_tables(
    zone: str = Query(None, description="Filter by zone: bronze, silver, gold"),
    catalog: CatalogManager = Depends(get_catalog),
):
    tables = catalog.list_tables(zone=zone)
    return {
        "tables": [
            {
                "table_id": t.table_id,
                "zone": t.zone,
                "entity": t.entity,
                "location": t.location,
                "owner": t.owner,
                "row_count": t.row_count,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tables
        ]
    }


@router.get("/{zone}/{entity}")
def get_table(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    table = catalog.get_table(table_id)
    if not table or not table.is_active:
        raise KeyError(table_id)

    latest = catalog.get_latest_snapshot(table_id)
    return {
        "table_id": table.table_id,
        "zone": table.zone,
        "entity": table.entity,
        "location": table.location,
        "owner": table.owner,
        "row_count": table.row_count,
        "latest_version": latest.version if latest else None,
        "created_at": table.created_at,
        "updated_at": table.updated_at,
    }


@router.delete("/{zone}/{entity}", status_code=204)
def deregister_table(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    found = catalog.deregister_table(table_id)
    if not found:
        raise KeyError(table_id)
    return Response(status_code=204)
