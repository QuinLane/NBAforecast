"""Unit tests for partitioned Parquet writes (local filesystem, no S3)."""

from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from nbaforecast.storage.parquet_io import write_parquet


def _games_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "0022300001",
                "season": "2023-24",
                "season_type": "Regular Season",
                "game_date": pd.Timestamp("2023-10-24").date(),
                "game_datetime": None,
                "home_team_id": 1610612747,
                "away_team_id": 1610612738,
                "home_score": 110,
                "away_score": 105,
                "status": "final",
                "num_periods": 4,
            }
        ]
    )


def test_write_parquet_partition_path_and_contents(tmp_path: Path) -> None:
    path = write_parquet("games", _games_df(), 2023, partition_key="0022300001", root=str(tmp_path))
    assert path == tmp_path / "games" / "season_start_year=2023" / "part-0022300001.parquet"
    assert path.exists()

    # The partition column is stored in the path, not the file, and reconstructed on read.
    table = pq.read_table(path)
    assert table.num_rows == 1
    assert table.column("game_id").to_pylist() == ["0022300001"]
    assert table.column("season_start_year").to_pylist() == [2023]

    # Confirm the same via the dataset API across the table root.
    dataset = ds.dataset(tmp_path / "games", partitioning="hive").to_table()
    assert dataset.column("season_start_year").to_pylist() == [2023]


def test_write_parquet_is_idempotent_for_same_key(tmp_path: Path) -> None:
    write_parquet("games", _games_df(), 2023, partition_key="0022300001", root=str(tmp_path))
    write_parquet("games", _games_df(), 2023, partition_key="0022300001", root=str(tmp_path))
    part_dir = tmp_path / "games" / "season_start_year=2023"
    assert len(list(part_dir.glob("*.parquet"))) == 1  # same key overwrote, no duplicate file
