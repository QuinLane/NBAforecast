"""Idempotent upsert repositories for the silver tables (data-pipeline.md Prompt 3).

Every load is keyed on a natural key so re-running a flow never duplicates rows. Most tables
upsert via ``INSERT ... ON CONFLICT DO UPDATE``; ``possessions`` has only a surrogate key, so it
is made idempotent by replacing all rows for a game (delete-by-game then insert).
"""

import logging
from typing import Any

from sqlalchemy import delete, func
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
