"""Shared fixtures for API contract tests (backend-api.md Prompt 8).

Seeds an in-memory SQLite database (``StaticPool`` — separate sessions must all see the same
data, which plain ``:memory:`` doesn't guarantee across connections) with a small synthetic
league, trains a real ``LightGBMWinProbHead`` on it, and overrides the app's
``get_db_session``/``get_model_provider`` dependencies so ``TestClient`` requests exercise real
SQLAlchemy queries and a real (if tiny) trained model — without needing Postgres or a live
MLflow server, neither of which is available in this sandbox.
"""

from collections.abc import AsyncIterator, Iterator

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from nbaforecast.api.deps import get_db_session, get_model_provider
from nbaforecast.api.main import app
from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.win_prob import LightGBMWinProbHead
from nbaforecast.storage.database import Base
from nbaforecast.storage.models import Game, Team, TeamGameStats
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from tests.ml._synthetic_league import build_synthetic_league

SEEDED_TABLES = (Team.__table__, Game.__table__, TeamGameStats.__table__)
N_TEAMS = 6

# TeamGameStats requires these NOT NULL box-score columns; the contract tests only exercise
# ratings/pace (what build_team_game_features actually reads), so they're all zeroed.
_COUNTING_STAT_DEFAULTS = dict.fromkeys(
    (
        "pts",
        "reb",
        "oreb",
        "dreb",
        "ast",
        "stl",
        "blk",
        "tov",
        "pf",
        "fgm",
        "fga",
        "fg3m",
        "fg3a",
        "ftm",
        "fta",
    ),
    0,
)


def _synthetic_league() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return build_synthetic_league(n_teams=N_TEAMS)


async def _seed(session: AsyncSession) -> None:
    games_df, team_game_stats_df, teams_df = _synthetic_league()

    for row in teams_df.itertuples(index=False):
        session.add(
            Team(
                team_id=int(row.team_id),
                abbreviation=f"T{row.team_id}",
                full_name=f"Team {row.team_id}",
                # Plain Python floats, not numpy.float64 — aiosqlite silently NULLs a Numeric
                # column for a numpy scalar it doesn't recognize (confirmed empirically: one
                # team's arena_lat came back None after the round trip, with no error raised).
                arena_lat=float(row.arena_lat),
                arena_lon=float(row.arena_lon),
            )
        )

    for row in games_df.itertuples(index=False):
        session.add(
            Game(
                game_id=row.game_id,
                season=row.season,
                season_start_year=int(row.season_start_year),
                season_type="Regular Season",
                game_date=row.game_date.date(),
                home_team_id=int(row.home_team_id),
                away_team_id=int(row.away_team_id),
                home_score=int(row.home_score),
                away_score=int(row.away_score),
                status=row.status,
            )
        )

    for row in team_game_stats_df.itertuples(index=False):
        session.add(
            TeamGameStats(
                game_id=row.game_id,
                team_id=int(row.team_id),
                opponent_team_id=int(row.opponent_team_id),
                is_home=bool(row.is_home),
                off_rating=row.off_rating,
                def_rating=row.def_rating,
                net_rating=row.net_rating,
                pace=row.pace,
                possessions=100,
                **_COUNTING_STAT_DEFAULTS,
            )
        )

    await session.commit()


@pytest_asyncio.fixture
async def seeded_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=SEEDED_TABLES)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        await _seed(session)

    yield engine
    await engine.dispose()


@pytest.fixture
def trained_model_provider() -> ModelProvider:
    """A ModelProvider wired to a real LightGBMWinProbHead trained on the same league the DB is
    seeded with — bypasses MLflow entirely, while still exercising the real predict()/explain()
    path end to end.
    """
    games_df, team_game_stats_df, teams_df = _synthetic_league()
    features = build_team_game_features(games_df, team_game_stats_df, teams_df)

    outcomes = team_game_stats_df.merge(
        games_df[["game_id", "home_score", "away_score"]], on="game_id"
    )
    outcomes["win"] = np.where(
        outcomes["is_home"],
        outcomes["home_score"] > outcomes["away_score"],
        outcomes["away_score"] > outcomes["home_score"],
    ).astype(float)
    merged = features.merge(
        outcomes[["game_id", "team_id", "win"]], on=["game_id", "team_id"], how="left"
    )

    head = LightGBMWinProbHead()
    result = head.train(features, merged["win"])

    provider = ModelProvider(heads={"game_win": head})
    provider._models["game_win"] = result.model
    return provider


@pytest.fixture
def client(
    seeded_engine: AsyncEngine, trained_model_provider: ModelProvider
) -> Iterator[TestClient]:
    sessionmaker = async_sessionmaker(seeded_engine, expire_on_commit=False)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_model_provider] = lambda: trained_model_provider

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_game_id() -> str:
    """A deterministic, always-present game id from the seeded league (seed=42)."""
    games_df, _, _ = _synthetic_league()
    return str(games_df.sort_values("game_date").iloc[0]["game_id"])
