"""Pandera schemas validating silver DataFrames before load (data-pipeline.md §6).

A failed validation raises :class:`~nbaforecast.errors.DataValidationError`; the load step
(:mod:`nbaforecast.ingestion.load`) quarantines the offending payload and re-raises so the flow
fails loudly instead of loading bad data.
"""

from typing import Any

import pandas as pd
import pandera.pandas as pa

from nbaforecast.errors import DataValidationError

# Box-score counting stats — non-negative integers, never null in silver.
_COUNTING = (
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
)

_SEASON_RE = r"^\d{4}-\d{2}$"
# stats.nba.com court coordinates are tenths of feet: x∈[-250,250], y∈[-50,900] generously.
_COURT_X = (-300, 300)
_COURT_Y = (-100, 950)


def _counting_columns() -> dict[str, pa.Column]:
    return {c: pa.Column(int, pa.Check.ge(0), coerce=True) for c in _COUNTING}


def _nonneg_int(nullable: bool = False) -> pa.Column:
    dtype = "Int64" if nullable else int
    return pa.Column(dtype, pa.Check.ge(0), nullable=nullable, coerce=True)


def _is_list(series: "pd.Series[Any]") -> "pd.Series[bool]":
    return series.apply(lambda v: isinstance(v, list) and all(isinstance(x, int) for x in v))


GAMES_SCHEMA = pa.DataFrameSchema(
    {
        "game_id": pa.Column(str),
        "season": pa.Column(str, pa.Check.str_matches(_SEASON_RE)),
        "season_start_year": pa.Column(int, pa.Check.in_range(1996, 2100), coerce=True),
        "season_type": pa.Column(str),
        "game_date": pa.Column("datetime64[ns]", coerce=True, nullable=False),
        "game_datetime": pa.Column("datetime64[ns, UTC]", nullable=True, coerce=True),
        "home_team_id": pa.Column(int, coerce=True),
        "away_team_id": pa.Column(int, coerce=True),
        "home_score": _nonneg_int(nullable=True),
        "away_score": _nonneg_int(nullable=True),
        "status": pa.Column(str, pa.Check.isin(["scheduled", "live", "final"])),
        "num_periods": pa.Column(int, pa.Check.ge(4), coerce=True),
    },
    checks=pa.Check(
        lambda df: df["home_team_id"] != df["away_team_id"],
        error="home_team_id must differ from away_team_id",
    ),
    strict=True,
    coerce=True,
)

TEAM_GAME_STATS_SCHEMA = pa.DataFrameSchema(
    {
        "game_id": pa.Column(str),
        "team_id": pa.Column(int, coerce=True),
        "opponent_team_id": pa.Column(int, coerce=True),
        "is_home": pa.Column(bool, coerce=True),
        **_counting_columns(),
        "off_rating": pa.Column(float, nullable=True, coerce=True),
        "def_rating": pa.Column(float, nullable=True, coerce=True),
        "net_rating": pa.Column(float, nullable=True, coerce=True),
        "pace": pa.Column(float, pa.Check.ge(0), nullable=True, coerce=True),
        "possessions": pa.Column(float, pa.Check.ge(0), nullable=True, coerce=True),
    },
    strict=True,
)

PLAYER_GAME_STATS_SCHEMA = pa.DataFrameSchema(
    {
        "game_id": pa.Column(str),
        "player_id": pa.Column(int, coerce=True),
        "team_id": pa.Column(int, coerce=True),
        "opponent_team_id": pa.Column(int, coerce=True),
        "is_home": pa.Column(bool, coerce=True),
        "started": pa.Column(bool, coerce=True),
        "min": pa.Column(float, pa.Check.ge(0), nullable=True, coerce=True),
        **_counting_columns(),
        "plus_minus": pa.Column("Int64", nullable=True, coerce=True),
        "usage_rate": pa.Column(float, pa.Check.in_range(0.0, 1.0), nullable=True, coerce=True),
    },
    strict=True,
)

PLAY_BY_PLAY_SCHEMA = pa.DataFrameSchema(
    {
        "game_id": pa.Column(str),
        "event_num": pa.Column(int, coerce=True),
        "period": pa.Column(int, pa.Check.ge(1), coerce=True),
        "pc_time": pa.Column(str, nullable=True),
        "seconds_remaining_period": _nonneg_int(nullable=True),
        "action_type": pa.Column(str, nullable=True),
        "sub_type": pa.Column(str, nullable=True),
        "description": pa.Column(str, nullable=True),
        "home_score": _nonneg_int(nullable=True),
        "away_score": _nonneg_int(nullable=True),
        "player1_id": pa.Column("Int64", nullable=True, coerce=True),
        "player2_id": pa.Column("Int64", nullable=True, coerce=True),
        "player3_id": pa.Column("Int64", nullable=True, coerce=True),
        "team_id": pa.Column("Int64", nullable=True, coerce=True),
    },
    strict=True,
)

SHOTS_SCHEMA = pa.DataFrameSchema(
    {
        "game_id": pa.Column(str),
        "event_num": pa.Column(int, coerce=True),
        "player_id": pa.Column(int, coerce=True),
        "team_id": pa.Column(int, coerce=True),
        "period": pa.Column(int, pa.Check.ge(1), coerce=True),
        "seconds_remaining_period": _nonneg_int(nullable=True),
        "loc_x": pa.Column("Int64", pa.Check.in_range(*_COURT_X), nullable=True, coerce=True),
        "loc_y": pa.Column("Int64", pa.Check.in_range(*_COURT_Y), nullable=True, coerce=True),
        "shot_distance": _nonneg_int(nullable=True),
        "shot_zone": pa.Column(str, nullable=True),
        "shot_zone_area": pa.Column(str, nullable=True),
        "shot_zone_range": pa.Column(str, nullable=True),
        "shot_type": pa.Column(str, nullable=True),
        "action_type": pa.Column(str, nullable=True),
        "made": pa.Column(bool, coerce=True),
        "location_reliable": pa.Column(bool, coerce=True),
    },
    strict=True,
)

POSSESSIONS_SCHEMA = pa.DataFrameSchema(
    {
        "game_id": pa.Column(str),
        "period": pa.Column(int, pa.Check.ge(1), coerce=True),
        "start_seconds": _nonneg_int(nullable=True),
        "end_seconds": _nonneg_int(nullable=True),
        "offense_team_id": pa.Column(int, coerce=True),
        "defense_team_id": pa.Column(int, coerce=True),
        "points": pa.Column(int, pa.Check.in_range(0, 6), coerce=True),
        "off_player_ids": pa.Column(object, pa.Check(_is_list, element_wise=False)),
        "def_player_ids": pa.Column(object, pa.Check(_is_list, element_wise=False)),
    },
    strict=True,
)

SILVER_SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "games": GAMES_SCHEMA,
    "team_game_stats": TEAM_GAME_STATS_SCHEMA,
    "player_game_stats": PLAYER_GAME_STATS_SCHEMA,
    "play_by_play": PLAY_BY_PLAY_SCHEMA,
    "shots": SHOTS_SCHEMA,
    "possessions": POSSESSIONS_SCHEMA,
}


def validate(table: str, df: pd.DataFrame) -> pd.DataFrame:
    """Validate ``df`` against the silver schema for ``table``.

    Returns:
        The validated (coerced) DataFrame.

    Raises:
        DataValidationError: if validation fails (wrapping the Pandera error).
    """
    schema = SILVER_SCHEMAS.get(table)
    if schema is None:
        raise DataValidationError(f"no silver schema registered for table {table!r}")
    try:
        return schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        raise DataValidationError(f"{table} failed validation: {exc}") from exc
