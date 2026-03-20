from dataclasses import dataclass
from typing import Optional


@dataclass
class TableMeta:
    table_id:   str
    name:       str
    zone:       str
    entity:     str
    location:   str
    owner:      str = "system"
    row_count:  int = 0
    is_active:  int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "TableMeta":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class Column:
    column_id:          str
    table_id:           str
    column_name:        str
    column_type:        str
    column_order:       int
    nulls_allowed:      int = 1
    default_value:      Optional[str] = None
    added_at_version:   int = 1
    dropped_at_version: Optional[int] = None

    @classmethod
    def from_row(cls, row) -> "Column":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class Snapshot:
    snapshot_id: str
    table_id:    str
    version:     int
    row_count:   Optional[int] = None
    byte_size:   Optional[int] = None
    created_at:  Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Snapshot":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class CatalogFile:
    file_id:     str
    snapshot_id: str
    table_id:    str
    file_path:   str
    row_count:   Optional[int] = None
    byte_size:   Optional[int] = None

    @classmethod
    def from_row(cls, row) -> "CatalogFile":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class DeleteFile:
    delete_file_id:   str
    table_id:         str
    snapshot_id:      str
    file_id:          str
    delete_file_path: str
    delete_count:     Optional[int] = None
    byte_size:        Optional[int] = None
    created_at:       Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "DeleteFile":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class ColumnStats:
    table_id:   str
    column_id:  str
    null_count: int = 0
    min_value:  Optional[str] = None
    max_value:  Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "ColumnStats":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class FileColumnStats:
    file_id:           str
    table_id:          str
    column_id:         str
    value_count:       Optional[int] = None
    null_count:        int = 0
    min_value:         Optional[str] = None
    max_value:         Optional[str] = None
    column_size_bytes: Optional[int] = None

    @classmethod
    def from_row(cls, row) -> "FileColumnStats":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class View:
    view_id:             str
    view_name:           str
    zone:                str
    view_type:           str
    sql:                 str
    owner:               str = "system"
    created_at:          Optional[str] = None
    updated_at:          Optional[str] = None
    is_active:           int = 1
    last_refreshed_at:   Optional[str] = None
    refresh_snapshot_id: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "View":
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
