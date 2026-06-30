"""No-leakage and train/serve-parity regression tests (feature-engineering.md Prompt 6).

Builds a larger synthetic multi-team, multi-season league (not the tiny hand-derived fixture in
test_team_game.py) and checks two structural properties that must hold for *every* feature, not
just the handful a value-level unit test happens to assert on:

(a) **No-leakage** — recomputing a sampled game's features from a dataset truncated to end at
    that game must reproduce the materialized (full-history) row exactly. If it didn't, some
    feature would have to be reading a row dated after the game it's predicting.
(b) **Train/serve parity** — calling ``build_team_game_features`` with ``as_of`` set to a sampled
    game's date, against a dataset that only knows about *prior* results, must reproduce that
    game's materialized training row exactly. Training and serving are one code path by
    construction (team_game.py's module docstring); this is the proof.
"""

import pandas as pd
import pytest
from nbaforecast.features.team_game import FEATURE_COLUMNS, build_team_game_features

from tests.ml._synthetic_league import build_synthetic_league


def _sample_game_ids(games: pd.DataFrame) -> list[str]:
    """A handful of games spread across the league: early (mostly-NaN features), mid-season,
    a season-boundary game, and the very last game (no future data exists at all)."""
    ordered = games.sort_values("game_date")["game_id"].tolist()
    n = len(ordered)
    return [ordered[1], ordered[n // 4], ordered[n // 2], ordered[-1]]


@pytest.fixture(scope="module")
def league() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return build_synthetic_league()


@pytest.fixture(scope="module")
def materialized(league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> pd.DataFrame:
    games, team_game_stats, teams = league
    return build_team_game_features(games, team_game_stats, teams)


def _assert_team_row_matches(
    candidate: pd.DataFrame, materialized: pd.DataFrame, game_id: str, team_id: int
) -> None:
    candidate_row = candidate.loc[
        (candidate["game_id"] == game_id) & (candidate["team_id"] == team_id)
    ].iloc[0]
    materialized_row = materialized.loc[
        (materialized["game_id"] == game_id) & (materialized["team_id"] == team_id)
    ].iloc[0]
    pd.testing.assert_series_equal(
        candidate_row[FEATURE_COLUMNS],
        materialized_row[FEATURE_COLUMNS],
        check_dtype=False,
        check_names=False,
    )


@pytest.mark.parametrize("game_index", [0, 1, 2, 3])
def test_no_leakage_recompute_from_truncated_history(
    league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    materialized: pd.DataFrame,
    game_index: int,
) -> None:
    games, team_game_stats, teams = league
    sample_game_id = _sample_game_ids(games)[game_index]
    cutoff = games.loc[games["game_id"] == sample_game_id, "game_date"].iloc[0]

    # Drop every game dated after the sample — if any feature secretly depended on future data,
    # this recompute would diverge from the materialized (full-history) row.
    truncated_games = games.loc[games["game_date"] <= cutoff]
    truncated_stats = team_game_stats.loc[
        team_game_stats["game_id"].isin(truncated_games["game_id"])
    ]
    recomputed = build_team_game_features(truncated_games, truncated_stats, teams)

    sample_game = games.loc[games["game_id"] == sample_game_id].iloc[0]
    for team_id in (sample_game["home_team_id"], sample_game["away_team_id"]):
        _assert_team_row_matches(recomputed, materialized, sample_game_id, team_id)


@pytest.mark.parametrize("game_index", [0, 1, 2, 3])
def test_train_serve_parity_at_tip_off(
    league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    materialized: pd.DataFrame,
    game_index: int,
) -> None:
    games, team_game_stats, teams = league
    sample_game_id = _sample_game_ids(games)[game_index]
    tip_off = games.loc[games["game_id"] == sample_game_id, "game_date"].iloc[0]

    # Simulate "tonight, before the game": prior completed games + this one game re-marked
    # scheduled, with its own result withheld entirely.
    prior_games = games.loc[games["game_date"] < tip_off]
    sample_game = games.loc[games["game_id"] == sample_game_id].copy()
    sample_game["status"] = "scheduled"
    serving_games = pd.concat([prior_games, sample_game], ignore_index=True)
    prior_stats = team_game_stats.loc[team_game_stats["game_id"].isin(prior_games["game_id"])]

    serving = build_team_game_features(serving_games, prior_stats, teams, as_of=tip_off.date())

    sample_game_row = games.loc[games["game_id"] == sample_game_id].iloc[0]
    for team_id in (sample_game_row["home_team_id"], sample_game_row["away_team_id"]):
        _assert_team_row_matches(serving, materialized, sample_game_id, team_id)
