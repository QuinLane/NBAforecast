"""Silver load step: validate → quarantine-and-raise on failure → upsert + Parquet on success.

This is the single choke point every entity passes through (data-pipeline.md Prompt 3, §6). Bad
data is never loaded: a validation failure writes the offending raw payload to ``quarantine/``
and re-raises so the Prefect flow fails loudly.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.errors import DataValidationError, IngestionError
from nbaforecast.ingestion.schemas import validate
from nbaforecast.storage.database import Base
from nbaforecast.storage.models import (
    Game,
    PlayByPlay,
    PlayerGameStats,
    Possession,
    Shot,
    TeamGameStats,
)
from nbaforecast.storage.object_store import Json, ObjectStore
from nbaforecast.storage.parquet_io import write_parquet
from nbaforecast.storage.repositories import (
    REPLACE_BY_GAME,
    UPSERT_KEYS,
    replace_game_rows,
    to_db_records,
    upsert_rows,
)

logger = logging.getLogger(__name__)

TABLE_MODELS: dict[str, type[Base]] = {
    "games": Game,
    "team_game_stats": TeamGameStats,
    "player_game_stats": PlayerGameStats,
    "play_by_play": PlayByPlay,
    "shots": Shot,
    "possessions": Possession,
}


@dataclass(slots=True)
class LoadResult:
    """Outcome of loading one silver batch."""

    table: str
    rows: int
    parquet_path: Path | None


async def load_silver(
    session: AsyncSession,
    store: ObjectStore,
    table: str,
    df: pd.DataFrame,
    *,
    season_start_year: int,
    partition_key: str,
    raw_payload: Json,
    source: str,
    endpoint: str,
    game_id: str | None = None,
) -> LoadResult:
    """Validate and load one silver batch to Postgres + Parquet.

    Args:
        table: Target silver table.
        df: Parsed silver rows.
        season_start_year: Parquet partition value.
        partition_key: Deterministic Parquet part-file id (game_id, or the season for schedule).
        raw_payload: The source payload, quarantined verbatim if validation fails.
        source/endpoint: Bronze coordinates, used for the quarantine key.
        game_id: Required for replace-by-game tables (e.g. possessions).

    Raises:
        DataValidationError: re-raised after quarantining, on validation failure.
    """
    model = TABLE_MODELS[table]
    try:
        validate(table, df)
    except DataValidationError as err:
        store.quarantine(raw_payload, str(err), source, endpoint, partition_key)
        logger.error("quarantined %s/%s: validation failed", source, endpoint)
        raise

    rows = to_db_records(df)
    if table in REPLACE_BY_GAME:
        if game_id is None:
            raise IngestionError(f"{table} load requires game_id for idempotent replace")
        await replace_game_rows(session, model, game_id, rows)
    else:
        await upsert_rows(session, model, rows, UPSERT_KEYS[table])

    parquet_path = (
        write_parquet(table, df, season_start_year, partition_key=partition_key)
        if not df.empty
        else None
    )
    return LoadResult(table=table, rows=len(rows), parquet_path=parquet_path)
