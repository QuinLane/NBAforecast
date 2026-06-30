"""Games + predictions response schemas — backend-api.md §4."""

from datetime import date, datetime

from pydantic import BaseModel

from nbaforecast.explain.schema import Explanation


class TeamSummary(BaseModel):
    """The minimal team identity embedded in a game response."""

    team_id: int
    abbreviation: str
    full_name: str


class GameSummary(BaseModel):
    """One row of a games list — backend-api.md §3 ``GET /games``."""

    game_id: str
    season: str
    game_date: date
    home_team: TeamSummary
    away_team: TeamSummary
    home_score: int | None
    away_score: int | None
    status: str


class GameDetail(GameSummary):
    """Full game record — backend-api.md §3 ``GET /games/{game_id}``."""

    game_datetime: datetime | None
    num_periods: int


class GamePrediction(BaseModel):
    """backend-api.md §4 ``GamePrediction``.

    ``margin``/``total`` are reserved for the regressor heads (T3.1, M3 scope) — ``None`` until
    then. ``market`` is reserved for the v2 odds-comparison feature (modeling.md §10).
    """

    game_id: str
    win_prob: float
    margin: float | None = None
    total: float | None = None
    market: float | None = None
    explanation: Explanation
