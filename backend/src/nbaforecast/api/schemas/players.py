"""Players / teams / stats response schemas — backend-api.md §3-4."""

from datetime import date

from pydantic import BaseModel

from nbaforecast.api.schemas.games import GameSummary
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
    team_abbreviation: str | None
    opponent_abbreviation: str | None
    is_home: bool
    # Whether this player's team won; None while the game has no final score.
    won: bool | None
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


class PlayerGameStatLine(BaseModel):
    """One game's values for the stat-trajectory chart — chronological per-game series."""

    game_id: str
    game_date: date
    season: str
    min: float | None
    pts: int
    reb: int
    ast: int
    fg3m: int


class PlayerSeasonAverages(BaseModel):
    """A player's per-game averages for one season — the season/career table."""

    season: str
    games_played: int
    min: float | None
    pts: float
    reb: float
    ast: float
    fg3m: float
    # Shooting percentages from summed makes/attempts (None when no attempts).
    fg_pct: float | None
    fg3_pct: float | None
    ft_pct: float | None


class PlayerStatTrajectory(BaseModel):
    """``GET /players/{player_id}/stats`` — the per-game series plus season averages.

    ``games`` drives the trajectory chart (PTS/REB/AST/3PM/MIN tabs; RAPM comes from the
    separate snapshot-cadence ``/rapm`` history). ``seasons`` drives the season/career table —
    one row today, a career ladder once the full-era backfill lands.
    """

    games: list[PlayerGameStatLine]
    seasons: list[PlayerSeasonAverages]


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


class TeamProfile(BaseModel):
    """``GET /teams/{team_id}/profile`` — record + roster + recent games for a team page."""

    team: TeamSummary
    wins: int
    losses: int
    roster: list[PlayerSummary]
    recent_games: list[GameSummary]


class HeadToHead(BaseModel):
    """``GET /teams/{team_id}/head-to-head`` — the series between two teams and its record."""

    team: TeamSummary
    opponent: TeamSummary
    team_wins: int
    opponent_wins: int
    games: list[GameSummary]


class LeaderboardEntry(BaseModel):
    """One row of a generic stat leaderboard — ``GET /stats/leaderboards``."""

    player_id: int
    full_name: str | None
    stat: str
    value: float
    games_played: int
