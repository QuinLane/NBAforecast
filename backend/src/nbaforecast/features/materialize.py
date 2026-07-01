"""Feature materialization — feature-engineering.md Prompt 5.

Builds the team-game feature table (T2.2), stamps it with the current ``feature_version``, and
writes it to both Postgres (``features_team_game``, serving) and Parquet (training), partitioned
by season — mirroring the silver layer's storage split (data-pipeline.md §4). Pure compute lives
here; the Prefect task wiring (DB loading, the nightly refresh trigger) lives in
``features/flows.py``.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.features.player_game import build_player_game_features
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.rapm.aggregate import attach_player_rapm, attach_team_rapm
from nbaforecast.storage.models.gold import FeaturePlayerGame, FeatureTeamGame
from nbaforecast.storage.parquet_io import write_parquet
from nbaforecast.storage.parquet_schemas import GOLD_PARQUET_SCHEMAS
from nbaforecast.storage.repositories import to_db_records, upsert_rows

# Bumped whenever build_team_game_features' column definitions change (data-pipeline.md §9).
TEAM_GAME_FEATURE_VERSION = "team_game_v1"
TEAM_GAME_UPSERT_KEY = ("game_id", "team_id")

# team_orapm/team_drapm (team) and player_rapm (player) are filled by T3.9's leakage-safe RAPM
# aggregation (models/rapm/aggregate.py) when ``rapm_snapshots`` is supplied, and left NULL
# otherwise — e.g. very early in a fresh backfill before any RAPM snapshot exists.
_TEAM_RAPM_COLUMNS = ("team_orapm", "team_drapm")
_PLAYER_RAPM_COLUMNS = ("player_rapm",)

# Bumped whenever build_player_game_features' column definitions change (data-pipeline.md §9).
PLAYER_GAME_FEATURE_VERSION = "player_game_v1"
PLAYER_GAME_UPSERT_KEY = ("game_id", "player_id")


def materialize_team_game_features(
    games: pd.DataFrame,
    team_game_stats: pd.DataFrame,
    teams: pd.DataFrame,
    *,
    game_ids: list[str] | None = None,
    player_game_stats: pd.DataFrame | None = None,
    rapm_snapshots: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build team-game features and stamp them with the current ``feature_version``.

    ``game_ids``, if given, narrows the *output* to those games (incremental refresh) — the full
    history is still used as computation context, so rolling/season-to-date values stay correct;
    only which rows get written is restricted.

    When ``player_game_stats`` and ``rapm_snapshots`` are both supplied, ``team_orapm``/
    ``team_drapm`` are filled with the leakage-safe possession-weighted team RAPM (T3.9); when
    either is absent they stay NULL (the pre-RAPM state).
    """
    features = build_team_game_features(games, team_game_stats, teams)
    if game_ids is not None:
        features = features.loc[features["game_id"].isin(game_ids)].reset_index(drop=True)
    if player_game_stats is not None and rapm_snapshots is not None:
        team_rapm = attach_team_rapm(features, player_game_stats, games, rapm_snapshots)
        features = features.assign(
            team_orapm=team_rapm["team_orapm"].to_numpy(),
            team_drapm=team_rapm["team_drapm"].to_numpy(),
        )
    else:
        features = features.assign(**dict.fromkeys(_TEAM_RAPM_COLUMNS, np.nan))
    return features.assign(feature_version=TEAM_GAME_FEATURE_VERSION)


async def upsert_team_game_features(session: AsyncSession, features: pd.DataFrame) -> int:
    """Upsert materialized rows into Postgres (``features_team_game``)."""
    return await upsert_rows(
        session, FeatureTeamGame, to_db_records(features), TEAM_GAME_UPSERT_KEY
    )


def write_team_game_features_parquet(features: pd.DataFrame, root: str | None = None) -> list[Path]:
    """Write one Parquet part-file per game (mirrors the silver layout) — idempotent on game_id."""
    schema = GOLD_PARQUET_SCHEMAS["features_team_game"]
    paths = []
    for (season_start_year, game_id), group in features.groupby(
        ["season_start_year", "game_id"], sort=False
    ):
        paths.append(
            write_parquet(
                "features_team_game",
                group,
                int(season_start_year),  # type: ignore[call-overload]  # pandas-stubs: group key is Hashable
                partition_key=str(game_id),
                root=root,
                schema=schema,
            )
        )
    return paths


def materialize_player_game_features(
    games: pd.DataFrame,
    player_game_stats: pd.DataFrame,
    team_game_stats: pd.DataFrame,
    players: pd.DataFrame,
    *,
    game_ids: list[str] | None = None,
    rapm_snapshots: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build player-game features and stamp them with the current ``feature_version``.

    ``game_ids``, if given, narrows the *output* to those games (incremental refresh) — the full
    history is still used as computation context, so rolling/season-to-date values stay correct;
    only which rows get written is restricted. Mirrors ``materialize_team_game_features``.

    When ``rapm_snapshots`` is supplied, ``player_rapm`` is filled with the leakage-safe as-of
    player RAPM (T3.9); otherwise it stays NULL (the pre-RAPM state).
    """
    features = build_player_game_features(games, player_game_stats, team_game_stats, players)
    if game_ids is not None:
        features = features.loc[features["game_id"].isin(game_ids)].reset_index(drop=True)
    if rapm_snapshots is not None:
        features = features.assign(player_rapm=attach_player_rapm(features, rapm_snapshots))
    else:
        features = features.assign(**dict.fromkeys(_PLAYER_RAPM_COLUMNS, np.nan))
    return features.assign(feature_version=PLAYER_GAME_FEATURE_VERSION)


async def upsert_player_game_features(session: AsyncSession, features: pd.DataFrame) -> int:
    """Upsert materialized rows into Postgres (``features_player_game``)."""
    return await upsert_rows(
        session, FeaturePlayerGame, to_db_records(features), PLAYER_GAME_UPSERT_KEY
    )


def write_player_game_features_parquet(
    features: pd.DataFrame, root: str | None = None
) -> list[Path]:
    """Write one Parquet part-file per game (mirrors the silver layout) — idempotent on game_id."""
    schema = GOLD_PARQUET_SCHEMAS["features_player_game"]
    paths = []
    for (season_start_year, game_id), group in features.groupby(
        ["season_start_year", "game_id"], sort=False
    ):
        paths.append(
            write_parquet(
                "features_player_game",
                group,
                int(season_start_year),  # type: ignore[call-overload]  # pandas-stubs: group key is Hashable
                partition_key=str(game_id),
                root=root,
                schema=schema,
            )
        )
    return paths
