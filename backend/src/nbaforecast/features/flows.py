"""Prefect refresh task — feature-engineering.md Prompt 5.

Run by ``ingestion/flows/ingest.py::ingest_daily`` right after it lands a day's games, so
``features_team_game`` never drifts behind silver for more than one nightly cycle.
"""

import logging

from prefect import task

from nbaforecast.features.materialize import (
    materialize_team_game_features,
    upsert_team_game_features,
    write_team_game_features_parquet,
)
from nbaforecast.storage.database import get_sessionmaker
from nbaforecast.storage.models import Game, Team, TeamGameStats
from nbaforecast.storage.repositories import load_table_as_dataframe

logger = logging.getLogger(__name__)


@task(name="refresh-team-game-features")
async def refresh_team_game_features(game_ids: list[str]) -> int:
    """Incrementally refresh ``features_team_game`` for ``game_ids`` (Postgres + Parquet).

    Recomputes from the full games/team_game_stats history (so rolling and season-to-date
    values stay correct) but only writes rows for ``game_ids`` — the games just landed by
    ``ingest_daily``. A no-op (no DB round trip) when ``game_ids`` is empty.
    """
    if not game_ids:
        return 0
    async with get_sessionmaker()() as session:
        games = await load_table_as_dataframe(session, Game)
        team_game_stats = await load_table_as_dataframe(session, TeamGameStats)
        teams = await load_table_as_dataframe(session, Team)
        features = materialize_team_game_features(games, team_game_stats, teams, game_ids=game_ids)
        write_team_game_features_parquet(features)
        count = await upsert_team_game_features(session, features)
        await session.commit()
    logger.info("refreshed features_team_game for %d game(s), %d rows", len(game_ids), count)
    return count
