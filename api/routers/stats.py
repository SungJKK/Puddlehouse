from fastapi import APIRouter, Depends
from catalog.manager import CatalogManager
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["stats"])


@router.get("/{zone}/{entity}/stats")
def get_table_stats(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    stats = catalog.get_column_stats(table_id)
    return {
        "table_id": table_id,
        "column_stats": [
            {
                "column_id": s["column_id"],
                "name": s["column_name"],
                "null_count": s["null_count"],
                "min_value": s["min_value"],
                "max_value": s["max_value"],
            }
            for s in stats
        ],
    }


@router.get("/{zone}/{entity}/stats/files")
def get_file_stats(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    file_stats = catalog.get_file_column_stats(table_id)
    return {
        "table_id": table_id,
        "file_stats": file_stats,
    }
