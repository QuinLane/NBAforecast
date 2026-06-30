"""Unit tests for team-game features (feature-engineering.md Prompt 2).

Builds a small, hand-computable synthetic league (3 teams, 2 seasons, one upcoming scheduled
game) and checks every feature group against manually-derived expectations, plus the
train/serve code path (``as_of`` set vs unset) for internal consistency. The formal no-leakage
and train/serve-parity regression suite lives in T2.4; this file is T2.2's own correctness
check on top of that.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.team_game import INITIAL_ELO, build_team_game_features

TEAM_A, TEAM_B, TEAM_C = 1, 2, 3
SEASON_1, SEASON_1_START = "2023-24", 2023
SEASON_2, SEASON_2_START = "2024-25", 2024


def _teams() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"team_id": TEAM_A, "arena_lat": 34.05, "arena_lon": -118.24},  # LA
            {"team_id": TEAM_B, "arena_lat": 40.71, "arena_lon": -74.01},  # NYC
            {"team_id": TEAM_C, "arena_lat": 41.88, "arena_lon": -87.63},  # Chicago
        ]
    )


def _games() -> pd.DataFrame:
    rows = [
        # game_id, season, season_start_year, date, home, away, home_score, away_score, status
        ("G1", SEASON_1, SEASON_1_START, "2023-10-24", TEAM_A, TEAM_B, 110, 100, "final"),
        ("G2", SEASON_1, SEASON_1_START, "2023-10-25", TEAM_B, TEAM_A, 90, 100, "final"),
        ("G3", SEASON_1, SEASON_1_START, "2023-10-29", TEAM_A, TEAM_B, 130, 100, "final"),
        ("G4", SEASON_1, SEASON_1_START, "2023-11-05", TEAM_A, TEAM_C, 108, 95, "final"),
        ("G5", SEASON_2, SEASON_2_START, "2024-10-22", TEAM_B, TEAM_A, 101, 99, "final"),
        ("G7", SEASON_2, SEASON_2_START, "2024-10-25", TEAM_A, TEAM_C, np.nan, np.nan, "scheduled"),
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
    # (game_id, team_id, opponent_team_id, is_home, off_rating, def_rating, net_rating, pace)
    rows = [
        ("G1", TEAM_A, TEAM_B, True, 115, 100, 15, 98),
        ("G1", TEAM_B, TEAM_A, False, 100, 115, -15, 98),
        ("G2", TEAM_A, TEAM_B, False, 110, 95, 15, 102),
        ("G2", TEAM_B, TEAM_A, True, 95, 110, -15, 102),
        ("G3", TEAM_A, TEAM_B, True, 120, 90, 30, 100),
        ("G3", TEAM_B, TEAM_A, False, 90, 120, -30, 100),
        ("G4", TEAM_A, TEAM_C, True, 112, 99, 13, 99),
        ("G4", TEAM_C, TEAM_A, False, 99, 112, -13, 99),
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


def _row(df: pd.DataFrame, game_id: str, team_id: int) -> pd.Series:
    matches = df.loc[(df["game_id"] == game_id) & (df["team_id"] == team_id)]
    assert len(matches) == 1
    return matches.iloc[0]


# ── Shape ────────────────────────────────────────────────────────────────────────────────────


def test_training_returns_one_row_per_team_per_completed_game() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())
    assert len(out) == 10  # 5 completed games x 2 teams; G7 (scheduled) excluded
    assert set(out["game_id"]) == {"G1", "G2", "G3", "G4", "G5"}


# ── First game / no-history ─────────────────────────────────────────────────────────────────


def test_first_ever_game_has_nan_history_features_and_initial_elo() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())
    g1_a = _row(out, "G1", TEAM_A)

    assert np.isnan(g1_a["days_rest"])
    assert np.isnan(g1_a["roll5_net_rating"])
    assert np.isnan(g1_a["std_net_rating"])
    assert np.isnan(g1_a["h2h_win_pct"])
    assert g1_a["elo"] == INITIAL_ELO


# ── Rest / back-to-back / travel ────────────────────────────────────────────────────────────


def test_days_rest_and_back_to_back() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())
    g2_a = _row(out, "G2", TEAM_A)  # G1 (10-24) -> G2 (10-25): 1 day later

    assert g2_a["days_rest"] == 1
    assert g2_a["is_back_to_back"] == 1.0

    g3_a = _row(out, "G3", TEAM_A)  # G2 (10-25) -> G3 (10-29): 4 days later
    assert g3_a["days_rest"] == 4
    assert g3_a["is_back_to_back"] == 0.0


def test_travel_distance_round_trip_la_nyc() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())
    g2_a = _row(out, "G2", TEAM_A)  # team A travels LA -> NYC for G2

    assert g2_a["travel_distance_km"] == pytest.approx(3936, rel=0.02)


# ── Recent form (rolling) ───────────────────────────────────────────────────────────────────


def test_rolling_form_uses_only_prior_games_and_does_not_reset_at_season_boundary() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())

    g2_a = _row(out, "G2", TEAM_A)
    assert g2_a["roll5_net_rating"] == 15.0  # only G1 (net=15) is prior

    g3_a = _row(out, "G3", TEAM_A)
    assert g3_a["roll5_net_rating"] == pytest.approx((15.0 + 15.0) / 2)  # G1, G2

    # G5 is season 2024-25, but rolling form is a fixed-window feature, not season-scoped — it
    # still sees team A's last games from season 2023-24 (G1, G2, G3, G4).
    g5_a = _row(out, "G5", TEAM_A)
    assert g5_a["roll5_net_rating"] == pytest.approx((15.0 + 15.0 + 30.0 + 13.0) / 4)


# ── Season-to-date (resets per season) ──────────────────────────────────────────────────────


def test_season_to_date_resets_at_season_boundary() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())

    g4_a = _row(out, "G4", TEAM_A)  # 4th game of season 2023-24
    assert g4_a["std_net_rating"] == pytest.approx((15.0 + 15.0 + 30.0) / 3)

    g5_a = _row(out, "G5", TEAM_A)  # 1st game of season 2024-25 — resets despite 4 prior games
    assert np.isnan(g5_a["std_net_rating"])


# ── Elo ──────────────────────────────────────────────────────────────────────────────────────


def test_elo_increases_for_the_winner_across_games() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())

    elo_g1 = _row(out, "G1", TEAM_A)["elo"]
    elo_g2 = _row(out, "G2", TEAM_A)["elo"]
    elo_g3 = _row(out, "G3", TEAM_A)["elo"]

    assert elo_g1 == INITIAL_ELO
    assert elo_g1 < elo_g2 < elo_g3  # team A won G1 and G2, both feed forward


# ── Head-to-head ─────────────────────────────────────────────────────────────────────────────


def test_head_to_head_tracks_only_meetings_vs_that_specific_opponent() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())

    # Team A enters G5 (3rd meeting vs B) having won both prior meetings (G1, G2).
    g5_a = _row(out, "G5", TEAM_A)
    assert g5_a["h2h_win_pct"] == 1.0
    g5_b = _row(out, "G5", TEAM_B)
    assert g5_b["h2h_win_pct"] == 0.0

    # G4 is team A's *first* meeting with team C — no prior head-to-head history yet, despite A
    # having played plenty of games against team B by then.
    g4_a = _row(out, "G4", TEAM_A)
    assert np.isnan(g4_a["h2h_win_pct"])


# ── Differentials ────────────────────────────────────────────────────────────────────────────


def test_differentials_are_mirrored_between_home_and_away_rows() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams())
    g3_a = _row(out, "G3", TEAM_A)
    g3_b = _row(out, "G3", TEAM_B)

    assert g3_a["rest_advantage"] == pytest.approx(-g3_b["rest_advantage"])
    assert g3_a["rating_diff"] == pytest.approx(-g3_b["rating_diff"])
    assert g3_a["elo_diff"] == pytest.approx(-g3_b["elo_diff"])


# ── Serving (as_of) ──────────────────────────────────────────────────────────────────────────


def test_serving_builds_only_the_requested_slate_from_completed_history() -> None:
    out = build_team_game_features(_games(), _team_game_stats(), _teams(), as_of=date(2024, 10, 25))

    assert len(out) == 2
    assert set(out["game_id"]) == {"G7"}
    assert set(out["team_id"]) == {TEAM_A, TEAM_C}

    tonight_a = _row(out, "G7", TEAM_A)
    assert tonight_a["days_rest"] == 3  # last played G5 on 2024-10-22
    assert tonight_a["std_net_rating"] == pytest.approx(-2.0)  # only G5 so far this season


def test_serving_elo_matches_teams_final_post_history_rating() -> None:
    training = build_team_game_features(_games(), _team_game_stats(), _teams())
    serving = build_team_game_features(
        _games(), _team_game_stats(), _teams(), as_of=date(2024, 10, 25)
    )

    # Team A's serving-time elo should reflect everything through G5 (its most recent completed
    # game) — i.e. strictly more recent than its pre-game elo *at* G5.
    elo_at_g5 = _row(training, "G5", TEAM_A)["elo"]
    elo_tonight = _row(serving, "G7", TEAM_A)["elo"]
    assert elo_tonight != elo_at_g5
