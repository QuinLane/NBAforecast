"""Games + predictions service layer — backend-api.md Prompt 4.

Pulls stored games/team data and, for predictions, calls the ``ModelProvider`` for the current
champion game-win head. Train/serve parity holds here for free: a completed game's prediction is
built the same way ``build_team_game_features(as_of=None)`` builds every training row (filtered
to that one game), and a still-scheduled game uses the exact ``as_of``-set serving path —
features/team_game.py's module docstring is the reason this works without a separate code path.
"""

from datetime import date as date_type

import numpy as np
import pandas as pd
import shap
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.games import (
    BoxScorePlayerLine,
    BoxScoreTeam,
    GameBoxScore,
    GameDetail,
    GamePrediction,
    GameSummary,
    GameWinProbabilityTimeline,
    TeamSummary,
    WinProbabilityDriver,
    WinProbabilityPoint,
)
from nbaforecast.explain.humanizer import humanize
from nbaforecast.features.game_state import build_game_state_features
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.win_probability.in_game import design_matrix as in_game_design_matrix
from nbaforecast.storage.models import (
    Game,
    PlayByPlay,
    Player,
    PlayerGameStats,
    Team,
    TeamGameStats,
)
from nbaforecast.storage.repositories import load_table_as_dataframe

IN_GAME_WIN_HEAD = "in_game_win"
_WIN_PROB_FEATURE_LABELS = {
    "score_margin": "Score margin",
    "seconds_remaining": "Time remaining",
    "period": "Period",
}

TOP_N_DRIVERS = 5
GAME_WIN_HEAD = "game_win"
# Regressor heads (T3.1) attached to the prediction when a champion is promoted for them —
# schema field -> head name. Skipped silently while a head has no champion yet.
GAME_REGRESSOR_HEADS = {"margin": "game_margin", "total": "game_total"}


async def _team_lookup(session: AsyncSession) -> dict[int, TeamSummary]:
    teams = (await session.execute(select(Team))).scalars().all()
    return {
        team.team_id: TeamSummary(
            team_id=team.team_id, abbreviation=team.abbreviation, full_name=team.full_name
        )
        for team in teams
    }


def _to_summary(game: Game, teams: dict[int, TeamSummary]) -> GameSummary:
    home_team = teams.get(game.home_team_id)
    away_team = teams.get(game.away_team_id)
    if home_team is None or away_team is None:
        missing = [t for t in (game.home_team_id, game.away_team_id) if t not in teams]
        raise RuntimeError(f"team_id(s) {missing} not found in teams reference table")
    return GameSummary(
        game_id=game.game_id,
        season=game.season,
        game_date=game.game_date,
        home_team=home_team,
        away_team=away_team,
        home_score=game.home_score,
        away_score=game.away_score,
        status=game.status,
    )


