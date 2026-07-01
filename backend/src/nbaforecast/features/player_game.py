"""Player-game features — feature-engineering.md Prompt 3 (§4 player-game catalog).

``build_player_game_features`` mirrors ``features/team_game.py``'s shape exactly: a pure
function over already-loaded silver DataFrames, one code path for both training (``as_of=None``,
one row per player per *completed* game) and serving (``as_of`` set, one row per player for that
date's scheduled games) — every feature computed only from games strictly before ``as_of`` via
``features.primitives``.

Two columns don't come from a leakage-safe primitive directly:
- ``opp_pos_def`` (opponent positional defense): the opponent's as-of-that-game season-to-date
  points allowed *to the player's own position*, expanding + shifted the same way team_game.py's
  ``opp_adj_net_rating`` derives strength-of-schedule — never the full season, never today's game.
- ``minutes_trend``: last-5-game rolling minutes minus the last-15-game rolling minutes (both
  already leakage-safe via ``rolling_as_of``) — a simple, checkable "is this player's role
  trending up or down" signal, positive when recent minutes exceed the longer baseline.

``player_rapm`` is intentionally left out of ``FEATURE_COLUMNS``/this builder — it's wired in by
T3.9 once player RAPM values exist; the gold column stays NULL until then (see
``features/materialize.py``).
"""

from datetime import date

import numpy as np
import pandas as pd

from nbaforecast.features.primitives import days_rest, rolling_as_of

ROLLING_WINDOWS = (5, 10, 15)
STD_WINDOW = 10
MINUTES_TREND_SHORT_WINDOW = 5
MINUTES_TREND_LONG_WINDOW = 15
_STAT_COLUMNS = ("pts", "reb", "ast", "fg3m")

KEY_COLUMNS = [
    "game_id",
    "player_id",
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
    "roll5_pts",
    "roll10_pts",
    "roll15_pts",
    "roll10_std_pts",
    "roll5_reb",
    "roll10_reb",
    "roll15_reb",
    "roll10_std_reb",
    "roll5_ast",
    "roll10_ast",
    "roll15_ast",
    "roll10_std_ast",
    "roll5_fg3m",
    "roll10_fg3m",
    "roll15_fg3m",
    "season_avg_pts",
    "season_avg_reb",
    "season_avg_ast",
    "season_avg_fg3m",
    "roll_minutes",
    "usage_rate",
    "minutes_trend",
    "opp_def_rating",
    "opp_pace",
    "opp_pos_def",
]


