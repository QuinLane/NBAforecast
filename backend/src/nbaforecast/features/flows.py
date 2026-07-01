"""Prefect refresh tasks — feature-engineering.md Prompt 5 (+ T3.9 RAPM wiring).

Run by ``ingestion/flows/ingest.py::ingest_daily`` right after it lands a day's games, so the
gold feature tables never drift behind silver for more than one nightly cycle. Both refreshes
pass the current ``player_rapm`` snapshots through to the materializer so ``team_orapm``/
``team_drapm`` and ``player_rapm`` are filled leakage-safely (models/rapm/aggregate.py).
"""

import logging

from prefect import task

from nbaforecast.features.materialize import (
    materialize_player_game_features,
    materialize_team_game_features,
    upsert_player_game_features,
    upsert_team_game_features,
    write_player_game_features_parquet,
    write_team_game_features_parquet,
)
from nbaforecast.storage.database import get_sessionmaker
from nbaforecast.storage.models import (
    Game,
    Player,
    PlayerGameStats,
    PlayerRapm,
    Team,
    TeamGameStats,
)
from nbaforecast.storage.repositories import load_table_as_dataframe

logger = logging.getLogger(__name__)


@task(name="refresh-team-game-features")
async def refresh_team_game_features(game_ids: list[str]) -> int:
    """Incrementally refresh ``features_team_game`` for ``game_ids`` (Postgres + Parquet).

    Recomputes from the full games/team_game_stats history (so rolling and season-to-date
    values stay correct) but only writes rows for ``game_ids`` — the games just landed by
    ``ingest_daily``. ``team_orapm``/``team_drapm`` are filled from the latest ``player_rapm``
    snapshots. A no-op (no DB round trip) when ``game_ids`` is empty.
    """
    if not game_ids:
        return 0
    async with get_sessionmaker()() as session:
        games = await load_table_as_dataframe(session, Game)
        team_game_stats = await load_table_as_dataframe(session, TeamGameStats)
        teams = await load_table_as_dataframe(session, Team)
        player_game_stats = await load_table_as_dataframe(session, PlayerGameStats)
        rapm_snapshots = await load_table_as_dataframe(session, PlayerRapm)
        features = materialize_team_game_features(
            games,
            team_game_stats,
            teams,
            game_ids=game_ids,
            player_game_stats=player_game_stats,
            rapm_snapshots=rapm_snapshots,
        )
        count = await upsert_team_game_features(session, features)
        await session.commit()
        write_team_game_features_parquet(features)
    logger.info("refreshed features_team_game for %d game(s), %d rows", len(game_ids), count)
    return count


@task(name="refresh-player-game-features")
async def refresh_player_game_features(game_ids: list[str]) -> int:
    """Incrementally refresh ``features_player_game`` for ``game_ids`` (Postgres + Parquet).

    Mirrors ``refresh_team_game_features``: recomputes from full history for correctness but
    only writes the landed games, filling ``player_rapm`` from the latest snapshots. A no-op
    when ``game_ids`` is empty.
    """
    if not game_ids:
        return 0
    async with get_sessionmaker()() as session:
        games = await load_table_as_dataframe(session, Game)
        player_game_stats = await load_table_as_dataframe(session, PlayerGameStats)
        team_game_stats = await load_table_as_dataframe(session, TeamGameStats)
        players = await load_table_as_dataframe(session, Player)
        rapm_snapshots = await load_table_as_dataframe(session, PlayerRapm)
        features = materialize_player_game_features(
            games,
            player_game_stats,
            team_game_stats,
            players,
            game_ids=game_ids,
            rapm_snapshots=rapm_snapshots,
        )
        count = await upsert_player_game_features(session, features)
        await session.commit()
        write_player_game_features_parquet(features)
    logger.info("refreshed features_player_game for %d game(s), %d rows", len(game_ids), count)
    return count
