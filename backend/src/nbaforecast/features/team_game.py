"""Team-game features — feature-engineering.md Prompt 2 (§4 team-game catalog).

``build_team_game_features`` is a pure function over already-loaded silver DataFrames (mirrors
the ``ingestion/parse.py`` vs ``ingestion/load.py`` split: parsing/computation is pure and
DB-free, I/O is a separate thin layer materialized in ``features/materialize.py``, T2.3).

The same function call serves both training and serving: when ``as_of`` is ``None`` it returns
one row per team per *completed* game (training); when ``as_of`` is a date it returns one row
per team for that date's *scheduled* games (serving), with every feature still computed only
from games strictly before ``as_of``. This is achieved by appending the scheduled target rows
(with no box-score result yet) onto the same chronological per-team history before running the
``features.primitives`` helpers — every primitive already excludes a row's own value via
``shift(1)``, so an appended, result-less "tonight" row gets exactly the same treatment as a
historical row's pre-game feature value. One code path, no train/serve skew.
"""

import math
from datetime import date

import numpy as np
import pandas as pd

from nbaforecast.features.primitives import (
    days_rest,
    rolling_as_of,
    schedule_density,
    travel_distance,
)

INITIAL_ELO = 1500.0
ELO_K = 20.0
ELO_HOME_ADVANTAGE = 100.0
ROLLING_WINDOWS = (5, 10)
SCHEDULE_DENSITY_WINDOWS = (7, 14)

KEY_COLUMNS = [
    "game_id",
    "team_id",
    "opponent_team_id",
    "season",
    "season_start_year",
    "game_date",
    "is_home",
]
FEATURE_COLUMNS = [
    "days_rest",
    "is_back_to_back",
    "games_last_7d",
    "games_last_14d",
    "travel_distance_km",
    "tz_shift",
    "roll5_net_rating",
    "roll10_net_rating",
    "roll5_off_rating",
    "roll10_off_rating",
    "roll5_def_rating",
    "roll10_def_rating",
    "roll5_pace",
    "roll10_pace",
    "season_off_rating",
    "season_def_rating",
    "season_net_rating",
    "season_pace",
    "win_pct_to_date",
    "elo",
    "opp_adj_net_rating",
    "h2h_record",
    "h2h_avg_margin",
    "rest_advantage",
    "rating_diff",
    "elo_diff",
]


