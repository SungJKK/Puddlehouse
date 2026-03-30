from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Literal
from catalog.manager import CatalogManager
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["lineage"])


class RecordLineageRequest(BaseModel):
    source_id: str
    job_name: str | None = None
    run_id: str | None = None
    rows_read: int = 0
    rows_written: int = 0


def _serialize(record) -> dict:
    return {
        "lineage_id": record.lineage_id,
        "source_id": record.source_id,
        "target_id": record.target_id,
        "job_name": record.job_name,
        "run_id": record.run_id,
        "rows_read": record.rows_read,
        "rows_written": record.rows_written,
        "recorded_at": record.created_at,
    }


@router.get("/{zone}/{entity}/lineage")
def get_lineage(
    zone: str,
    entity: str,
    direction: Literal["upstream", "downstream", "both"] = Query("both"),
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    result = catalog.get_lineage(table_id, direction=direction)
    return {
        "table_id": table_id,
        "upstream": [_serialize(r) for r in result["upstream"]],
        "downstream": [_serialize(r) for r in result["downstream"]],
    }


@router.post("/{zone}/{entity}/lineage", status_code=201)
def record_lineage(
    zone: str,
    entity: str,
    body: RecordLineageRequest,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    lineage_id = catalog.record_lineage(
        source_id=body.source_id,
        target_id=table_id,
        job_name=body.job_name or "",
        run_id=body.run_id or "",
        rows_read=body.rows_read,
        rows_written=body.rows_written,
    )
    return {"lineage_id": lineage_id}
