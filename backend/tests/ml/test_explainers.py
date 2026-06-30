"""Unit tests for explain/explainers.py (explainability.md Prompt 2), exercising paths the
indirect coverage in test_win_prob.py doesn't reach: the log-odds (unconverted) output mode,
shap's list-of-arrays output shape, and the single-row guard on both explainers.
"""

from typing import Any

import numpy as np
import pandas as pd
import pytest
import shap
from nbaforecast.explain.explainers import explain_lightgbm_classifier, explain_linear_classifier
from nbaforecast.explain.schema import ExplanationUnits
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.win_prob import (
    LightGBMWinProbHead,
    LogisticWinProbHead,
    design_matrix,
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


@pytest.fixture(scope="module")
def lightgbm_fit() -> tuple[dict[str, Any], pd.DataFrame]:
    features, labels = _features_and_labels()
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    return result.model, features


@pytest.fixture(scope="module")
def logistic_fit() -> tuple[Any, pd.DataFrame]:
    features, labels = _features_and_labels()
    head = LogisticWinProbHead()
    result = head.train(features, labels)
    return result.model, features


def test_lightgbm_explainer_rejects_multi_row_input(
    lightgbm_fit: tuple[dict[str, Any], pd.DataFrame],
) -> None:
    model, features = lightgbm_fit
    with pytest.raises(ValueError, match="one row"):
        explain_lightgbm_classifier(model, features)


def test_linear_explainer_rejects_multi_row_input(logistic_fit: tuple[Any, pd.DataFrame]) -> None:
    model, features = logistic_fit
    with pytest.raises(ValueError, match="one row"):
        explain_linear_classifier(model, features)


def test_lightgbm_explainer_log_odds_mode_is_additive(
    lightgbm_fit: tuple[dict[str, Any], pd.DataFrame],
) -> None:
    model, features = lightgbm_fit
    explanation = explain_lightgbm_classifier(
        model, features.iloc[[0]], units=ExplanationUnits.LOG_ODDS
    )

    assert explanation.units == ExplanationUnits.LOG_ODDS
    total = sum(c.contribution for c in explanation.contributions)
    assert total == pytest.approx(explanation.prediction - explanation.baseline, abs=1e-9)


def test_lightgbm_explainer_log_odds_baseline_matches_shap_expected_value(
    lightgbm_fit: tuple[dict[str, Any], pd.DataFrame],
) -> None:
    model, features = lightgbm_fit
    explanation = explain_lightgbm_classifier(
        model, features.iloc[[0]], units=ExplanationUnits.LOG_ODDS
    )

    explainer = shap.TreeExplainer(model["booster"])
    expected_baseline = float(np.asarray(explainer.expected_value).reshape(-1)[-1])
    assert explanation.baseline == pytest.approx(expected_baseline)


def test_lightgbm_explainer_probability_points_baseline_is_a_probability(
    lightgbm_fit: tuple[dict[str, Any], pd.DataFrame],
) -> None:
    model, features = lightgbm_fit
    explanation = explain_lightgbm_classifier(model, features.iloc[[0]])
    assert 0.0 <= explanation.baseline <= 1.0
    assert 0.0 <= explanation.prediction <= 1.0


def test_linear_explainer_log_odds_baseline_matches_intercept(
    logistic_fit: tuple[Any, pd.DataFrame],
) -> None:
    model, features = logistic_fit
    explanation = explain_linear_classifier(model, features.iloc[[0]])
    classifier = model.named_steps["logisticregression"]
    assert explanation.baseline == pytest.approx(float(classifier.intercept_[0]))


def test_linear_explainer_prediction_matches_raw_decision_function(
    logistic_fit: tuple[Any, pd.DataFrame],
) -> None:
    model, features = logistic_fit
    row = features.iloc[[0]]
    explanation = explain_linear_classifier(model, row)

    decision = model.decision_function(design_matrix(row))[0]
    assert explanation.prediction == pytest.approx(decision)
