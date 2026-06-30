"""Idempotent upsert repositories for the silver tables (data-pipeline.md Prompt 3).

Every load is keyed on a natural key so re-running a flow never duplicates rows. Most tables
upsert via ``INSERT ... ON CONFLICT DO UPDATE``; ``possessions`` has only a surrogate key, so it
is made idempotent by replacing all rows for a game (delete-by-game then insert).
"""

import logging
import math
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.storage.database import Base

logger = logging.getLogger(__name__)

# Silver table → natural-key columns used as the ON CONFLICT target.
UPSERT_KEYS: dict[str, tuple[str, ...]] = {
    "games": ("game_id",),
    "team_game_stats": ("game_id", "team_id"),
    "player_game_stats": ("game_id", "player_id"),
    "play_by_play": ("game_id", "event_num"),
    "shots": ("game_id", "event_num"),
}

# Tables with no natural unique key — replaced wholesale per game instead.
REPLACE_BY_GAME: frozenset[str] = frozenset({"possessions"})


def clean_db_value(value: Any) -> Any:
    """Convert a pandas/numpy scalar to a DB-friendly Python type (``NaN`` -> ``None``)."""
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float | np.floating):
        if math.isnan(float(value)):
            return None
        return int(value) if float(value).is_integer() else float(value)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def to_db_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame -> list of DB row dicts with native Python types and NULLs."""
    return [{str(k): clean_db_value(v) for k, v in row.items()} for row in df.to_dict("records")]


async def load_table_as_dataframe(session: AsyncSession, model: type[Base]) -> pd.DataFrame:
    """Read every row of ``model`` into a DataFrame (one-off script / batch-job use, not request
    serving). Selects the underlying ``Table`` directly so the result is plain columns, not ORM
    instances.
    """
    rows = (await session.execute(select(model.__table__))).mappings().all()
    return pd.DataFrame(rows)


async def upsert_rows(
    session: AsyncSession,
    model: type[Base],
    rows: list[dict[str, Any]],
    conflict_columns: tuple[str, ...],
) -> int:
    """Upsert ``rows`` into ``model`` on ``conflict_columns``; returns rows affected.

    On conflict, every non-key column is overwritten (``created_at`` is preserved and
    ``updated_at`` is refreshed to ``now()`` when present).
    """
    if not rows:
        return 0
    stmt = insert(model).values(rows)
    columns = {c.name for c in model.__table__.columns}
    update_set = {
        name: stmt.excluded[name]
        for name in columns
        if name not in conflict_columns and name not in {"created_at", "updated_at"}
    }
    if "updated_at" in columns:
        update_set["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=list(conflict_columns), set_=update_set)
    await session.execute(stmt)
    logger.debug("upserted %d rows into %s", len(rows), model.__tablename__)
    return len(rows)


async def replace_game_rows(
    session: AsyncSession,
    model: type[Base],
    game_id: str,
    rows: list[dict[str, Any]],
) -> int:
    """Delete rows for ``game_id`` then insert ``rows`` (idempotent for surrogate-key tables)."""
    await session.execute(delete(model).where(model.game_id == game_id))  # type: ignore[attr-defined]
    if rows:
        await session.execute(insert(model).values(rows))
    logger.debug("replaced %d rows for game %s in %s", len(rows), game_id, model.__tablename__)
    return len(rows)
