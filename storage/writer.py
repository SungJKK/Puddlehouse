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


def _compute_table_stats(table: pa.Table, column_id_map: dict[str, str]) -> list[dict]:
    """
    Compute aggregate column stats from an in-memory Arrow table.
    Returns [{"column_id", "null_count", "min_value", "max_value"}]
    """
    result = []
    for i, field in enumerate(table.schema):
        col_id = column_id_map.get(field.name)
        if not col_id:
            continue
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
            "column_id": col_id,
            "null_count": col.null_count,
            "min_value":  min_val,
            "max_value":  max_val,
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
    Updates the catalog (table, columns, snapshot, files, stats, lineage) automatically.
    Returns list of written file paths.
    """
    run_id  = run_id or str(uuid.uuid4())
    out_dir = config.data_root / zone / entity
    out_dir.mkdir(parents=True, exist_ok=True)

    arrow_table = pa.Table.from_pandas(df)
    schema      = [{"name": f.name, "type": str(f.type)} for f in arrow_table.schema]

    table_id = catalog.register_table(zone, entity)

    written_files: list[str] = []

    if partition_cols:
        pq.write_to_dataset(
            arrow_table,
            root_path=str(out_dir),
            partition_cols=partition_cols,
            compression="snappy",
        )
        written_files = [str(p) for p in out_dir.rglob("*.parquet")]
        for f in written_files:
            for part in Path(f).parent.relative_to(out_dir).parts:
                if "=" in part:
                    key, val = part.split("=", 1)
                    catalog.register_partition(table_id, key, val, f, len(df))
    else:
        fname = out_dir / f"{run_id}.parquet"
        pq.write_table(arrow_table, fname, compression="snappy")
        written_files = [str(fname)]

    # Build file metadata for snapshot
    files_meta = [
        {
            "file_path": f,
            "row_count": pq.ParquetFile(f).metadata.num_rows,
            "byte_size": Path(f).stat().st_size,
        }
        for f in written_files
    ]
    byte_size = sum(m["byte_size"] for m in files_meta)

    snapshot_id, version, file_id_map = catalog.create_snapshot(
        table_id, files_meta, len(df), byte_size
    )
    column_id_map = catalog.register_columns(table_id, version, schema)

    # Per-file column stats (enables file-level predicate pushdown)
    for file_path, file_id in file_id_map.items():
        file_stats = _read_file_stats(file_path)
        col_stats  = [
            {
                "column_id":         column_id_map[s["column_name"]],
                "value_count":       s["value_count"],
                "null_count":        s["null_count"],
                "min_value":         s["min_value"],
                "max_value":         s["max_value"],
                "column_size_bytes": s["column_size_bytes"],
            }
            for s in file_stats
            if s["column_name"] in column_id_map
        ]
        catalog.write_file_column_stats(file_id, table_id, col_stats)

    # Aggregate table-level column stats
    catalog.upsert_column_stats(
        table_id,
        _compute_table_stats(arrow_table, column_id_map)
    )

    catalog.record_lineage(source_id, table_id, job_name, run_id, 0, len(df))

    return written_files


def read_parquet(zone: str, entity: str, filters=None) -> pd.DataFrame:
    """
    Read all Parquet files for a zone/entity into a DataFrame.
    Optionally apply PyArrow filters: [('date', '=', '2025-01-01')]
    """
    path = config.data_root / zone / entity
    if not path.exists():
        raise FileNotFoundError(f"No data at {path}")
    return pq.read_table(str(path), filters=filters).to_pandas()
