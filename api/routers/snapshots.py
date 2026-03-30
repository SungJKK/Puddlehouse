from fastapi import APIRouter, Depends
from catalog.manager import CatalogManager
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["snapshots"])


def _snapshot_with_files(snapshot, catalog: CatalogManager) -> dict:
    files = catalog.get_snapshot_files(snapshot.snapshot_id)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "version": snapshot.version,
        "row_count": snapshot.row_count,
        "byte_size": snapshot.byte_size,
        "created_at": snapshot.created_at,
        "files": [
            {
                "file_id": f.file_id,
                "path": f.file_path,
                "row_count": f.row_count,
                "byte_size": f.byte_size,
            }
            for f in files
        ],
    }


@router.get("/{zone}/{entity}/snapshots")
def list_snapshots(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    snapshots = catalog.list_snapshots(table_id)
    return {
        "table_id": table_id,
        "snapshots": [
            {
                "snapshot_id": s.snapshot_id,
                "version": s.version,
                "row_count": s.row_count,
                "byte_size": s.byte_size,
                "created_at": s.created_at,
            }
            for s in snapshots
        ],
    }


@router.get("/{zone}/{entity}/snapshots/latest")
def get_latest_snapshot(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    snapshot = catalog.get_latest_snapshot(table_id)
    if not snapshot:
        raise KeyError(f"{table_id} has no snapshots")
    return _snapshot_with_files(snapshot, catalog)


@router.get("/{zone}/{entity}/snapshots/{version}")
def get_snapshot_at_version(
    zone: str,
    entity: str,
    version: int,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    snapshot = catalog.get_snapshot_at_version(table_id, version)
    if not snapshot:
        raise KeyError(f"{table_id} version {version} not found")
    return _snapshot_with_files(snapshot, catalog)
