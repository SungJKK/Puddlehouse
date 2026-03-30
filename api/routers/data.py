from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Any
import pandas as pd
from catalog.manager import CatalogManager
from storage.writer import write_parquet, read_parquet, read_parquet_at_version, compact
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["data"])


class WriteDataRequest(BaseModel):
    records: list[dict[str, Any]]
    partition_cols: list[str] | None = None
    job_name: str = "api"
    run_id: str | None = None
    source_id: str = "external:api"


@router.post("/{zone}/{entity}/data", status_code=201)
def write_data(
    zone: str,
    entity: str,
    body: WriteDataRequest,
    catalog: CatalogManager = Depends(get_catalog),
):
    df = pd.DataFrame(body.records)
    written_files = write_parquet(
        df=df,
        zone=zone,
        entity=entity,
        partition_cols=body.partition_cols,
        run_id=body.run_id,
        job_name=body.job_name,
        source_id=body.source_id,
    )

    snap = catalog.get_latest_snapshot(f"{zone}.{entity}")
    return {
        "snapshot_id": snap.snapshot_id,
        "version": snap.version,
        "files_written": len(written_files),
        "row_count": snap.row_count,
        "byte_size": snap.byte_size,
    }


@router.get("/{zone}/{entity}/data")
def read_data(
    zone: str,
    entity: str,
    version: int = Query(None, description="Read at this snapshot version"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"

    if version is not None:
        df = read_parquet_at_version(zone, entity, version)
        version_used = version
    else:
        snap = catalog.get_latest_snapshot(table_id)
        if not snap:
            raise KeyError(table_id)
        df = read_parquet(zone, entity)
        version_used = snap.version

    page = df.iloc[offset: offset + limit]
    return {
        "table_id": table_id,
        "version": version_used,
        "row_count": len(page),
        "columns": list(page.columns),
        "rows": page.values.tolist(),
    }


@router.post("/{zone}/{entity}/compact")
def compact_table(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"

    # Capture file count before compaction for files_merged
    pre_snap = catalog.get_latest_snapshot(table_id)
    if not pre_snap:
        raise KeyError(table_id)
    pre_files = catalog.get_table_files_at_version(table_id, pre_snap.version)

    compacted_path = compact(zone, entity)

    snap = catalog.get_latest_snapshot(table_id)
    return {
        "snapshot_id": snap.snapshot_id,
        "version": snap.version,
        "compacted_file": compacted_path,
        "files_merged": len(pre_files),
        "row_count": snap.row_count,
    }
