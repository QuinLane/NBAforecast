"""Unit tests for player-game features (feature-engineering.md Prompt 3).

Builds a small, hand-computable synthetic roster (2 players, 2 seasons, one upcoming scheduled
game) and checks every feature group against manually-derived expectations, plus the
train/serve code path (``as_of`` set vs unset) for internal consistency. The formal no-leakage
and train/serve-parity regression suite lives in ``test_player_game_leakage.py``; this file is
this task's own correctness check on top of that.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.player_game import build_player_game_features

TEAM_A, TEAM_B = 1, 2
PLAYER_A, PLAYER_B = 101, 201
SEASON_1, SEASON_1_START = "2023-24", 2023
SEASON_2, SEASON_2_START = "2024-25", 2024


def _teams() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"team_id": TEAM_A, "arena_lat": 34.05, "arena_lon": -118.24},
            {"team_id": TEAM_B, "arena_lat": 40.71, "arena_lon": -74.01},
        ]
    )


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": PLAYER_A, "position": "G"},
            {"player_id": PLAYER_B, "position": "F"},
        ]
    )


def _games() -> pd.DataFrame:
    rows = [
        ("G1", SEASON_1, SEASON_1_START, "2023-10-24", TEAM_A, TEAM_B, 110, 100, "final"),
        ("G2", SEASON_1, SEASON_1_START, "2023-10-25", TEAM_B, TEAM_A, 90, 100, "final"),
        ("G3", SEASON_1, SEASON_1_START, "2023-10-29", TEAM_A, TEAM_B, 130, 100, "final"),
        ("G5", SEASON_2, SEASON_2_START, "2024-10-22", TEAM_B, TEAM_A, 101, 99, "final"),
        ("G7", SEASON_2, SEASON_2_START, "2024-10-25", TEAM_A, TEAM_B, np.nan, np.nan, "scheduled"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "game_id",
            "season",
            "season_start_year",
            "game_date",
            "home_team_id",
            "away_team_id",
            "home_score",
            "away_score",
            "status",
        ],
    )


def _team_game_stats() -> pd.DataFrame:
    rows = [
        ("G1", TEAM_A, TEAM_B, True, 115, 100, 15, 98),
        ("G1", TEAM_B, TEAM_A, False, 100, 115, -15, 98),
        ("G2", TEAM_A, TEAM_B, False, 110, 95, 15, 102),
        ("G2", TEAM_B, TEAM_A, True, 95, 110, -15, 102),
        ("G3", TEAM_A, TEAM_B, True, 120, 90, 30, 100),
        ("G3", TEAM_B, TEAM_A, False, 90, 120, -30, 100),
        ("G5", TEAM_B, TEAM_A, True, 101, 99, 2, 97),
        ("G5", TEAM_A, TEAM_B, False, 99, 101, -2, 97),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "game_id",
            "team_id",
            "opponent_team_id",
            "is_home",
            "off_rating",
            "def_rating",
            "net_rating",
            "pace",
        ],
    )


def _player_game_stats() -> pd.DataFrame:
    # (game_id, player_id, team_id, opponent_team_id, is_home, min, pts, reb, ast, fg3m, usage_rate)
    rows = [
        ("G1", PLAYER_A, TEAM_A, TEAM_B, True, 30, 20, 5, 4, 2, 0.25),
        ("G1", PLAYER_B, TEAM_B, TEAM_A, False, 28, 12, 8, 2, 1, 0.18),
        ("G2", PLAYER_A, TEAM_A, TEAM_B, False, 32, 24, 6, 5, 3, 0.27),
        ("G2", PLAYER_B, TEAM_B, TEAM_A, True, 26, 10, 7, 3, 0, 0.17),
        ("G3", PLAYER_A, TEAM_A, TEAM_B, True, 34, 30, 4, 6, 4, 0.30),
        ("G3", PLAYER_B, TEAM_B, TEAM_A, False, 27, 14, 9, 2, 1, 0.19),
        ("G5", PLAYER_A, TEAM_A, TEAM_B, False, 29, 18, 5, 5, 2, 0.24),
        ("G5", PLAYER_B, TEAM_B, TEAM_A, True, 25, 11, 6, 2, 1, 0.16),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "game_id",
            "player_id",
            "team_id",
            "opponent_team_id",
            "is_home",
            "min",
            "pts",
            "reb",
            "ast",
            "fg3m",
            "usage_rate",
        ],
    )


def _row(df: pd.DataFrame, game_id: str, player_id: int) -> pd.Series:
    matches = df.loc[(df["game_id"] == game_id) & (df["player_id"] == player_id)]
    assert len(matches) == 1
    return matches.iloc[0]


def _build(as_of: date | None = None) -> pd.DataFrame:
    return build_player_game_features(
        _games(), _player_game_stats(), _team_game_stats(), _players(), as_of=as_of
    )


# ── Shape ────────────────────────────────────────────────────────────────────────────────────


def test_training_returns_one_row_per_player_per_completed_game() -> None:
    out = _build()
    assert len(out) == 8  # 4 completed games x 2 players; G7 (scheduled) excluded
    assert set(out["game_id"]) == {"G1", "G2", "G3", "G5"}


# ── First game / no-history ─────────────────────────────────────────────────────────────────


def test_first_ever_game_has_nan_history_features() -> None:
    out = _build()
    g1_a = _row(out, "G1", PLAYER_A)

    assert np.isnan(g1_a["days_rest"])
    assert np.isnan(g1_a["roll5_pts"])
    assert np.isnan(g1_a["season_avg_pts"])
    assert np.isnan(g1_a["opp_def_rating"])


# ── Rest / back-to-back ──────────────────────────────────────────────────────────────────────


def test_days_rest_and_back_to_back() -> None:
    out = _build()
    g2_a = _row(out, "G2", PLAYER_A)  # G1 (10-24) -> G2 (10-25): 1 day later
    assert g2_a["days_rest"] == 1
    assert g2_a["is_back_to_back"] == 1.0

    g3_a = _row(out, "G3", PLAYER_A)  # G2 (10-25) -> G3 (10-29): 4 days later
    assert g3_a["days_rest"] == 4
    assert g3_a["is_back_to_back"] == 0.0


# ── Recent production (rolling) ──────────────────────────────────────────────────────────────


def test_rolling_pts_uses_only_prior_games() -> None:
    out = _build()
    g2_a = _row(out, "G2", PLAYER_A)
    assert g2_a["roll5_pts"] == 20.0  # only G1 (pts=20) is prior

    g3_a = _row(out, "G3", PLAYER_A)
    assert g3_a["roll5_pts"] == pytest.approx((20.0 + 24.0) / 2)  # G1, G2

    g5_a = _row(out, "G5", PLAYER_A)  # season boundary; rolling form is not season-scoped
    assert g5_a["roll5_pts"] == pytest.approx((20.0 + 24.0 + 30.0) / 3)


# ── Season-to-date (resets per season) ──────────────────────────────────────────────────────


def test_season_avg_resets_at_season_boundary() -> None:
    out = _build()
    g3_a = _row(out, "G3", PLAYER_A)  # 3rd game of season 2023-24
    assert g3_a["season_avg_pts"] == pytest.approx((20.0 + 24.0) / 2)

    g5_a = _row(out, "G5", PLAYER_A)  # 1st game of season 2024-25 — resets
    assert np.isnan(g5_a["season_avg_pts"])


# ── Role/usage ────────────────────────────────────────────────────────────────────────────────


def test_roll_minutes_and_usage_rate_use_only_prior_games() -> None:
    out = _build()
    g2_a = _row(out, "G2", PLAYER_A)
    assert g2_a["roll_minutes"] == pytest.approx(30.0)  # only G1's 30 minutes prior
    assert g2_a["usage_rate"] == pytest.approx(0.25)  # only G1's usage prior


def test_minutes_trend_is_short_minus_long_rolling_average() -> None:
    out = _build()
    g3_a = _row(out, "G3", PLAYER_A)
    # short window (5) == long window (15) with only 2 prior games -> trend is 0
    assert g3_a["minutes_trend"] == pytest.approx(0.0)


# ── Opponent context ─────────────────────────────────────────────────────────────────────────


def test_opponent_def_rating_and_pace_reflect_opponent_as_of_form() -> None:
    out = _build()
    g3_a = _row(out, "G3", PLAYER_A)  # opponent is team B, entering its 3rd meeting (G1, G2 prior)
    assert g3_a["opp_def_rating"] == pytest.approx((115.0 + 110.0) / 2)  # team B's def_rating avg
    assert g3_a["opp_pace"] == pytest.approx((98.0 + 102.0) / 2)


def test_opponent_positional_defense_matches_points_allowed_to_position() -> None:
    out = _build()
    # PLAYER_A is a guard; opponent (team B) has allowed points to guards only via team A's own
    # guard (PLAYER_A) so far — checked at G3 (team B's 2nd meeting with team A this season).
    g3_a = _row(out, "G3", PLAYER_A)
    assert g3_a["opp_pos_def"] == pytest.approx((20.0 + 24.0) / 2)


# ── Serving (as_of) ──────────────────────────────────────────────────────────────────────────


def test_serving_builds_only_the_requested_slate_from_completed_history() -> None:
    out = _build(as_of=date(2024, 10, 25))
    assert len(out) == 2
    assert set(out["game_id"]) == {"G7"}
    assert set(out["player_id"]) == {PLAYER_A, PLAYER_B}

    tonight_a = _row(out, "G7", PLAYER_A)
    assert tonight_a["days_rest"] == 3  # last played G5 on 2024-10-22
    assert tonight_a["season_avg_pts"] == pytest.approx(18.0)  # only G5 so far this season
