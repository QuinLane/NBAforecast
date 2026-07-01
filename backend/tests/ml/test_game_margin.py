"""Unit + baseline-floor tests for the game point-margin models (modeling.md Prompt 3b).

Mirrors ``test_win_prob.py``/``test_baseline_floor.py``'s fixtures and structure: a synthetic
league with genuine, checkable home-court + skill signal in ``margin`` (self-relative,
``team_score - opponent_score``), evaluated through the walk-forward backtest harness.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.baseline import (
    ConstantHomeCourtMarginHead,
    RatingDiffMarginHead,
)
from nbaforecast.models.game_prediction.margin import LightGBMMarginHead
from nbaforecast.models.game_prediction.win_prob import MODEL_FEATURE_COLUMNS
from nbaforecast.training.backtest import run_backtest
from nbaforecast.training.metrics import regression_metrics

from tests.ml._synthetic_league import build_synthetic_league


def _features_and_labels(n_teams: int = 8, n_seasons: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2020, 2020 + n_seasons))
    games, team_game_stats, teams = build_synthetic_league(n_teams=n_teams, seasons=seasons)
    features = build_team_game_features(games, team_game_stats, teams)

    outcomes = team_game_stats.merge(games[["game_id", "home_score", "away_score"]], on="game_id")
    outcomes["margin"] = np.where(
        outcomes["is_home"],
        outcomes["home_score"] - outcomes["away_score"],
        outcomes["away_score"] - outcomes["home_score"],
    ).astype(float)
    merged = features.merge(
        outcomes[["game_id", "team_id", "margin"]], on=["game_id", "team_id"], how="left"
    )
    return merged.drop(columns=["margin"]), merged["margin"]


# ── Baseline sanity ─────────────────────────────────────────────────────────────────────────────


def test_constant_home_court_margin_is_symmetric() -> None:
    head = ConstantHomeCourtMarginHead()
    features = pd.DataFrame({"is_home": [True, False]})
    predictions = head.predict({}, features)
    assert predictions.iloc[0] == pytest.approx(2.5)
    assert predictions.iloc[1] == pytest.approx(-2.5)


def test_rating_diff_margin_head_favors_the_better_rated_team() -> None:
    features, labels = _features_and_labels()
    head = RatingDiffMarginHead()
    result = head.train(features, labels)
    higher = pd.DataFrame({"rating_diff": [10.0], "is_home": [True]})
    lower = pd.DataFrame({"rating_diff": [-10.0], "is_home": [True]})
    assert head.predict(result.model, higher).iloc[0] > head.predict(result.model, lower).iloc[0]


# ── Floor comparison ─────────────────────────────────────────────────────────────────────────────


def test_rating_diff_beats_constant_margin_floor() -> None:
    features, labels = _features_and_labels()

    rating_result = run_backtest(RatingDiffMarginHead(), features, labels, regression_metrics)
    constant_result = run_backtest(
        ConstantHomeCourtMarginHead(), features, labels, regression_metrics
    )

    rating_mae = float(np.mean([m["mae"] for m in rating_result.fold_metrics]))
    constant_mae = float(np.mean([m["mae"] for m in constant_result.fold_metrics]))

    assert rating_mae < constant_mae


def test_lightgbm_margin_head_beats_both_baselines() -> None:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2012, 2024))
    features, labels = _features_and_labels(n_teams=14, n_seasons=len(seasons))

    constant_result = run_backtest(
        ConstantHomeCourtMarginHead(), features, labels, regression_metrics
    )
    rating_result = run_backtest(RatingDiffMarginHead(), features, labels, regression_metrics)
    lgbm_result = run_backtest(LightGBMMarginHead(), features, labels, regression_metrics)

    constant_mae = float(np.mean([m["mae"] for m in constant_result.fold_metrics]))
    rating_mae = float(np.mean([m["mae"] for m in rating_result.fold_metrics]))
    lgbm_mae = float(np.mean([m["mae"] for m in lgbm_result.fold_metrics]))

    assert lgbm_mae < constant_mae
    assert lgbm_mae < rating_mae


# ── LightGBMMarginHead correctness ──────────────────────────────────────────────────────────────


def test_lightgbm_margin_explain_returns_a_contribution_per_feature() -> None:
    features, labels = _features_and_labels()
    head = LightGBMMarginHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    assert {c.feature for c in explanation.contributions} == set(MODEL_FEATURE_COLUMNS)


def test_lightgbm_margin_explain_contributions_sorted_by_magnitude() -> None:
    features, labels = _features_and_labels()
    head = LightGBMMarginHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    magnitudes = [abs(c.contribution) for c in explanation.contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_lightgbm_margin_explain_is_additive() -> None:
    features, labels = _features_and_labels()
    head = LightGBMMarginHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    total = sum(c.contribution for c in explanation.contributions)
    assert total == pytest.approx(explanation.prediction - explanation.baseline, abs=1e-6)


def test_lightgbm_margin_explain_prediction_matches_predict() -> None:
    features, labels = _features_and_labels()
    head = LightGBMMarginHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    predicted = head.predict(result.model, features.iloc[[0]]).iloc[0]
    assert explanation.prediction == pytest.approx(predicted, abs=1e-6)


def test_lightgbm_margin_explain_rejects_multi_row_input() -> None:
    features, labels = _features_and_labels()
    head = LightGBMMarginHead()
    result = head.train(features, labels)
    with pytest.raises(ValueError, match="one row"):
        head.explain(result.model, features)
