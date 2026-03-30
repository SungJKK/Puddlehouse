from fastapi import APIRouter, Depends
from pydantic import BaseModel
from catalog.manager import CatalogManager
from api.deps import get_catalog

router = APIRouter(prefix="/tables", tags=["partitions"])


class RegisterPartitionRequest(BaseModel):
    key: str
    value: str
    file_path: str
    row_count: int


@router.get("/{zone}/{entity}/partitions")
def list_partitions(
    zone: str,
    entity: str,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    partitions = catalog.list_partitions(table_id)
    return {
        "table_id": table_id,
        "partitions": [
            {
                "partition_id": p.partition_id,
                "key": p.partition_key,
                "value": p.partition_val,
                "file_path": p.file_path,
                "row_count": p.row_count,
            }
            for p in partitions
        ],
    }


@router.post("/{zone}/{entity}/partitions", status_code=201)
def register_partition(
    zone: str,
    entity: str,
    body: RegisterPartitionRequest,
    catalog: CatalogManager = Depends(get_catalog),
):
    table_id = f"{zone}.{entity}"
    partition_id = catalog.register_partition(
        table_id=table_id,
        key=body.key,
        val=body.value,
        file_path=body.file_path,
        row_count=body.row_count,
    )
    return {"partition_id": partition_id}
