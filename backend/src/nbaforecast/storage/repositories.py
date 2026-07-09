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
from sqlalchemy import ColumnElement, delete, func, select
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
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def to_db_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame -> list of DB row dicts with native Python types and NULLs."""
    return [{str(k): clean_db_value(v) for k, v in row.items()} for row in df.to_dict("records")]


async def load_table_as_dataframe(
    session: AsyncSession,
    model: type[Base],
    *,
    where: list[ColumnElement[bool]] | None = None,
) -> pd.DataFrame:
    """Read rows of ``model`` into a DataFrame. Selects the underlying ``Table`` directly so the
    result is plain columns, not ORM instances.

    ``where`` scopes the load (e.g. to one season's games) — essential on the request path, where
    a full-table load doesn't scale as history accumulates. Batch jobs (``features/flows.py``'s
    refresh) still load the whole table for full rolling/Elo context.

    ``Numeric``/``DECIMAL`` columns come back from the DBAPI as ``decimal.Decimal`` (an
    object-dtype column, with plain Python ``None`` for ``NULL`` rather than ``NaN``) — every
    primitive/feature function downstream assumes ordinary float64 + ``NaN`` semantics, so those
    columns are coerced here rather than at every call site.
    """
    stmt = select(model.__table__)
    if where is not None:
        stmt = stmt.where(*where)
    rows = (await session.execute(stmt)).mappings().all()
    return _coerce_decimal_columns(pd.DataFrame(rows))


def _coerce_decimal_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in df.select_dtypes(include="object").columns:
        sample = df[column].dropna()
        if sample.empty or isinstance(sample.iloc[0], str):
            # Plain Python strings (game_id, status, abbreviation …) are never Decimal —
            # skip them so that leading-zero IDs like "0022300001" aren't silently truncated
            # to the integer 22300001, which would break every downstream string equality filter.
            continue
        try:
            df[column] = pd.to_numeric(df[column])
        except (TypeError, ValueError):
            continue
    return df


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
