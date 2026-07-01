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
from nbaforecast.storage.models.gold import FeaturePlayerGame, FeatureTeamGame
from nbaforecast.storage.parquet_io import write_parquet
from nbaforecast.storage.parquet_schemas import GOLD_PARQUET_SCHEMAS
from nbaforecast.storage.repositories import to_db_records, upsert_rows

# Bumped whenever build_team_game_features' column definitions change (data-pipeline.md §9).
TEAM_GAME_FEATURE_VERSION = "team_game_v1"
TEAM_GAME_UPSERT_KEY = ("game_id", "team_id")

# Reserved in the gold schema (data-model.md §4) but not produced by build_team_game_features
# until T3.9 wires RAPM into features — written as NULL until then.
_RAPM_PLACEHOLDER_COLUMNS = ("team_orapm", "team_drapm")

# Bumped whenever build_player_game_features' column definitions change (data-pipeline.md §9).
PLAYER_GAME_FEATURE_VERSION = "player_game_v1"
PLAYER_GAME_UPSERT_KEY = ("game_id", "player_id")

# Reserved in the gold schema (data-model.md §4) but not produced by build_player_game_features
# until T3.9 wires player RAPM into features — written as NULL until then.
_PLAYER_RAPM_PLACEHOLDER_COLUMNS = ("player_rapm",)


def materialize_team_game_features(
    games: pd.DataFrame,
    team_game_stats: pd.DataFrame,
    teams: pd.DataFrame,
    *,
    game_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Build team-game features and stamp them with the current ``feature_version``.

    ``game_ids``, if given, narrows the *output* to those games (incremental refresh) — the full
    history is still used as computation context, so rolling/season-to-date values stay correct;
    only which rows get written is restricted.
    """
    features = build_team_game_features(games, team_game_stats, teams)
    if game_ids is not None:
        features = features.loc[features["game_id"].isin(game_ids)].reset_index(drop=True)
    features = features.assign(**dict.fromkeys(_RAPM_PLACEHOLDER_COLUMNS, np.nan))
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
) -> pd.DataFrame:
    """Build player-game features and stamp them with the current ``feature_version``.

    ``game_ids``, if given, narrows the *output* to those games (incremental refresh) — the full
    history is still used as computation context, so rolling/season-to-date values stay correct;
    only which rows get written is restricted. Mirrors ``materialize_team_game_features``.
    """
    features = build_player_game_features(games, player_game_stats, team_game_stats, players)
    if game_ids is not None:
        features = features.loc[features["game_id"].isin(game_ids)].reset_index(drop=True)
    features = features.assign(**dict.fromkeys(_PLAYER_RAPM_PLACEHOLDER_COLUMNS, np.nan))
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
