"""Ingestion checkpoint — tracks which entities of each game are loaded (resumable backfill).

Backed by the ``ingested_games`` table. Backfill consults :func:`is_complete` to skip games that
are already fully ingested, so a crashed run resumes instead of restarting (data-pipeline.md §5).
"""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.storage.models import IngestedGame

logger = logging.getLogger(__name__)

# The per-game entities a full ingest must land.
REQUIRED_ENTITIES: frozenset[str] = frozenset({"boxscore", "pbp", "shots", "possessions"})


async def get_checkpoint(session: AsyncSession, game_id: str) -> set[str]:
    """Return the set of entities already ingested for ``game_id`` (empty if none)."""
    row = await session.get(IngestedGame, game_id)
    if row is None:
        return set()
    return set(row.entities_done.get("entities", []))


async def is_complete(
    session: AsyncSession, game_id: str, required: frozenset[str] = REQUIRED_ENTITIES
) -> bool:
    """True if every ``required`` entity has been ingested for ``game_id``."""
    return required <= await get_checkpoint(session, game_id)


async def list_complete_games(
    session: AsyncSession, game_ids: list[str], required: frozenset[str] = REQUIRED_ENTITIES
) -> set[str]:
    """Return which of ``game_ids`` are already fully ingested (single query)."""
    if not game_ids:
        return set()
    result = await session.execute(
        select(IngestedGame.game_id, IngestedGame.entities_done).where(
            IngestedGame.game_id.in_(game_ids)
        )
    )
    return {gid for gid, done in result.all() if required <= set(done.get("entities", []))}


async def upsert_checkpoint(session: AsyncSession, game_id: str, entities: set[str]) -> None:
    """Record (idempotently) the union of ingested entities for ``game_id``."""
    existing = await get_checkpoint(session, game_id)
    merged = sorted(existing | entities)
    stmt = insert(IngestedGame).values(game_id=game_id, entities_done={"entities": merged})
    stmt = stmt.on_conflict_do_update(
        index_elements=["game_id"],
        set_={"entities_done": {"entities": merged}, "ingested_at": stmt.excluded.ingested_at},
    )
    await session.execute(stmt)
    logger.debug("checkpoint %s: %s", game_id, merged)