async def list_games(
    session: AsyncSession,
    *,
    game_date: date_type | None = None,
    season: str | None = None,
    team_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> Page[GameSummary]:
    """``GET /games`` — paginated schedule + results, filterable by date/season/team."""
    query = select(Game)
    if game_date is not None:
        query = query.where(Game.game_date == game_date)
    if season is not None:
        query = query.where(Game.season == season)
    if team_id is not None:
        query = query.where((Game.home_team_id == team_id) | (Game.away_team_id == team_id))

    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()

    paged_query = (
        query.order_by(Game.game_date.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    games = (await session.execute(paged_query)).scalars().all()
    teams = await _team_lookup(session)

    return Page(
        items=[_to_summary(game, teams) for game in games],
        total=total,
        page=page,
        page_size=page_size,
    )


async def summarize_games(session: AsyncSession, games: list[Game]) -> list[GameSummary]:
    """Map ``Game`` rows to ``GameSummary`` with a single shared team lookup (reused by teams)."""
    teams = await _team_lookup(session)
    return [_to_summary(game, teams) for game in games]


async def get_game(session: AsyncSession, game_id: str) -> GameDetail | None:
    """``GET /games/{game_id}`` — full game record, or ``None`` if it doesn't exist."""
    game = await session.get(Game, game_id)
    if game is None:
        return None
    teams = await _team_lookup(session)
    summary = _to_summary(game, teams)
    return GameDetail(
        **summary.model_dump(), game_datetime=game.game_datetime, num_periods=game.num_periods
    )


def _boxscore_team(
    team_stats: TeamGameStats,
    team: TeamSummary,
    player_rows: list[tuple[PlayerGameStats, str | None]],
) -> BoxScoreTeam:
    # Starters first, then by minutes played (descending); a stable, box-score-like order.
    ordered = sorted(
        player_rows,
        key=lambda row: (not row[0].started, -(float(row[0].min) if row[0].min else 0.0)),
    )
    players = [
        BoxScorePlayerLine(
            player_id=stat.player_id,
            full_name=name,
            started=stat.started,
            min=None if stat.min is None else float(stat.min),
            pts=stat.pts,
            reb=stat.reb,
            ast=stat.ast,
            stl=stat.stl,
            blk=stat.blk,
            tov=stat.tov,
            fgm=stat.fgm,
            fga=stat.fga,
            fg3m=stat.fg3m,
            fg3a=stat.fg3a,
            ftm=stat.ftm,
            fta=stat.fta,
            plus_minus=stat.plus_minus,
        )
        for stat, name in ordered
    ]
    return BoxScoreTeam(
        team=team,
        is_home=team_stats.is_home,
        pts=team_stats.pts,
        reb=team_stats.reb,
        ast=team_stats.ast,
        stl=team_stats.stl,
        blk=team_stats.blk,
        tov=team_stats.tov,
        fgm=team_stats.fgm,
        fga=team_stats.fga,
        fg3m=team_stats.fg3m,
        fg3a=team_stats.fg3a,
        ftm=team_stats.ftm,
        fta=team_stats.fta,
        players=players,
    )


async def get_game_boxscore(session: AsyncSession, game_id: str) -> GameBoxScore | None:
    """``GET /games/{game_id}/boxscore`` — team totals + player lines for a played game.

    Returns ``None`` if the game doesn't exist or has no ingested box score yet (scheduled/live);
    callers 404 in that case.
    """
    game = await session.get(Game, game_id)
    if game is None:
        return None

    team_stats = {
        ts.team_id: ts
        for ts in (
            await session.execute(select(TeamGameStats).where(TeamGameStats.game_id == game_id))
        )
        .scalars()
        .all()
    }
    home_stats = team_stats.get(game.home_team_id)
    away_stats = team_stats.get(game.away_team_id)
    if home_stats is None or away_stats is None:
        return None  # not played / not ingested yet

    player_rows = (
        await session.execute(
            select(PlayerGameStats, Player.full_name)
            .join(Player, Player.player_id == PlayerGameStats.player_id)
            .where(PlayerGameStats.game_id == game_id)
        )
    ).all()
    by_team: dict[int, list[tuple[PlayerGameStats, str | None]]] = {
        game.home_team_id: [],
        game.away_team_id: [],
    }
    for stat, name in player_rows:
        by_team.setdefault(stat.team_id, []).append((stat, name))

    teams = await _team_lookup(session)
    return GameBoxScore(
        game_id=game_id,
        status=game.status,
        home=_boxscore_team(home_stats, teams[game.home_team_id], by_team[game.home_team_id]),
        away=_boxscore_team(away_stats, teams[game.away_team_id], by_team[game.away_team_id]),
    )


async def get_game_prediction(
    session: AsyncSession,
    model_provider: ModelProvider,
    game_id: str,
    *,
    full: bool = False,
) -> GamePrediction | None:
    """``GET /games/{game_id}/prediction`` (and the full-explanation variant via ``full=True``).

    Returns ``None`` if the game doesn't exist or hasn't been ingested into team_game_stats yet
    in a way ``build_team_game_features`` can find a row for (callers should 404 in that case).
    """
    game = await session.get(Game, game_id)
    if game is None:
        return None

    # Scope the feature build to the game's own season: it's fast (one season, not the full
    # backfilled history), and it reproduces the single-season context the champions were trained
    # on — so within-season rolling/Elo/season-to-date features (and thus predictions) match
    # training exactly instead of drifting as older seasons are backfilled in.
    season_games = select(Game.game_id).where(Game.season_start_year == game.season_start_year)
    games_df = await load_table_as_dataframe(
        session, Game, where=[Game.season_start_year == game.season_start_year]
    )
    team_game_stats_df = await load_table_as_dataframe(
        session, TeamGameStats, where=[TeamGameStats.game_id.in_(season_games)]
    )
    teams_df = await load_table_as_dataframe(session, Team)

    if game.status in ("scheduled", "live"):
        # Live games haven't produced final box-score stats yet; treat them like scheduled
        # games so features are built from prior games only (as_of = tip-off date).
        features = build_team_game_features(
            games_df, team_game_stats_df, teams_df, as_of=game.game_date
        )
    else:
        features = build_team_game_features(games_df, team_game_stats_df, teams_df)

    home_row = features.loc[
        (features["game_id"] == game_id) & (features["team_id"] == game.home_team_id)
    ]
    if home_row.empty:
        return None

    loaded_head = model_provider.get(GAME_WIN_HEAD)
    win_prob = float(loaded_head.predict(home_row).iloc[0])
    raw_explanation = loaded_head.explain(home_row)
    # When calibration is active the SHAP values are in uncalibrated space and cannot attribute
    # the isotonic step, so sync the headline number to what was actually served.
    explanation = humanize(raw_explanation.model_copy(update={"prediction": win_prob}))
    if not full:
        explanation = explanation.model_copy(
            update={"contributions": explanation.contributions[:TOP_N_DRIVERS]}
        )

    regressor_values: dict[str, float] = {}
    for field, head_name in GAME_REGRESSOR_HEADS.items():
        if model_provider.is_loaded(head_name):
            regressor_values[field] = float(model_provider.get(head_name).predict(home_row).iloc[0])

    return GamePrediction(
        game_id=game_id, win_prob=win_prob, explanation=explanation, **regressor_values
    )


def _clock(seconds_in_period: float | None) -> str:
    """Game clock 'M:SS' from seconds left in the period (blank when unknown)."""
    if seconds_in_period is None or pd.isna(seconds_in_period):
        return ""
    total = int(seconds_in_period)
    return f"{total // 60}:{total % 60:02d}"


def _format_feature(column: str, value: float) -> str:
    if column == "score_margin":
        return f"{int(value):+d}"
    if column == "period":
        period = int(value)
        return f"OT{period - 4}" if period > 4 else f"Q{period}"
    total = int(value)  # seconds_remaining
    return f"{total // 60}:{total % 60:02d} left"


def _win_prob_drivers(
    shap_row: np.ndarray, columns: list[str], feature_row: pd.Series, baseline_log_odds: float
) -> list[WinProbabilityDriver]:
    """Per-moment drivers in probability points, via the same telescoping logistic mapping the
    game-page explainer uses (so ``sum(contributions)`` matches ``prediction - baseline``)."""
    order = np.argsort(-np.abs(shap_row))
    running = baseline_log_odds
    drivers: list[WinProbabilityDriver] = []
    for i in order:
        prev = 1.0 / (1.0 + np.exp(-running))
        running += float(shap_row[i])
        new = 1.0 / (1.0 + np.exp(-running))
        drivers.append(
            WinProbabilityDriver(
                label=_WIN_PROB_FEATURE_LABELS[columns[i]],
                value=_format_feature(columns[i], float(feature_row[columns[i]])),
                contribution=float(new - prev),
                direction="up" if new >= prev else "down",
            )
        )
    return drivers


async def game_win_probability(
    session: AsyncSession, model_provider: ModelProvider, game_id: str
) -> GameWinProbabilityTimeline | None:
    """``GET /games/{game_id}/win-probability`` — replay a game's play-by-play through the in-game
    win-prob champion into a per-moment trajectory with SHAP drivers.

    ``None`` if the game is unknown or has no usable play-by-play (not played yet → 404). Raises
    ``RuntimeError`` (→ 503) if no ``in_game_win`` champion is loaded, like the prediction path.
    """
    game = await session.get(Game, game_id)
    if game is None:
        return None

    rows = (
        (
            await session.execute(
                select(PlayByPlay)
                .where(PlayByPlay.game_id == game_id)
                .order_by(PlayByPlay.event_num)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None

    pbp = pd.DataFrame(
        [
            {
                "game_id": r.game_id,
                "event_num": r.event_num,
                "period": r.period,
                "seconds_remaining_period": r.seconds_remaining_period,
                "home_score": r.home_score,
                "away_score": r.away_score,
                "description": r.description,
            }
            for r in rows
        ]
    )
    games_df = pd.DataFrame(
        [
            {
                "game_id": game.game_id,
                "game_date": game.game_date,
                "season_start_year": game.season_start_year,
            }
        ]
    )
    features = (
        build_game_state_features(games_df, pbp).sort_values("event_num").reset_index(drop=True)
    )
    if features.empty:
        return None

    loaded = model_provider.get(IN_GAME_WIN_HEAD)  # RuntimeError → 503 at the router
    probs = loaded.predict(features).to_numpy()

    design = in_game_design_matrix(features)
    model = loaded.model
    explainer = model.get("explainer") or shap.TreeExplainer(model["booster"])
    raw_shap = explainer.shap_values(design)
    shap_matrix = np.asarray(raw_shap[1] if isinstance(raw_shap, list) else raw_shap)
    baseline = float(np.asarray(explainer.expected_value).reshape(-1)[-1])

    columns = list(design.columns)
    display = pbp.set_index("event_num")
    points: list[WinProbabilityPoint] = []
    for i in range(len(features)):
        row = features.iloc[i]
        event_num = int(row["event_num"])
        period = int(row["period"])
        seconds_remaining = int(row["seconds_remaining"])
        # Clock within the period: strip the not-yet-played regulation periods back off.
        in_period = seconds_remaining - (4 - period) * 60 * 12 if period <= 4 else seconds_remaining
        description = display.loc[event_num, "description"]
        points.append(
            WinProbabilityPoint(
                event_num=event_num,
                period=period,
                clock=_clock(in_period),
                seconds_remaining=seconds_remaining,
                home_score=int(row["home_score"]),
                away_score=int(row["away_score"]),
                home_win_prob=float(probs[i]),
                description=None if pd.isna(description) else str(description),
                drivers=_win_prob_drivers(shap_matrix[i], columns, row, baseline),
            )
        )

    teams = await _team_lookup(session)
    return GameWinProbabilityTimeline(
        game_id=game_id,
        home_team=teams[game.home_team_id],
        away_team=teams[game.away_team_id],
        points=points,
    )
