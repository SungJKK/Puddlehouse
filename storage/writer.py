import uuid, time
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from config import config
from catalog.manager import CatalogManager

catalog = CatalogManager()

def write_parquet(
    df:         pd.DataFrame,
    zone:       str,
    entity:     str,
    partition_cols: list[str] = None,
    run_id:     str = None,
    job_name:   str = "manual",
    source_id:  str = "external",
) -> list[str]:
    """
    Write a DataFrame to the correct zone/entity path as parquet.
    Updates the catalog automatically.
    Returns list of written file paths.
    """
    run_id   = run_id or str(uuid.uuid4())
    out_dir  = config.data_root / zone / entity
    out_dir.mkdir(parents=True, exist_ok=True)

    table    = pa.Table.from_pandas(df)
    schema   = [{"name": f.name, "type": str(f.type)} for f in table.schema]
    table_id = catalog.register_table(zone, entity, schema)

    written_files = []

    if partition_cols:
        # Write partitioned dataset
        pq.write_to_dataset(
            table,
            root_path=str(out_dir),
            partition_cols=partition_cols,
            compression="snappy",
        )
        # Discover written files for catalog registration
        written_files = [str(p) for p in out_dir.rglob("*.parquet")]
        # Register each partition
        for f in written_files:
            parts = Path(f).parent
            for part in parts.relative_to(out_dir).parts:
                if "=" in part:
                    key, val = part.split("=", 1)
                    catalog.register_partition(table_id, key, val, f, len(df))
    else:
        # Single file write
        fname = out_dir / f"{run_id}.parquet"
        pq.write_table(table, fname, compression="snappy")
        written_files = [str(fname)]

    byte_size = sum(Path(f).stat().st_size for f in written_files)
    catalog.create_snapshot(table_id, written_files, len(df), byte_size)
    catalog.record_lineage(source_id, table_id, job_name, run_id, 0, len(df))

    return written_files


def read_parquet(zone: str, entity: str, filters=None) -> pd.DataFrame:
    """
    Read all parquet files for a zone/entity into a DataFrame.
    Optionally apply pyarrow filters: [('date', '=', '2025-01-01')]
    """
    path = config.data_root / zone / entity
    if not path.exists():
        raise FileNotFoundError(f"No data at {path}")
    return pq.read_table(str(path), filters=filters).to_pandas()
