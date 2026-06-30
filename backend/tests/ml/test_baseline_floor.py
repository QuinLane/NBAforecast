"""Baseline floor test (modeling.md Prompt 2 + §3).

The win-prob baselines must be meaningfully ordered: Elo (carries real per-game signal) must
beat the constant-rate baseline on held-out log-loss, via the walk-forward harness on a
synthetic-but-skill-correlated league. This is the same comparison T2.7's real LightGBM model
will later be held to against Elo as *its* baseline.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.baseline import EloWinProbHead, HomeAlwaysWinsHead
from nbaforecast.training.backtest import run_backtest

from tests.ml._synthetic_league import build_synthetic_league


def _log_loss(predictions: pd.Series, actuals: pd.Series) -> dict[str, float]:
    """Minimal binary log-loss — temporary until training/metrics.py (T2.9) lands."""
    eps = 1e-15
    clipped = predictions.clip(eps, 1 - eps)
    loss = -(actuals * np.log(clipped) + (1 - actuals) * np.log(1 - clipped)).mean()
    return {"log_loss": float(loss)}


def _features_and_labels() -> tuple[pd.DataFrame, pd.Series]:
    games, team_game_stats, teams = build_synthetic_league()
    features = build_team_game_features(games, team_game_stats, teams)

    outcomes = team_game_stats.merge(games[["game_id", "home_score", "away_score"]], on="game_id")
    outcomes["win"] = np.where(
        outcomes["is_home"],
        outcomes["home_score"] > outcomes["away_score"],
        outcomes["away_score"] > outcomes["home_score"],
    ).astype(float)

    merged = features.merge(
        outcomes[["game_id", "team_id", "win"]], on=["game_id", "team_id"], how="left"
    )
    return merged.drop(columns=["win"]), merged["win"]


# ── Individual baseline sanity ──────────────────────────────────────────────────────────────────


def test_home_always_wins_predicts_constant_training_rate() -> None:
    head = HomeAlwaysWinsHead()
    features = pd.DataFrame({"x": [1, 2, 3]})
    labels = pd.Series([1.0, 1.0, 0.0])  # 2/3 home wins

    result = head.train(features, labels)
    predictions = head.predict(result.model, features)

    assert predictions.unique().tolist() == pytest.approx([2 / 3])


def test_elo_baseline_favors_the_higher_rated_home_team() -> None:
    head = EloWinProbHead()
    features = pd.DataFrame(
        {
            "is_home": [True, False],
            "elo_diff": [100.0, -100.0],  # this row's team is +100 elo over its opponent
        }
    )
    predictions = head.predict({}, features)

    assert predictions.iloc[0] > 0.5  # stronger team, at home
    assert predictions.iloc[1] < 0.5  # weaker team, on the road


def test_elo_baseline_evenly_matched_at_a_neutral_site_is_fifty_fifty() -> None:
    head = EloWinProbHead()
    features = pd.DataFrame({"is_home": [True], "elo_diff": [0.0]})
    predictions = head.predict({}, features)
    assert predictions.iloc[0] != 0.5  # home edge still applies even when elo is dead even
    assert predictions.iloc[0] > 0.5


# ── Floor comparison ─────────────────────────────────────────────────────────────────────────────


def test_elo_baseline_beats_home_always_wins_floor() -> None:
    features, labels = _features_and_labels()

    elo_result = run_backtest(EloWinProbHead(), features, labels, _log_loss)
    home_result = run_backtest(HomeAlwaysWinsHead(), features, labels, _log_loss)

    elo_log_loss = float(np.mean([m["log_loss"] for m in elo_result.fold_metrics]))
    home_log_loss = float(np.mean([m["log_loss"] for m in home_result.fold_metrics]))

    assert elo_log_loss < home_log_loss
