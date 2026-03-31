import uuid
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
from pathlib import Path
from config import config
from catalog.manager import CatalogManager

catalog = CatalogManager()


def _read_file_stats(file_path: str) -> list[dict]:
    """
    Read per-column stats from a Parquet file's footer metadata.
    Aggregates across row groups without loading any data.
    Returns [{"column_name", "value_count", "null_count", "min_value", "max_value", "column_size_bytes"}]
    """
    pf = pq.ParquetFile(file_path)
    totals: dict[str, dict] = {}

    for rg_i in range(pf.metadata.num_row_groups):
        rg = pf.metadata.row_group(rg_i)
        for col_i in range(rg.num_columns):
            chunk = rg.column(col_i)
            name  = chunk.path_in_schema
            s     = chunk.statistics

            if name not in totals:
                totals[name] = {
                    "column_name":       name,
                    "value_count":       0,
                    "null_count":        0,
                    "mins":              [],
                    "maxes":             [],
                    "column_size_bytes": 0,
                }
            totals[name]["value_count"]       += rg.num_rows
            totals[name]["column_size_bytes"] += chunk.total_compressed_size
            if s:
                totals[name]["null_count"] += s.null_count or 0
                if s.has_min_max:
                    try:
                        totals[name]["mins"].append(s.min)
                        totals[name]["maxes"].append(s.max)
                    except Exception:
                        pass

    return [
        {
            "column_name":       name,
            "value_count":       d["value_count"],
            "null_count":        d["null_count"],
            "min_value":         str(min(d["mins"]))  if d["mins"]  else None,
            "max_value":         str(max(d["maxes"])) if d["maxes"] else None,
            "column_size_bytes": d["column_size_bytes"],
        }
        for name, d in totals.items()
    ]


def _compute_table_stats(table: pa.Table) -> list[dict]:
    """
    Compute aggregate column stats from an in-memory Arrow table.
    Returns [{"column_name", "null_count", "min_value", "max_value"}]
    """
    result = []
    for i, field in enumerate(table.schema):
        col      = table.column(i)
        non_null = col.drop_null()
        min_val  = max_val = None
        if len(non_null) > 0:
            try:
                min_val = str(pc.min(non_null).as_py())
                max_val = str(pc.max(non_null).as_py())
            except Exception:
                pass
        result.append({
            "column_name": field.name,
            "null_count":  col.null_count,
            "min_value":   min_val,
            "max_value":   max_val,
        })
    return result


def write_parquet(
    df:             pd.DataFrame,
    zone:           str,
    entity:         str,
    partition_cols: list[str] = None,
    run_id:         str = None,
    job_name:       str = "manual",
    source_id:      str = "external",
) -> list[str]:
    """
    Write a DataFrame to the correct zone/entity path as Parquet.
    All catalog updates (table, snapshot, columns, stats, lineage, partitions)
    are committed atomically in a single SQLite transaction.
    Returns list of written file paths.
    """
    run_id  = run_id or str(uuid.uuid4())
    out_dir = config.data_root / zone / entity
    out_dir.mkdir(parents=True, exist_ok=True)

    arrow_table = pa.Table.from_pandas(df)
    schema      = [{"name": f.name, "type": str(f.type)} for f in arrow_table.schema]

    # ── 1. Write Parquet files to disk ────────────────────────────────
    written_files: list[str] = []
    partitions:    list[dict] = []

    if partition_cols:
        pq.write_to_dataset(
            arrow_table,
            root_path=str(out_dir),
            partition_cols=partition_cols,
            compression="snappy",
        )
        written_files = [str(p) for p in out_dir.rglob("*.parquet")]
        for f in written_files:
            file_row_count = pq.ParquetFile(f).metadata.num_rows
            for part in Path(f).parent.relative_to(out_dir).parts:
                if "=" in part:
                    key, val = part.split("=", 1)
                    partitions.append({"key": key, "val": val, "file_path": f, "row_count": file_row_count})
    else:
        fname = out_dir / f"{run_id}.parquet"
        pq.write_table(arrow_table, fname, compression="snappy")
        written_files = [str(fname)]

    # ── 2. Gather file metadata and stats (I/O before the transaction) ─
    files_meta = [
        {
            "file_path": f,
            "row_count": pq.ParquetFile(f).metadata.num_rows,
            "byte_size": Path(f).stat().st_size,
        }
        for f in written_files
    ]
    byte_size = sum(m["byte_size"] for m in files_meta)

    file_col_stats  = {f: _read_file_stats(f) for f in written_files}
    table_col_stats = _compute_table_stats(arrow_table)

    # ── 3. Validate schema evolution, then atomic catalog commit ──────
    existing_snap = catalog.get_latest_snapshot(f"{zone}.{entity}")
    cumulative_row_count = (existing_snap.row_count if existing_snap else 0) + len(df)

    catalog.validate_schema_evolution(f"{zone}.{entity}", schema)
    catalog.commit_write(
        zone=zone,
        entity=entity,
        files_meta=files_meta,
        row_count=cumulative_row_count,
        byte_size=byte_size,
        schema=schema,
        file_col_stats=file_col_stats,
        table_col_stats=table_col_stats,
        source_id=source_id,
        job_name=job_name,
        run_id=run_id,
        partitions=partitions,
    )

    return written_files


