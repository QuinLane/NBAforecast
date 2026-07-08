"""Prefect flows: full-era backfill + nightly daily ingest (data-pipeline.md Prompt 4).

The flows compose the :mod:`nbaforecast.ingestion.pipeline` steps with Prefect task retries and a
shared concurrency tag (``stats-nba``). Games already fully ingested are skipped via the
``ingested_games`` checkpoint, so a crashed backfill resumes instead of restarting.
"""

import asyncio
import logging
from datetime import date

from prefect import flow, task

from nbaforecast.config.settings import get_settings
from nbaforecast.features.flows import refresh_team_game_features
from nbaforecast.ingestion.checkpoint import (
    list_complete_games,
    required_entities,
    upsert_checkpoint,
)
from nbaforecast.ingestion.pipeline import (
    GameMeta,
    ingest_game,
    ingest_schedule,
    season_for_date,
)
from nbaforecast.ingestion.seed import seed_reference_tables
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


async def _run_games(metas: list[GameMeta], *, label: str = "") -> list[GameMeta]:
    """Ingest the games not already complete; returns the ones that actually succeeded.

    Games run up to ``ingest_concurrency`` at a time (the shared request throttle still bounds
    the upstream call rate). A game that still fails after the task's retries is logged and
    skipped rather than failing the whole season (seen live at M3.5: one malformed boxscore
    payload killed a 1,225-game backfill). Failed games stay un-checkpointed, so the next run
    retries them. Progress is logged so a detached run is watchable via the log file.
    """
    # Every meta in a call is from one season, so one era-appropriate required set applies.
    required = required_entities(metas[0].season_start_year) if metas else None
    async with get_sessionmaker()() as session:
        complete = (
            await list_complete_games(session, [m.game_id for m in metas], required=required)
            if required is not None
            else set()
        )
    pending = [m for m in metas if m.game_id not in complete]
    total_pending = len(pending)
    logger.info("[backfill] %s: %d pending of %d games", label, total_pending, len(metas))

    concurrency = max(1, get_settings().ingest_concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    progress_lock = asyncio.Lock()
    failed: list[str] = []
    done = 0

    async def _ingest_one(meta: GameMeta) -> None:
        nonlocal done
        async with semaphore:
            try:
                await ingest_game_task(meta)
            except Exception:
                logger.exception(
                    "game %s failed after retries; continuing (next run will retry it)",
                    meta.game_id,
                )
                async with progress_lock:
                    failed.append(meta.game_id)
                return
        async with progress_lock:
            done += 1
            if done % 10 == 0 or done == total_pending:
                logger.info(
                    "[backfill] %s: %d/%d done, %d remaining",
                    label,
                    done,
                    total_pending,
                    total_pending - done,
                )

    await asyncio.gather(*(_ingest_one(meta) for meta in pending))
    if failed:
        logger.warning("[backfill] %s: %d game(s) failed this run: %s", label, len(failed), failed)
    return [m for m in pending if m.game_id not in set(failed)]


@flow(name="backfill-season")
async def backfill_season(season: str, season_type: str = "Regular Season") -> int:
    """Backfill an entire season (schedule + every game), resumable via the checkpoint."""
    store = ObjectStore()
    store.ensure_bucket()
    async with get_sessionmaker()() as session:
        await seed_reference_tables(session)
        metas = await ingest_schedule(session, store, season, season_type)
        await session.commit()
    return len(await _run_games(metas, label=f"{season} {season_type}"))


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
        await seed_reference_tables(session)
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
    steps = [
        (f"{year}-{(year + 1) % 100:02d}", season_type)
        for year in range(start_year, end_year + 1)
        for season_type in season_types
    ]
    for i, (season, season_type) in enumerate(steps, start=1):
        logger.info(
            "[backfill] === season %d/%d: %s %s (era total so far: %d games) ===",
            i,
            len(steps),
            season,
            season_type,
            total,
        )
        total += await backfill_season(season, season_type)
    logger.info("[backfill] era complete: %d games processed across %d seasons", total, len(steps))
    return total