def build_team_game_features(
    games: pd.DataFrame,
    team_game_stats: pd.DataFrame,
    teams: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build the team-game feature table.

    Args:
        games: Silver ``games`` rows (schema: ``storage.models.silver.Game``).
        team_game_stats: Silver ``team_game_stats`` rows — completed-game box lines, one row per
            team per played game.
        teams: Reference ``teams`` rows (for ``arena_lat``/``arena_lon``).
        as_of: ``None`` builds the full historical table (training, one row per team per
            completed game). A date builds serving rows for that date's scheduled games.

    Returns:
        One row per team per game with ``KEY_COLUMNS`` + ``FEATURE_COLUMNS``.
    """
    games = games.assign(game_date=pd.to_datetime(games["game_date"]))
    history = _build_history(games, team_game_stats, teams)

    if as_of is None:
        combined = history.assign(_is_target=True)
    else:
        targets = _scheduled_team_rows(games, teams, as_of)
        combined = pd.concat(
            [history.assign(_is_target=False), targets.assign(_is_target=True)], ignore_index=True
        )

    combined = _attach_rest_schedule_travel(combined)
    combined = _attach_recent_form(combined)
    combined = _attach_season_to_date(combined)
    combined = _attach_elo(combined, games)
    combined = _attach_opponent_columns(combined)
    combined = _attach_matchup(combined)
    combined = _attach_opponent_adjusted_rating(combined)
    combined = _attach_differentials(combined)

    result = combined.loc[combined["_is_target"]].reset_index(drop=True)
    return result[KEY_COLUMNS + FEATURE_COLUMNS]


# ── Base rows ────────────────────────────────────────────────────────────────────────────────


def _attach_location(df: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    """Attach where the game was played: the home team's arena, for both teams' rows."""
    arenas = teams[["team_id", "arena_lat", "arena_lon"]].rename(
        columns={"team_id": "home_team_id", "arena_lat": "loc_lat", "arena_lon": "loc_lon"}
    )
    return df.merge(arenas, on="home_team_id", how="left")


def _build_history(
    games: pd.DataFrame, team_game_stats: pd.DataFrame, teams: pd.DataFrame
) -> pd.DataFrame:
    """One row per team per *completed* game, with outcome (win/margin) and game location."""
    completed = games.loc[
        games["status"] == "final",
        [
            "game_id",
            "season",
            "season_start_year",
            "game_date",
            "home_team_id",
            "away_team_id",
            "home_score",
            "away_score",
        ],
    ]
    df = team_game_stats.merge(completed, on="game_id", how="inner")
    team_score = np.where(df["is_home"], df["home_score"], df["away_score"])
    opp_score = np.where(df["is_home"], df["away_score"], df["home_score"])
    df["win"] = (team_score > opp_score).astype(float)
    df["margin"] = (team_score - opp_score).astype(float)
    df = _attach_location(df, teams)
    return df


def _scheduled_team_rows(games: pd.DataFrame, teams: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """One row per team for each game scheduled on ``as_of`` (serving targets, no result yet)."""
    slate = games.loc[
        (games["game_date"].dt.date == as_of) & (games["status"] == "scheduled"),
        ["game_id", "season", "season_start_year", "game_date", "home_team_id", "away_team_id"],
    ]
    slate = _attach_location(slate, teams)
    common = [
        "game_id",
        "season",
        "season_start_year",
        "game_date",
        "home_team_id",
        "away_team_id",
        "loc_lat",
        "loc_lon",
    ]
    home = (
        slate[common]
        .rename(columns={"home_team_id": "team_id", "away_team_id": "opponent_team_id"})
        .assign(is_home=True)
    )
    away = (
        slate[common]
        .rename(columns={"away_team_id": "team_id", "home_team_id": "opponent_team_id"})
        .assign(is_home=False)
    )
    return pd.concat([home, away], ignore_index=True)


# ── Expanding (season-to-date) helper ───────────────────────────────────────────────────────
# Not in features/primitives.py: Prompt 1 scopes rolling/as-of-join/rest/density/travel only.
# Mirrors the same leakage-safe shape (sort, shift(1), aggregate, realign) for an unbounded
# (expanding) window instead of a fixed one.


def _expanding_as_of(
    df: pd.DataFrame, group_keys: str | list[str], value: str, datetime_col: str
) -> pd.Series:
    keys = [group_keys] if isinstance(group_keys, str) else group_keys
    parts = [
        group.sort_values(datetime_col, kind="mergesort")[value]
        .shift(1)
        .expanding(min_periods=1)
        .mean()
        for _, group in df.groupby(keys, sort=False)
    ]
    result = pd.concat(parts) if parts else pd.Series(dtype="float64")
    return result.reindex(df.index)


# ── Feature groups ──────────────────────────────────────────────────────────────────────────

# Longitude bands approximating the four continental-US timezones NBA arenas sit in. A jet-lag
# proxy feature, not a timezone database — ignores DST transitions and Arizona's no-DST quirk.
_TZ_LON_BANDS = ([-87.0, -5], [-102.0, -6], [-115.0, -7])


def _utc_offset_hours(lon: pd.Series) -> pd.Series:
    # Coerce first: NULL reference coordinates arrive as object-dtype None (M3.5), which
    # band comparisons can't handle; missing longitude yields NaN offset (imputed later),
    # not a fake west-coast default.
    lon = pd.to_numeric(lon, errors="coerce")
    conditions = [lon > threshold for threshold, _ in _TZ_LON_BANDS]
    choices = [hours for _, hours in _TZ_LON_BANDS]
    offsets = pd.Series(
        np.select(conditions, choices, default=-8), index=lon.index, dtype="float64"
    )
    return offsets.where(lon.notna())


def _attach_rest_schedule_travel(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["days_rest"] = days_rest(df, "team_id", "game_date")
    df["is_back_to_back"] = np.where(
        df["days_rest"].isna(), np.nan, (df["days_rest"] <= 1).astype(float)
    )
    for window in SCHEDULE_DENSITY_WINDOWS:
        df[f"games_last_{window}d"] = schedule_density(
            df, "team_id", "game_date", window_days=window
        )
    df["travel_distance_km"] = travel_distance(
        df, "team_id", lat_col="loc_lat", lon_col="loc_lon", datetime_col="game_date"
    )
    df["_utc_offset"] = _utc_offset_hours(df["loc_lon"])
    prev_offset = rolling_as_of(df, "team_id", "_utc_offset", window=1, datetime_col="game_date")
    df["tz_shift"] = df["_utc_offset"] - prev_offset
    return df.drop(columns=["_utc_offset"])


def _attach_recent_form(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for window in ROLLING_WINDOWS:
        for metric in ("net_rating", "off_rating", "def_rating", "pace"):
            df[f"roll{window}_{metric}"] = rolling_as_of(
                df, "team_id", metric, window=window, datetime_col="game_date"
            )
    return df


def _attach_season_to_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for metric, column in (
        ("net_rating", "season_net_rating"),
        ("off_rating", "season_off_rating"),
        ("def_rating", "season_def_rating"),
        ("pace", "season_pace"),
        ("win", "win_pct_to_date"),
    ):
        df[column] = _expanding_as_of(df, ["team_id", "season"], metric, "game_date")
    return df


def _compute_elo(games: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, float]]:
    """Process completed games chronologically with a margin-of-victory-weighted Elo update.

    Returns each game's *pre-game* rating for both teams (for historical/training rows) and the
    final post-history rating per team (for serving rows — "current form" as of right now).
    """
    completed = games.loc[games["status"] == "final"].sort_values(
        ["game_date", "game_id"], kind="mergesort"
    )
    game_ids = completed["game_id"].to_numpy()
    home_ids = completed["home_team_id"].to_numpy()
    away_ids = completed["away_team_id"].to_numpy()
    home_scores = completed["home_score"].to_numpy(dtype="float64")
    away_scores = completed["away_score"].to_numpy(dtype="float64")

    rating: dict[int, float] = {}
    records: list[dict[str, float | str | int]] = []
    for game_id, home_id_raw, away_id_raw, home_score, away_score in zip(
        game_ids, home_ids, away_ids, home_scores, away_scores, strict=True
    ):
        home_id, away_id = int(home_id_raw), int(away_id_raw)
        home_elo = rating.get(home_id, INITIAL_ELO)
        away_elo = rating.get(away_id, INITIAL_ELO)
        records.append({"game_id": game_id, "team_id": home_id, "elo": home_elo})
        records.append({"game_id": game_id, "team_id": away_id, "elo": away_elo})

        expected_home = 1.0 / (1.0 + 10 ** (-((home_elo + ELO_HOME_ADVANTAGE) - away_elo) / 400))
        home_won = 1.0 if home_score > away_score else 0.0
        margin = abs(home_score - away_score)
        elo_diff_winner = (home_elo - away_elo) if home_won else (away_elo - home_elo)
        mov_multiplier = math.log(margin + 1) * (2.2 / (max(0.0, elo_diff_winner) * 0.001 + 2.2))
        delta = ELO_K * mov_multiplier * (home_won - expected_home)

        rating[home_id] = home_elo + delta
        rating[away_id] = away_elo - delta

    pre_game_elo = (
        pd.DataFrame.from_records(records)
        if records
        else pd.DataFrame(columns=["game_id", "team_id", "elo"])
    )
    return pre_game_elo, rating


def _attach_elo(df: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    pre_game_elo, final_rating = _compute_elo(games)
    df = df.merge(pre_game_elo, on=["game_id", "team_id"], how="left")
    missing = df["elo"].isna()
    df.loc[missing, "elo"] = df.loc[missing, "team_id"].map(final_rating).fillna(INITIAL_ELO)
    return df


def _attach_opponent_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Pull each row's *specific* opponent's days_rest/season_net_rating/elo for this matchup."""
    opp = df[["game_id", "team_id", "days_rest", "season_net_rating", "elo"]].rename(
        columns={
            "team_id": "opponent_team_id",
            "days_rest": "opp_days_rest",
            "season_net_rating": "opp_season_net_rating",
            "elo": "opp_elo",
        }
    )
    return df.merge(opp, on=["game_id", "opponent_team_id"], how="left")


def _attach_matchup(df: pd.DataFrame) -> pd.DataFrame:
    """Head-to-head record/margin vs tonight's specific opponent, prior meetings only."""
    df = df.copy()
    df["h2h_record"] = _expanding_as_of(df, ["team_id", "opponent_team_id"], "win", "game_date")
    df["h2h_avg_margin"] = _expanding_as_of(
        df, ["team_id", "opponent_team_id"], "margin", "game_date"
    )
    return df


def _attach_opponent_adjusted_rating(df: pd.DataFrame) -> pd.DataFrame:
    """Season-to-date net rating adjusted by the average strength of opponents faced so far.

    A simplified strength-of-schedule adjustment (not a full iterative SRS solve): each prior
    opponent's own as-of-that-game season-to-date net rating is averaged (expanding, shifted —
    so it never includes tonight's opponent) and subtracted from the team's own rating.
    """
    df = df.copy()
    opp_strength_to_date = _expanding_as_of(df, "team_id", "opp_season_net_rating", "game_date")
    df["opp_adj_net_rating"] = df["season_net_rating"] - opp_strength_to_date
    return df


def _attach_differentials(df: pd.DataFrame) -> pd.DataFrame:
    """Home/away-agnostic differentials, always expressed as this row's team minus opponent."""
    df = df.copy()
    df["rest_advantage"] = df["days_rest"] - df["opp_days_rest"]
    df["rating_diff"] = df["season_net_rating"] - df["opp_season_net_rating"]
    df["elo_diff"] = df["elo"] - df["opp_elo"]
    return df