def build_player_game_features(
    games: pd.DataFrame,
    player_game_stats: pd.DataFrame,
    team_game_stats: pd.DataFrame,
    players: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Build the player-game feature table.

    Args:
        games: Silver ``games`` rows (schema: ``storage.models.silver.Game``).
        player_game_stats: Silver ``player_game_stats`` rows — completed-game box lines, one row
            per player per played game.
        team_game_stats: Silver ``team_game_stats`` rows — used to source the *opponent's*
            def_rating/pace for matchup context.
        players: Reference ``players`` rows (for ``position`` — positional-defense matchup).
        as_of: ``None`` builds the full historical table (training, one row per player per
            completed game). A date builds serving rows for that date's scheduled games.

    Returns:
        One row per player per game with ``KEY_COLUMNS`` + ``FEATURE_COLUMNS``.
    """
    games = games.assign(game_date=pd.to_datetime(games["game_date"]))
    history = _build_history(games, player_game_stats, players)

    if as_of is None:
        combined = history.assign(_is_target=True)
    else:
        targets = _scheduled_player_rows(games, player_game_stats, players, as_of)
        combined = pd.concat(
            [history.assign(_is_target=False), targets.assign(_is_target=True)], ignore_index=True
        )

    combined = _attach_rest(combined)
    combined = _attach_recent_production(combined)
    combined = _attach_season_to_date(combined)
    combined = _attach_role_usage(combined)
    team_form = _build_team_form_history(games, team_game_stats)
    combined = _attach_opponent_context(combined, team_form)
    combined = _attach_opponent_positional_defense(combined, games, player_game_stats, players)

    result = combined.loc[combined["_is_target"]].reset_index(drop=True)
    return result[KEY_COLUMNS + FEATURE_COLUMNS]


# ── Base rows ────────────────────────────────────────────────────────────────────────────────


def _build_history(
    games: pd.DataFrame, player_game_stats: pd.DataFrame, players: pd.DataFrame
) -> pd.DataFrame:
    """One row per player per *completed* game, with the game's season/date context."""
    completed = games.loc[
        games["status"] == "final",
        ["game_id", "season", "season_start_year", "game_date"],
    ]
    df = player_game_stats.merge(completed, on="game_id", how="inner")
    return df.merge(players[["player_id", "position"]], on="player_id", how="left")


def _scheduled_player_rows(
    games: pd.DataFrame, player_game_stats: pd.DataFrame, players: pd.DataFrame, as_of: date
) -> pd.DataFrame:
    """One row per player who most recently suited up for a team scheduled to play on ``as_of``.

    Mirrors team_game.py's ``_scheduled_team_rows`` shape, but rosters aren't a silver table here
    — a player's *team* for tonight is inferred from their most recent completed-game row
    (players who haven't played yet this history have no prior team and are excluded, matching
    team_game.py's own "no history -> no serving row" behavior for a team's very first game).
    """
    slate = games.loc[
        (games["game_date"].dt.date == as_of) & (games["status"] == "scheduled"),
        ["game_id", "season", "season_start_year", "game_date", "home_team_id", "away_team_id"],
    ]
    if slate.empty:
        return pd.DataFrame(
            columns=[
                "game_id",
                "season",
                "season_start_year",
                "game_date",
                "player_id",
                "team_id",
                "opponent_team_id",
                "is_home",
                "position",
            ]
        )

    latest_team = (
        player_game_stats.sort_values("game_id", kind="mergesort")
        .groupby("player_id", sort=False)[["team_id"]]
        .last()
        .reset_index()
    )
    latest_team = latest_team.merge(players[["player_id", "position"]], on="player_id", how="left")

    rows = []
    for _, game in slate.iterrows():
        for team_id, opponent_id, is_home in (
            (game["home_team_id"], game["away_team_id"], True),
            (game["away_team_id"], game["home_team_id"], False),
        ):
            roster = latest_team.loc[latest_team["team_id"] == team_id].copy()
            roster["game_id"] = game["game_id"]
            roster["season"] = game["season"]
            roster["season_start_year"] = game["season_start_year"]
            roster["game_date"] = game["game_date"]
            roster["opponent_team_id"] = opponent_id
            roster["is_home"] = is_home
            rows.append(roster)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ── Expanding (season-to-date) helper ───────────────────────────────────────────────────────
# Not in features/primitives.py: primitives scopes rolling/as-of-join/rest/density/travel only
# (feature-engineering.md Prompt 1). Mirrors team_game.py's own ``_expanding_as_of``.


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


def _attach_rest(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["days_rest"] = days_rest(df, "player_id", "game_date")
    df["is_back_to_back"] = np.where(
        df["days_rest"].isna(), np.nan, (df["days_rest"] <= 1).astype(float)
    )
    return df


def _attach_recent_production(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for window in ROLLING_WINDOWS:
        for stat in _STAT_COLUMNS:
            df[f"roll{window}_{stat}"] = rolling_as_of(
                df, "player_id", stat, window=window, datetime_col="game_date"
            )
    # roll10_std_{stat} — pts/reb/ast only (not fg3m, per the gold schema).
    for stat in ("pts", "reb", "ast"):
        df[f"roll{STD_WINDOW}_std_{stat}"] = rolling_as_of(
            df, "player_id", stat, window=STD_WINDOW, datetime_col="game_date", agg="std"
        )
    return df


def _attach_season_to_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for stat in _STAT_COLUMNS:
        df[f"season_avg_{stat}"] = _expanding_as_of(df, ["player_id", "season"], stat, "game_date")
    return df


def _attach_role_usage(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling minutes/usage_rate (role proxy), plus a short-vs-long rolling-minutes trend."""
    df = df.copy()
    df["roll_minutes"] = rolling_as_of(
        df, "player_id", "min", window=STD_WINDOW, datetime_col="game_date"
    )
    df["usage_rate"] = rolling_as_of(
        df, "player_id", "usage_rate", window=STD_WINDOW, datetime_col="game_date"
    )
    roll_minutes_short = rolling_as_of(
        df, "player_id", "min", window=MINUTES_TREND_SHORT_WINDOW, datetime_col="game_date"
    )
    roll_minutes_long = rolling_as_of(
        df, "player_id", "min", window=MINUTES_TREND_LONG_WINDOW, datetime_col="game_date"
    )
    df["minutes_trend"] = roll_minutes_short - roll_minutes_long
    return df


def _build_team_form_history(games: pd.DataFrame, team_game_stats: pd.DataFrame) -> pd.DataFrame:
    """Each team's own as-of (shifted) rolling def_rating/pace, keyed by ``game_id``.

    Includes **every** game on the ``games`` slate for each team — completed games (with a real
    box score) and, if present, later scheduled games (no box score yet) — the same "append
    tonight's game before computing the rolling primitive" trick team_game.py's own
    ``_build_history``/``_scheduled_team_rows`` split uses, so ``rolling_as_of``'s ``shift(1)``
    naturally produces each team's correct pre-game value *for that exact game_id*, whether or
    not that game has been played. Keying by ``game_id`` (rather than ``game_date`` + an as-of
    join) is what makes this exact for two teams who play each other on the same date — the
    opponent's row for the shared ``game_id`` is always this game's own pre-game value, never a
    stale prior date's value.
    """
    home = games[["game_id", "game_date", "home_team_id"]].rename(
        columns={"home_team_id": "team_id"}
    )
    away = games[["game_id", "game_date", "away_team_id"]].rename(
        columns={"away_team_id": "team_id"}
    )
    slate = pd.concat([home, away], ignore_index=True)

    team_history = slate.merge(
        team_game_stats[["game_id", "team_id", "def_rating", "pace"]],
        on=["game_id", "team_id"],
        how="left",
    ).sort_values("game_date", kind="mergesort")
    team_history["def_rating_asof"] = rolling_as_of(
        team_history, "team_id", "def_rating", window=STD_WINDOW, datetime_col="game_date"
    )
    team_history["pace_asof"] = rolling_as_of(
        team_history, "team_id", "pace", window=STD_WINDOW, datetime_col="game_date"
    )
    return team_history[["game_id", "team_id", "def_rating_asof", "pace_asof"]]


def _attach_opponent_context(df: pd.DataFrame, team_form: pd.DataFrame) -> pd.DataFrame:
    """Attach the opponent *team's* as-of rolling def_rating/pace for this specific matchup.

    Joined by ``(game_id, opponent_team_id)`` — the opponent's row for this exact game_id in
    ``team_form`` already *is* their pre-game value entering this matchup (see
    ``_build_team_form_history``), so a plain merge is exact for both a historical training row
    and a serving row, with no as-of-join date-matching subtlety to get wrong.
    """
    opp_form = team_form.rename(
        columns={
            "team_id": "opponent_team_id",
            "def_rating_asof": "opp_def_rating",
            "pace_asof": "opp_pace",
        }
    )
    return df.merge(opp_form, on=["game_id", "opponent_team_id"], how="left")


def _attach_opponent_positional_defense(
    df: pd.DataFrame,
    games: pd.DataFrame,
    player_game_stats: pd.DataFrame,
    players: pd.DataFrame,
) -> pd.DataFrame:
    """Opponent's as-of season-to-date points allowed to the player's own position.

    Computed from the full completed box-score history (every finished game, not just games the
    player rows in ``df`` cover): for each completed game, sum the *opposing* team's points
    allowed to each position (points scored by players of that position on the team they played
    against), then expanding-average per (defending_team, position, season) and shift — the same
    leakage-safe shape as team_game.py's ``opp_adj_net_rating``.

    Keyed onto each team's full ``games`` slate by ``game_id`` (not a ``game_date`` as-of join) —
    the same reasoning as ``_build_team_form_history``: two teams meeting on the same date must
    resolve to *that exact game's* pre-game value, which a date-based as-of join can't
    distinguish from a stale earlier date once the game itself (today's, box-score-less) is
    excluded from the completed history.
    """
    completed = games.loc[games["status"] == "final", ["game_id", "season", "game_date"]]
    box = player_game_stats.merge(completed, on="game_id", how="inner").merge(
        players[["player_id", "position"]], on="player_id", how="left"
    )

    position_pts = (
        box.groupby(["game_id", "team_id", "position"], dropna=False)["pts"]
        .sum()
        .reset_index(name="position_pts")
    )
    opponent_by_game_team = box[["game_id", "team_id", "opponent_team_id"]].drop_duplicates()
    allowed = position_pts.merge(opponent_by_game_team, on=["game_id", "team_id"], how="left")
    allowed = allowed.rename(columns={"opponent_team_id": "defending_team_id"})
    allowed = allowed.merge(completed, on="game_id", how="left")

    # Every (defending_team, position, season) combination that actually occurs, so the slate
    # built below has a season to group on even for a defending team's very first game of it.
    positions = players["position"].dropna().unique()
    team_seasons = games[["game_id", "season", "home_team_id", "away_team_id", "game_date"]]
    home_slate = team_seasons.rename(columns={"home_team_id": "defending_team_id"})[
        ["game_id", "season", "defending_team_id", "game_date"]
    ]
    away_slate = team_seasons.rename(columns={"away_team_id": "defending_team_id"})[
        ["game_id", "season", "defending_team_id", "game_date"]
    ]
    team_game_slate = pd.concat([home_slate, away_slate], ignore_index=True)
    slate = team_game_slate.merge(pd.DataFrame({"position": positions}), how="cross")

    slate = slate.merge(
        allowed[["game_id", "defending_team_id", "position", "position_pts"]],
        on=["game_id", "defending_team_id", "position"],
        how="left",
    ).sort_values("game_date", kind="mergesort")
    slate["opp_pos_def_asof"] = _expanding_as_of(
        slate, ["defending_team_id", "position", "season"], "position_pts", "game_date"
    )

    defense_history = slate[
        ["game_id", "defending_team_id", "position", "opp_pos_def_asof"]
    ].rename(columns={"defending_team_id": "opponent_team_id"})

    result = df.merge(defense_history, on=["game_id", "opponent_team_id", "position"], how="left")
    result["opp_pos_def"] = result["opp_pos_def_asof"]
    return result.drop(columns=["opp_pos_def_asof"])