def compact(zone: str, entity: str) -> str:
    """
    Merge all Parquet files from the latest snapshot into a single file
    and commit it as a new snapshot. Old snapshots and their files are
    left on disk untouched so time travel still works.
    Returns the path of the compacted file.
    Raises ValueError if the table has no snapshots yet.
    """
    table_id = f"{zone}.{entity}"
    snap = catalog.get_latest_snapshot(table_id)
    if snap is None:
        raise ValueError(f"No snapshots found for {table_id} — nothing to compact")

    files = catalog.get_table_files_at_version(table_id, snap.version)
    if not files:
        raise ValueError(f"No files registered for {table_id} at version {snap.version}")

    # ── 1. Read full table state into one Arrow table ─────────────────
    arrow_table = pq.read_table([f.file_path for f in files])

    # ── 2. Write merged file ──────────────────────────────────────────
    out_dir        = config.data_root / zone / entity
    out_dir.mkdir(parents=True, exist_ok=True)
    compacted_path = str(out_dir / f"compacted-{uuid.uuid4()}.parquet")
    pq.write_table(arrow_table, compacted_path, compression="snappy")

    # ── 3. Gather metadata and stats ──────────────────────────────────
    schema     = [{"name": f.name, "type": str(f.type)} for f in arrow_table.schema]
    row_count  = len(arrow_table)
    byte_size  = Path(compacted_path).stat().st_size
    files_meta = [{"file_path": compacted_path, "row_count": row_count, "byte_size": byte_size}]

    # ── 4. Atomic catalog commit ──────────────────────────────────────
    catalog.commit_write(
        zone=zone,
        entity=entity,
        files_meta=files_meta,
        row_count=row_count,
        byte_size=byte_size,
        schema=schema,
        file_col_stats={compacted_path: _read_file_stats(compacted_path)},
        table_col_stats=_compute_table_stats(arrow_table),
        source_id=f"{table_id}@v{snap.version}",
        job_name="compact",
        run_id=str(uuid.uuid4()),
    )

    return compacted_path


def read_parquet_at_version(zone: str, entity: str, version: int, filters=None) -> pd.DataFrame:
    """
    Read the exact set of Parquet files registered for a specific snapshot version.
    Raises ValueError if the version does not exist for this table.
    """
    table_id = f"{zone}.{entity}"
    snap = catalog.get_snapshot_at_version(table_id, version)
    if snap is None:
        raise ValueError(f"No snapshot at version {version} for {table_id}")
    files = catalog.get_table_files_at_version(table_id, version)
    if not files:
        raise ValueError(f"No files found for {table_id} at version {version}")
    return pq.read_table([f.file_path for f in files], filters=filters).to_pandas()


def read_parquet(zone: str, entity: str, filters=None) -> pd.DataFrame:
    """
    Read all Parquet files for a zone/entity into a DataFrame.
    Optionally apply PyArrow filters: [('date', '=', '2025-01-01')]
    """
    path = config.data_root / zone / entity
    if not path.exists():
        raise FileNotFoundError(f"No data at {path}")
    return pq.read_table(str(path), filters=filters).to_pandas()
