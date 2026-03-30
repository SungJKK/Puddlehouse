import json
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Any
from catalog.manager import CatalogManager
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["governance"])


# ── Audit ─────────────────────────────────────────────────────────────

@router.get("/{zone}/{entity}/audit")
def get_audit_log(
    zone: str,
    entity: str,
    limit: int = Query(100, ge=1),
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    entries = catalog.get_audit_log(table_id=table_id, limit=limit)
    return {
        "table_id": table_id,
        "entries": [
            {
                "entry_id": e.log_id,
                "operation": e.operation,
                "details": json.loads(e.details) if e.details else {},
                "recorded_at": e.created_at,
            }
            for e in entries
        ],
    }


# ── Quality Contracts ─────────────────────────────────────────────────

@router.get("/{zone}/{entity}/quality/contracts")
def list_quality_contracts(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    contracts = catalog.list_quality_contracts(table_id)
    return {
        "table_id": table_id,
        "contracts": [
            {
                "contract_id": c["contract_id"],
                "check_type": c["check_type"],
                "params": json.loads(c["params"]),
                "is_active": bool(c["is_active"]),
            }
            for c in contracts
        ],
    }


class AddContractRequest(BaseModel):
    check_type: str
    params: dict[str, Any] = {}


@router.post("/{zone}/{entity}/quality/contracts", status_code=201)
def add_quality_contract(
    zone: str,
    entity: str,
    body: AddContractRequest,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    contract_id = catalog.add_quality_contract(
        table_id=table_id,
        check_type=body.check_type,
        params=body.params,
    )
    return {"contract_id": contract_id}


@router.post("/{zone}/{entity}/quality/run")
def run_quality_checks(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    results = catalog.run_quality_checks(table_id)
    return {
        "table_id": table_id,
        "all_passed": all(r["passed"] for r in results),
        "results": results,
    }


# ── Vacuum ────────────────────────────────────────────────────────────

class VacuumRequest(BaseModel):
    retain_last_n: int = 1
    dry_run: bool = True


@router.post("/{zone}/{entity}/vacuum")
def vacuum(
    zone: str,
    entity: str,
    body: VacuumRequest = VacuumRequest(),
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"

    # Count snapshots that will be removed before vacuuming
    with catalog._connect() as con:
        result = con.execute(
            "SELECT MAX(version) FROM catalog_snapshots WHERE table_id=?", (table_id,)
        ).fetchone()
        max_version = result[0]

    snapshots_removed = 0
    if max_version is not None:
        cutoff = max_version - body.retain_last_n
        if cutoff >= 1:
            with catalog._connect() as con:
                row = con.execute(
                    "SELECT COUNT(*) FROM catalog_snapshots WHERE table_id=? AND version <= ?",
                    (table_id, cutoff),
                ).fetchone()
                snapshots_removed = row[0]

    paths = catalog.vacuum(table_id, retain_last_n=body.retain_last_n, dry_run=body.dry_run)
    return {
        "table_id": table_id,
        "dry_run": body.dry_run,
        "snapshots_removed": snapshots_removed,
        "files_removed": len(paths),
        "paths": paths,
    }
