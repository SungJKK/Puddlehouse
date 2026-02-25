from dataclasses import dataclass
from typing import Optional


@dataclass
class TableMeta:
    table_id:    str
    name:        str
    zone:        str
    entity:      str
    location:    str
    schema_json: Optional[str] = None
    owner:       str = "system"
    row_count:   int = 0
    is_active:   int = 1
    created_at:  Optional[str] = None
    updated_at:  Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "TableMeta":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class Snapshot:
    snapshot_id:   str
    table_id:      str
    version:       int
    manifest_path: str
    row_count:     Optional[int] = None
    byte_size:     Optional[int] = None
    created_at:    Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Snapshot":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class Partition:
    partition_id:  str
    table_id:      str
    partition_key: str
    partition_val: str
    file_path:     str
    row_count:     Optional[int] = None
    created_at:    Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Partition":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class LineageRecord:
    lineage_id:   str
    source_id:    str
    target_id:    str
    job_name:     Optional[str] = None
    run_id:       Optional[str] = None
    rows_read:    int = 0
    rows_written: int = 0
    created_at:   Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "LineageRecord":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class AuditEntry:
    log_id:     str
    operation:  str
    table_id:   Optional[str] = None
    details:    Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "AuditEntry":
        return cls(**{k: row[k] for k in row.keys()})
