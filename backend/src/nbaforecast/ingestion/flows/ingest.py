"""Prefect flows: full-era backfill + nightly daily ingest (data-pipeline.md Prompt 4).

The flows compose the :mod:`nbaforecast.ingestion.pipeline` steps with Prefect task retries and a
shared concurrency tag (``stats-nba``). Games already fully ingested are skipped via the
``ingested_games`` checkpoint, so a crashed backfill resumes instead of restarting.
"""

import logging
from datetime import date

from prefect import flow, task

from nbaforecast.features.flows import refresh_team_game_features
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

# Earliest comprehensive play-by-play/shot season on stats.nba.com (roadmap §5, M1 DoD).
PBP_ERA_START_YEAR = 1996
# Season types backfilled across the era.
ERA_SEASON_TYPES = ("Regular Season", "Playoffs")

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


async def _run_games(metas: list[GameMeta]) -> list[GameMeta]:
    """Ingest the games not already complete; returns the ones actually processed."""
    async with get_sessionmaker()() as session:
        complete = await list_complete_games(session, [m.game_id for m in metas])
    pending = [m for m in metas if m.game_id not in complete]
    logger.info("%d games pending of %d", len(pending), len(metas))
    for meta in pending:
        await ingest_game_task(meta)
    return pending


@flow(name="backfill-season")
async def backfill_season(season: str, season_type: str = "Regular Season") -> int:
    """Backfill an entire season (schedule + every game), resumable via the checkpoint."""
    store = ObjectStore()
    store.ensure_bucket()
    async with get_sessionmaker()() as session:
        metas = await ingest_schedule(session, store, season, season_type)
        await session.commit()
    return len(await _run_games(metas))


@flow(name="ingest-daily")
async def ingest_daily(day: str | None = None) -> int:
    """Ingest finished games for one date (defaults to today); run nightly by the deployment.

    After landing the games, triggers an incremental refresh of ``features_team_game`` for just
    the games processed (feature-engineering.md Prompt 5) — rolling/season-to-date features stay
    correct because the refresh recomputes from full history, it just narrows what gets written.
    """
    target = date.fromisoformat(day) if day else date.today()
    season = season_for_date(target)
    stamp = target.strftime("%m/%d/%Y")
    store = ObjectStore()
    store.ensure_bucket()
    async with get_sessionmaker()() as session:
        metas = await ingest_schedule(session, store, season, date_from=stamp, date_to=stamp)
        await session.commit()
    processed = await _run_games(metas)
    await refresh_team_game_features([m.game_id for m in processed])
    return len(processed)


def _current_season_start_year() -> int:
    return int(season_for_date(date.today())[:4])


@flow(name="backfill-era")
async def backfill_era(
    start_year: int = PBP_ERA_START_YEAR,
    end_year: int | None = None,
    season_types: tuple[str, ...] = ERA_SEASON_TYPES,
) -> int:
    """Backfill every season from ``start_year`` through ``end_year`` (default: present).

    Resumable: each season's games are skipped when the checkpoint already marks them complete,
    so re-running after an interruption continues where it left off. Returns games processed.
    """
    end_year = end_year if end_year is not None else _current_season_start_year()
    total = 0
    for year in range(start_year, end_year + 1):
        season = f"{year}-{(year + 1) % 100:02d}"
        for season_type in season_types:
            logger.info("backfilling %s (%s)", season, season_type)
            total += await backfill_season(season, season_type)
    logger.info("era backfill processed %d games", total)
    return total
