"""Write silver DataFrames to the partitioned Parquet analytical store (data-pipeline.md §4).

Layout: ``{parquet_root}/{table}/season_start_year={YYYY}/part-{partition_key}.parquet``. The
deterministic part-file name (``partition_key``, typically the ``game_id``) makes re-runs
idempotent — re-writing the same key overwrites the same file instead of appending duplicates.
"""

import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from nbaforecast.config.settings import get_settings
from nbaforecast.storage.parquet_schemas import PARTITION_COLUMN, SILVER_PARQUET_SCHEMAS

logger = logging.getLogger(__name__)


def write_parquet(
    table: str,
    df: pd.DataFrame,
    season_start_year: int,
    partition_key: str,
    root: str | None = None,
) -> Path:
    """Write ``df`` to the Parquet partition for ``season_start_year`` and return the file path.

    Args:
        table: Silver table name (must have a registered pyarrow schema).
        df: Rows to write (silver columns; the partition column is added here).
        season_start_year: Partition value.
        partition_key: Deterministic part-file identifier (e.g. ``game_id``) for idempotency.
        root: Override the configured ``parquet_root`` (used in tests).
    """
    # The partition column lives in the hive directory name, not in the file, so reads via the
    # dataset API reconstruct it without a type clash against the in-file column.
    schema = SILVER_PARQUET_SCHEMAS[table]
    file_fields = [f for f in schema if f.name != PARTITION_COLUMN]
    file_schema = pa.schema(file_fields)
    names = [f.name for f in file_fields]
    arrow = pa.Table.from_pandas(df[names], schema=file_schema, preserve_index=False)

    base = (
        Path(root or get_settings().parquet_root)
        / table
        / f"{PARTITION_COLUMN}={season_start_year}"
    )
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"part-{partition_key}.parquet"
    pq.write_table(arrow, path)  # type: ignore[no-untyped-call]
    logger.debug("wrote %d rows to %s", len(df), path)
    return path
