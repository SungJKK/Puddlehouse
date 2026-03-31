from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Literal
from catalog.manager import CatalogManager
from api.deps import get_catalog

router = APIRouter(prefix="/views", tags=["views"])


def _serialize_view(v) -> dict:
    return {
        "view_id": v.view_id,
        "name": v.view_name,
        "zone": v.zone,
        "view_type": v.view_type,
        "sql": v.sql,
        "owner": v.owner,
        "refresh_snapshot_id": v.refresh_snapshot_id,
        "last_refreshed_at": v.last_refreshed_at,
        "created_at": v.created_at,
        "updated_at": v.updated_at,
    }


@router.get("")
def list_views(
    zone: str = Query(None),
    type: Literal["view", "materialized_view"] | None = Query(None),
    catalog: CatalogManager = Depends(get_catalog),
):
    views = catalog.list_views(zone=zone, view_type=type)
    return {"views": [_serialize_view(v) for v in views]}


class RegisterViewRequest(BaseModel):
    name: str
    zone: str
    view_type: Literal["view", "materialized_view"]
    sql: str
    owner: str = "default"


@router.post("", status_code=201)
def register_view(
    body: RegisterViewRequest,
    catalog: CatalogManager = Depends(get_catalog),
):
    view_id = catalog.register_view(
        view_name=body.name,
        zone=body.zone,
        view_type=body.view_type,
        sql=body.sql,
        owner=body.owner,
    )
    return {"view_id": view_id}


@router.get("/{view_id}")
def get_view(
    view_id: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    view = catalog.get_view(view_id)
    if not view:
        raise KeyError(view_id)
    return _serialize_view(view)


class RefreshViewRequest(BaseModel):
    snapshot_id: str


@router.post("/{view_id}/refresh")
def refresh_view(
    view_id: str,
    body: RefreshViewRequest,
    catalog: CatalogManager = Depends(get_catalog),
):
    view = catalog.get_view(view_id)
    if not view:
        raise KeyError(view_id)
    if view.view_type != "materialized_view":
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR",
                               "message": f"View '{view_id}' is not a materialized_view and cannot be refreshed.",
                               "details": {}}},
        )

    catalog.refresh_materialized_view(view_id, body.snapshot_id)

    updated = catalog.get_view(view_id)
    return {
        "view_id": updated.view_id,
        "refresh_snapshot_id": updated.refresh_snapshot_id,
        "last_refreshed_at": updated.last_refreshed_at,
    }
