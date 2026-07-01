"""Players / teams / stats response schemas — backend-api.md §3-4."""

from datetime import date

from pydantic import BaseModel

from nbaforecast.explain.schema import Explanation


class PlayerSummary(BaseModel):
    """One row of a players list — ``GET /players``."""

    player_id: int
    full_name: str
    position: str | None
    is_active: bool


class PlayerGameLog(BaseModel):
    """One recent game line on a player's profile."""

    game_id: str
    game_date: date
    team_id: int
    opponent_team_id: int
    is_home: bool
    min: float | None
    pts: int
    reb: int
    ast: int
    fg3m: int


class PlayerDetail(PlayerSummary):
    """Full player profile — ``GET /players/{player_id}`` (profile + recent game logs)."""

    height_inches: int | None
    weight_lbs: int | None
    birthdate: date | None
    recent_games: list[PlayerGameLog]


class ShotChartEntry(BaseModel):
    """One field-goal attempt for the shot chart — ``GET /players/{player_id}/shots``.

    Respects ``location_reliable`` (data-model): unreliable-location attempts still count toward
    make/miss but carry a flag so the frontend can omit them from the spatial chart.
    """

    game_id: str
    period: int
    loc_x: int | None
    loc_y: int | None
    shot_distance: int | None
    shot_zone: str | None
    shot_type: str | None
    made: bool
    location_reliable: bool


class PropsProjection(BaseModel):
    """A single-stat props projection — backend-api.md §4 ``PropsProjection``."""

    player_id: int
    game_id: str
    stat: str
    point: float
    interval_low: float
    interval_high: float
    explanation: Explanation


class TeamSummary(BaseModel):
    """One row of a teams list — ``GET /teams``."""

    team_id: int
    abbreviation: str
    full_name: str
    conference: str | None
    division: str | None


class LeaderboardEntry(BaseModel):
    """One row of a generic stat leaderboard — ``GET /stats/leaderboards``."""

    player_id: int
    full_name: str | None
    stat: str
    value: float
    games_played: int
