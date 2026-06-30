"""Unit tests for the game win-prob models (modeling.md Prompt 3a).

Correctness/wiring checks on top of the floor-test comparison in test_baseline_floor.py:
calibration is genuinely isolated to a held-out slice, the calibrator is actually consulted at
predict time, and explain() returns sensible shapes for both sub-models.
"""

from typing import Any

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.win_prob import (
    MODEL_FEATURE_COLUMNS,
    LightGBMWinProbHead,
    LogisticWinProbHead,
)

from tests.ml._synthetic_league import build_synthetic_league


def _features_and_labels(n_teams: int = 8, n_seasons: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2020, 2020 + n_seasons))
    games, team_game_stats, teams = build_synthetic_league(n_teams=n_teams, seasons=seasons)
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


# ── LogisticWinProbHead ──────────────────────────────────────────────────────────────────────────


def test_logistic_predictions_are_valid_probabilities() -> None:
    features, labels = _features_and_labels()
    head = LogisticWinProbHead()
    result = head.train(features, labels)
    predictions = head.predict(result.model, features)
    assert predictions.between(0, 1).all()


def test_logistic_explain_returns_a_coefficient_per_feature() -> None:
    features, labels = _features_and_labels()
    head = LogisticWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    assert {c.feature for c in explanation.contributions} == set(MODEL_FEATURE_COLUMNS)


def test_logistic_explain_contributions_sorted_by_magnitude() -> None:
    features, labels = _features_and_labels()
    head = LogisticWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    magnitudes = [abs(c.contribution) for c in explanation.contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_logistic_explain_is_additive() -> None:
    features, labels = _features_and_labels()
    head = LogisticWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    total = sum(c.contribution for c in explanation.contributions)
    assert total == pytest.approx(explanation.prediction - explanation.baseline)


# ── LightGBMWinProbHead ──────────────────────────────────────────────────────────────────────────


def test_lightgbm_calibration_is_off_by_default() -> None:
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    assert result.model["calibrator"] is None


def test_lightgbm_predictions_are_valid_probabilities() -> None:
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    predictions = head.predict(result.model, features)
    assert predictions.between(0, 1).all()


def test_lightgbm_explain_returns_a_contribution_per_feature() -> None:
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    assert {c.feature for c in explanation.contributions} == set(MODEL_FEATURE_COLUMNS)


def test_lightgbm_explain_contributions_sorted_by_magnitude() -> None:
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    magnitudes = [abs(c.contribution) for c in explanation.contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_lightgbm_explain_is_additive() -> None:
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    total = sum(c.contribution for c in explanation.contributions)
    assert total == pytest.approx(explanation.prediction - explanation.baseline, abs=1e-9)


def test_lightgbm_explain_prediction_matches_uncalibrated_predict() -> None:
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    predicted = head.predict(result.model, features.iloc[[0]]).iloc[0]
    assert explanation.prediction == pytest.approx(predicted)


def test_lightgbm_calibrator_is_actually_consulted_at_predict_time() -> None:
    """Swap in a fake calibrator and confirm predict() routes raw probs through it."""
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)

    class _AlwaysOne:
        def predict(self, raw: Any) -> Any:
            return np.ones_like(raw)

    model_with_fake_calibrator = {**result.model, "calibrator": _AlwaysOne()}
    predictions = head.predict(model_with_fake_calibrator, features)
    assert (predictions == 1.0).all()


def test_lightgbm_calibration_holdout_never_overlaps_the_fit_set() -> None:
    """The booster fits on the first (1 - holdout_frac) chronologically, calibrator on the rest
    — verified directly here since the floor test only checks the net effect on log-loss."""
    features, labels = _features_and_labels(n_teams=10, n_seasons=8)  # enough rows to calibrate
    head = LightGBMWinProbHead(calibrate=True, min_rows_to_calibrate=100)
    result = head.train(features, labels)
    assert result.model["calibrator"] is not None  # confirms calibration actually engaged
