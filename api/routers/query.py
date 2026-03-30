import duckdb
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any
from catalog.manager import CatalogManager
from query.engine import QueryEngine
from api.deps import get_catalog, get_engine

router = APIRouter(tags=["query"])


class QueryContext(BaseModel):
    zone: str
    entity: str
    version: int | None = None
    partition_filters: dict[str, str] | None = None


class QueryRequest(BaseModel):
    sql: str
    context: QueryContext


@router.post("/query")
def run_query(
    body: QueryRequest,
    catalog: CatalogManager = Depends(get_catalog),
    engine: QueryEngine = Depends(get_engine),
):
    ctx = body.context
    table_id = f"{ctx.zone}.{ctx.entity}"

    # Resolve the version that will actually be used so we can report it
    if ctx.version is not None:
        snap = catalog.get_snapshot_at_version(table_id, ctx.version)
        if snap is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "SNAPSHOT_NOT_FOUND",
                                   "message": f"{table_id} version {ctx.version} not found",
                                   "details": {}}},
            )
        version_used = ctx.version
    else:
        snap = catalog.get_latest_snapshot(table_id)
        if snap is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "TABLE_NOT_FOUND",
                                   "message": f"No snapshots found for {table_id}",
                                   "details": {}}},
            )
        version_used = snap.version

    try:
        df = engine.query(
            sql=body.sql,
            zone=ctx.zone,
            entity=ctx.entity,
            version=ctx.version,
            partition_filters=ctx.partition_filters,
        )
    except duckdb.Error as e:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_SQL", "message": str(e), "details": {}}},
        )

    return {
        "columns": list(df.columns),
        "rows": df.values.tolist(),
        "row_count": len(df),
        "version_used": version_used,
    }
