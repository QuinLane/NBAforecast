"""Prefect flows: full-era backfill + nightly daily ingest (data-pipeline.md Prompt 4).

The flows compose the :mod:`nbaforecast.ingestion.pipeline` steps with Prefect task retries and a
shared concurrency tag (``stats-nba``). Games already fully ingested are skipped via the
``ingested_games`` checkpoint, so a crashed backfill resumes instead of restarting.
"""

import logging
from datetime import date

from prefect import flow, task

from nbaforecast.ingestion.checkpoint import list_complete_games, upsert_checkpoint
from nbaforecast.ingestion.pipeline import (
    GameMeta,
    ingest_game,
    ingest_schedule,
    season_for_date,
)
from nbaforecast.storage.database import get_sessionmaker
from nbaforecast.storage.object_store import ObjectStore

logger = logging.getLogger(__name__)

# Retry transient stats.nba.com failures with growing backoff; the throttle paces calls.
_RETRY_DELAYS: list[float] = [10, 30, 60, 120]


@task(retries=len(_RETRY_DELAYS), retry_delay_seconds=_RETRY_DELAYS, tags=["stats-nba"])
async def ingest_game_task(meta: GameMeta) -> None:
    """Ingest one game and checkpoint it, in its own transaction."""
    store = ObjectStore()
    async with get_sessionmaker()() as session:
        done = await ingest_game(session, store, meta)
        await upsert_checkpoint(session, meta.game_id, done)
        await session.commit()


async def _run_games(metas: list[GameMeta]) -> int:
    """Ingest the games not already complete; returns how many were processed."""
    async with get_sessionmaker()() as session:
        complete = await list_complete_games(session, [m.game_id for m in metas])
    pending = [m for m in metas if m.game_id not in complete]
    logger.info("%d games pending of %d", len(pending), len(metas))
    for meta in pending:
        await ingest_game_task(meta)
    return len(pending)


@flow(name="backfill-season")
async def backfill_season(season: str, season_type: str = "Regular Season") -> int:
    """Backfill an entire season (schedule + every game), resumable via the checkpoint."""
    store = ObjectStore()
    store.ensure_bucket()
    async with get_sessionmaker()() as session:
        metas = await ingest_schedule(session, store, season, season_type)
        await session.commit()
    return await _run_games(metas)


@flow(name="ingest-daily")
async def ingest_daily(day: str | None = None) -> int:
    """Ingest finished games for one date (defaults to today); run nightly by the deployment."""
    target = date.fromisoformat(day) if day else date.today()
    season = season_for_date(target)
    stamp = target.strftime("%m/%d/%Y")
    store = ObjectStore()
    store.ensure_bucket()
    async with get_sessionmaker()() as session:
        metas = await ingest_schedule(session, store, season, date_from=stamp, date_to=stamp)
        await session.commit()
    return await _run_games(metas)
