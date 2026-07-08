"""Contract tests for the M3 read endpoints — backend-api.md Prompt 5/8.

Players, teams, RAPM leaderboard/history, stats leaderboards, and props projections, exercised
through ``TestClient`` against an in-memory SQLite database seeded with the shared synthetic
player league — plus a real ``PropsRegressorHead`` trained on that same league for the props path
(mirrors ``tests/api/conftest.py``'s approach for the game-win head, no MLflow needed).

Self-contained fixtures (local to this module) so the existing games-endpoint fixtures in
``conftest.py`` are untouched.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import date

import pandas as pd
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from nbaforecast.api.deps import get_db_session, get_model_provider
from nbaforecast.api.main import app
from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.features.player_game import build_player_game_features
from nbaforecast.models.props.regressor import PropsRegressorHead
from nbaforecast.storage.database import Base
from nbaforecast.storage.models import (
    Game,
    Player,
    PlayerGameStats,
    PlayerRapm,
    Shot,
    Team,
    TeamGameStats,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from tests.ml._synthetic_player_league import build_synthetic_player_league

N_TEAMS = 6

# PlayerGameStats / TeamGameStats NOT NULL box-score columns the synthetic league doesn't emit;
# zeroed since the M3 endpoints only read the stats they do emit (pts/reb/ast/fg3m/min/usage).
_PLAYER_STAT_DEFAULTS = dict.fromkeys(
    ("oreb", "dreb", "stl", "blk", "tov", "pf", "fgm", "fga", "fg3a", "ftm", "fta"), 0
)
_TEAM_STAT_DEFAULTS = dict.fromkeys(
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

RAPM_AS_OF = date(2020, 10, 1)


def _league() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return build_synthetic_player_league(n_teams=N_TEAMS)


async def _seed(session: AsyncSession) -> None:
    games_df, team_game_stats_df, teams_df, player_game_stats_df, players_df = _league()

    for row in teams_df.itertuples(index=False):
        session.add(
            Team(
                team_id=int(row.team_id),
                abbreviation=f"T{row.team_id}",
                full_name=f"Team {row.team_id}",
                conference="East" if int(row.team_id) % 2 == 0 else "West",
                division="Atlantic",
                arena_lat=float(row.arena_lat),
                arena_lon=float(row.arena_lon),
            )
        )
    for row in players_df.itertuples(index=False):
        session.add(
            Player(
                player_id=int(row.player_id),
                full_name=row.full_name,
                position=row.position,
                is_active=True,
                height_inches=78,
                weight_lbs=210,
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
                off_rating=float(row.off_rating),
                def_rating=float(row.def_rating),
                net_rating=float(row.net_rating),
                pace=float(row.pace),
                possessions=100,
                **_TEAM_STAT_DEFAULTS,
            )
        )
    for row in player_game_stats_df.itertuples(index=False):
        session.add(
            PlayerGameStats(
                game_id=row.game_id,
                player_id=int(row.player_id),
                team_id=int(row.team_id),
                opponent_team_id=int(row.opponent_team_id),
                is_home=bool(row.is_home),
                started=True,
                min=float(row.min),
                pts=int(row.pts),
                reb=int(row.reb),
                ast=int(row.ast),
                fg3m=int(row.fg3m),
                usage_rate=float(row.usage_rate),
                **_PLAYER_STAT_DEFAULTS,
            )
        )

    # Two deterministic RAPM snapshots (same as_of/window) so the leaderboard is comparable.
    first_two = players_df["player_id"].astype(int).tolist()[:2]
    session.add(
        PlayerRapm(
            player_id=first_two[0],
            as_of_date=RAPM_AS_OF,
            window=3,
            orapm=3.0,
            drapm=1.0,
            rapm=4.0,
            possessions=900,
        )
    )
    session.add(
        PlayerRapm(
            player_id=first_two[1],
            as_of_date=RAPM_AS_OF,
            window=3,
            orapm=1.0,
            drapm=0.5,
            rapm=1.5,
            possessions=400,
        )
    )
    # A couple of shots for the first player (one unreliable location).
    a_game = str(games_df.iloc[0]["game_id"])
    shot_team = int(players_df.iloc[0].player_id) // 100
    session.add(
        Shot(
            shot_id=1,
            game_id=a_game,
            event_num=1,
            player_id=first_two[0],
            team_id=shot_team,
            period=1,
            loc_x=10,
            loc_y=20,
            shot_distance=15,
            shot_zone="Mid-Range",
            shot_type="2PT Field Goal",
            made=True,
            location_reliable=True,
        )
    )
    session.add(
        Shot(
            shot_id=2,
            game_id=a_game,
            event_num=2,
            player_id=first_two[0],
            team_id=shot_team,
            period=2,
            loc_x=None,
            loc_y=None,
            shot_distance=None,
            shot_zone=None,
            shot_type="3PT Field Goal",
            made=False,
            location_reliable=False,
        )
    )
    await session.commit()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = (
        Team.__table__,
        Player.__table__,
        Game.__table__,
        TeamGameStats.__table__,
        PlayerGameStats.__table__,
        PlayerRapm.__table__,
        Shot.__table__,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        await _seed(session)
    yield engine
    await engine.dispose()


@pytest.fixture
def props_provider() -> ModelProvider:
    """Provider with a real ``props_pts`` head trained on the seeded league (no MLflow)."""
    games_df, team_game_stats_df, _teams, player_game_stats_df, players_df = _league()
    features = build_player_game_features(
        games_df, player_game_stats_df, team_game_stats_df, players_df
    )
    labels = features.merge(
        player_game_stats_df[["game_id", "player_id", "pts"]], on=["game_id", "player_id"]
    )["pts"].astype(float)
    head = PropsRegressorHead("pts")
    result = head.train(features, labels)
    provider = ModelProvider(heads={"props_pts": head})
    provider._models["props_pts"] = result.model
    return provider


@pytest.fixture
def client(engine: AsyncEngine, props_provider: ModelProvider) -> Iterator[TestClient]:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_model_provider] = lambda: props_provider
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def player_ids() -> list[int]:
    _g, _t, _te, _pgs, players_df = _league()
    return players_df["player_id"].astype(int).tolist()


# ── RAPM ────────────────────────────────────────────────────────────────────────────────────


def test_rapm_leaderboard_sorted_desc(client: TestClient) -> None:
    body = client.get("/api/v1/rapm", params={"min_poss": 0}).json()
    assert body["total"] == 2
    rapms = [item["rapm"] for item in body["items"]]
    assert rapms == sorted(rapms, reverse=True)
    assert body["items"][0]["rapm"] == 4.0
    assert body["items"][0]["full_name"] is not None


def test_rapm_leaderboard_default_min_poss_hides_small_samples(client: TestClient) -> None:
    # Fixture players have 900/400 possessions — below the default 1000 floor.
    body = client.get("/api/v1/rapm").json()
    assert body["total"] == 0
    body = client.get("/api/v1/rapm", params={"min_poss": 500}).json()
    assert body["total"] == 1


def test_rapm_leaderboard_sort_by_drapm(client: TestClient) -> None:
    body = client.get("/api/v1/rapm", params={"sort": "drapm", "min_poss": 0}).json()
    drapms = [item["drapm"] for item in body["items"]]
    assert drapms == sorted(drapms, reverse=True)


def test_rapm_leaderboard_bad_sort_is_400(client: TestClient) -> None:
    response = client.get("/api/v1/rapm", params={"sort": "nope"})
    assert response.status_code == 400
    assert response.json()["error"]  # typed error envelope


def test_player_rapm_history(client: TestClient, player_ids: list[int]) -> None:
    body = client.get(f"/api/v1/players/{player_ids[0]}/rapm").json()
    assert len(body) == 1
    assert body[0]["rapm"] == 4.0


# ── players / teams ───────────────────────────────────────────────────────────────────────────


def test_list_players_paginated(client: TestClient) -> None:
    body = client.get("/api/v1/players", params={"page_size": 3}).json()
    assert body["total"] == N_TEAMS * 5
    assert len(body["items"]) == 3


def test_get_player_detail_has_recent_games(client: TestClient, player_ids: list[int]) -> None:
    body = client.get(f"/api/v1/players/{player_ids[0]}").json()
    assert body["player_id"] == player_ids[0]
    assert len(body["recent_games"]) > 0


def test_get_unknown_player_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/players/99999999").status_code == 404


def test_player_stats_trajectory_has_games_and_seasons(
    client: TestClient, player_ids: list[int]
) -> None:
    body = client.get(f"/api/v1/players/{player_ids[0]}/stats").json()
    assert len(body["games"]) > 0
    assert len(body["seasons"]) > 0
    # Games arrive chronologically.
    dates = [g["game_date"] for g in body["games"]]
    assert dates == sorted(dates)
    # Season games_played reconciles with the per-game series for that season.
    counted = sum(1 for g in body["games"] if g["season"] == body["seasons"][0]["season"])
    assert body["seasons"][0]["games_played"] == counted
    # Synthetic league emits no shot attempts, so shooting pcts guard to None (no div-by-zero).
    assert body["seasons"][0]["fg_pct"] is None


def test_player_stats_unknown_player_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/players/99999999/stats").status_code == 404


def test_player_shots_reports_reliability(client: TestClient, player_ids: list[int]) -> None:
    shots = client.get(f"/api/v1/players/{player_ids[0]}/shots").json()
    assert len(shots) == 2
    assert {s["location_reliable"] for s in shots} == {True, False}


def test_list_and_get_team(client: TestClient) -> None:
    teams = client.get("/api/v1/teams").json()
    assert teams["total"] == N_TEAMS
    a_team_id = teams["items"][0]["team_id"]
    detail = client.get(f"/api/v1/teams/{a_team_id}")
    assert detail.status_code == 200
    assert detail.json()["team_id"] == a_team_id
    assert client.get("/api/v1/teams/99999999").status_code == 404


def test_team_profile_has_record_roster_and_recent(client: TestClient) -> None:
    team_id = client.get("/api/v1/teams").json()["items"][0]["team_id"]
    body = client.get(f"/api/v1/teams/{team_id}/profile").json()
    assert body["team"]["team_id"] == team_id
    assert len(body["roster"]) > 0
    assert len(body["recent_games"]) > 0
    # Total record is at least the finals visible in the (capped) recent window.
    final_recent = sum(1 for g in body["recent_games"] if g["status"] == "final")
    assert body["wins"] + body["losses"] >= final_recent


def test_team_profile_unknown_team_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/teams/99999999/profile").status_code == 404


def test_head_to_head_record_matches_played_games(client: TestClient) -> None:
    teams = client.get("/api/v1/teams").json()["items"]
    a, b = teams[0]["team_id"], teams[1]["team_id"]
    body = client.get(f"/api/v1/teams/{a}/head-to-head", params={"opponent": b}).json()
    assert body["team"]["team_id"] == a
    assert body["opponent"]["team_id"] == b
    # games is the full series (uncapped), so the record equals its played games exactly.
    played = sum(1 for g in body["games"] if g["status"] == "final")
    assert body["team_wins"] + body["opponent_wins"] == played


def test_head_to_head_unknown_opponent_is_404(client: TestClient) -> None:
    team_id = client.get("/api/v1/teams").json()["items"][0]["team_id"]
    response = client.get(
        f"/api/v1/teams/{team_id}/head-to-head", params={"opponent": 99999999}
    )
    assert response.status_code == 404


# ── box score ─────────────────────────────────────────────────────────────────────────────────


def test_game_boxscore_has_both_teams(client: TestClient) -> None:
    games_df, _t, _te, _pgs, _players = _league()
    game_id = str(
        games_df.loc[games_df["status"] == "final"].sort_values("game_date").iloc[-1]["game_id"]
    )
    body = client.get(f"/api/v1/games/{game_id}/boxscore").json()
    assert body["game_id"] == game_id
    assert len(body["home"]["players"]) > 0
    assert len(body["away"]["players"]) > 0
    # Starters sort ahead of bench.
    started_flags = [p["started"] for p in body["home"]["players"]]
    assert started_flags == sorted(started_flags, reverse=True)
    # Team-total fields are present on each side.
    assert "pts" in body["home"]
    assert "reb" in body["away"]


def test_game_boxscore_unknown_game_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/games/not_a_game/boxscore").status_code == 404


# ── stats ───────────────────────────────────────────────────────────────────────────────────


def test_stats_leaderboard_sorted(client: TestClient) -> None:
    body = client.get("/api/v1/stats/leaderboards", params={"stat": "pts"}).json()
    values = [item["value"] for item in body["items"]]
    assert values == sorted(values, reverse=True)
    assert body["items"][0]["games_played"] > 0


def test_stats_leaderboard_bad_stat_is_400(client: TestClient) -> None:
    assert client.get("/api/v1/stats/leaderboards", params={"stat": "nope"}).status_code == 400


# ── props ───────────────────────────────────────────────────────────────────────────────────


def _completed_game_and_player() -> tuple[str, int]:
    games_df, _t, _te, player_game_stats_df, _players = _league()
    completed = games_df.loc[games_df["status"] == "final"].sort_values("game_date")
    # Pick a late-season game so its players have prior-game rolling features.
    game_id = str(completed.iloc[-1]["game_id"])
    player_id = int(
        player_game_stats_df.loc[player_game_stats_df["game_id"] == game_id].iloc[0]["player_id"]
    )
    return game_id, player_id


def test_player_props_returns_pts_projection(client: TestClient) -> None:
    game_id, player_id = _completed_game_and_player()
    response = client.get(f"/api/v1/players/{player_id}/props", params={"game_id": game_id})
    assert response.status_code == 200, response.json()
    stats = {p["stat"]: p for p in response.json()}
    assert "pts" in stats
    pts = stats["pts"]
    assert pts["interval_low"] <= pts["point"] <= pts["interval_high"]
    assert pts["explanation"]["contributions"]  # top drivers present


def test_player_props_unknown_game_is_404(client: TestClient, player_ids: list[int]) -> None:
    response = client.get(
        f"/api/v1/players/{player_ids[0]}/props", params={"game_id": "not_a_game"}
    )
    assert response.status_code == 404


def test_player_props_503_when_no_champion(engine: AsyncEngine) -> None:
    """With an empty provider (no props champion loaded) the endpoint surfaces a 503, not a 500."""
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_model_provider] = lambda: ModelProvider(
        heads={"props_pts": PropsRegressorHead("pts")}
    )
    try:
        with TestClient(app) as test_client:
            game_id, player_id = _completed_game_and_player()
            response = test_client.get(
                f"/api/v1/players/{player_id}/props", params={"game_id": game_id}
            )
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()
