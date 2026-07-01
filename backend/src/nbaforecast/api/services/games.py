"""Games + predictions service layer — backend-api.md Prompt 4.

Pulls stored games/team data and, for predictions, calls the ``ModelProvider`` for the current
champion game-win head. Train/serve parity holds here for free: a completed game's prediction is
built the same way ``build_team_game_features(as_of=None)`` builds every training row (filtered
to that one game), and a still-scheduled game uses the exact ``as_of``-set serving path —
features/team_game.py's module docstring is the reason this works without a separate code path.
"""

from datetime import date as date_type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.games import GameDetail, GamePrediction, GameSummary, TeamSummary
from nbaforecast.explain.humanizer import humanize
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.storage.models import Game, Team, TeamGameStats
from nbaforecast.storage.repositories import load_table_as_dataframe

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

    games_df = await load_table_as_dataframe(session, Game)
    team_game_stats_df = await load_table_as_dataframe(session, TeamGameStats)
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
