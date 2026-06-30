"""SHAP additivity test (explainability.md Prompt 6).

For every game-win head, ``sum(c.contribution for c in explanation.contributions)`` must equal
``explanation.prediction - explanation.baseline`` within floating-point tolerance — the property
that makes a waterfall chart honest (the bars actually sum to the gap between baseline and
final prediction). Checked across several sample rows per head, not just one: additivity is a
property of the explainer's math, so if it ever fails it should fail for *every* row of a given
head, but checking several rows costs little and catches a row-dependent bug (e.g. a NaN-related
edge case) a single-row check could miss.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.explain.explainers import explain_lightgbm_classifier
from nbaforecast.explain.schema import Explanation, ExplanationUnits
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.baseline import EloWinProbHead, HomeAlwaysWinsHead
from nbaforecast.models.game_prediction.win_prob import LightGBMWinProbHead, LogisticWinProbHead

from tests.ml._synthetic_league import build_synthetic_league

SAMPLE_ROW_INDICES = (0, 1, 10, 100, 300, 447)


def _assert_additive(explanation: Explanation, *, abs_tol: float = 1e-9) -> None:
    total = sum(c.contribution for c in explanation.contributions)
    assert total == pytest.approx(explanation.prediction - explanation.baseline, abs=abs_tol)


@pytest.fixture(scope="module")
def features_and_labels() -> tuple[pd.DataFrame, pd.Series]:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2020, 2024))
    games, team_game_stats, teams = build_synthetic_league(n_teams=8, seasons=seasons)
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


@pytest.mark.parametrize("row_index", SAMPLE_ROW_INDICES)
def test_home_always_wins_explanation_is_additive(
    features_and_labels: tuple[pd.DataFrame, pd.Series], row_index: int
) -> None:
    features, labels = features_and_labels
    head = HomeAlwaysWinsHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[row_index]])
    _assert_additive(explanation)


@pytest.mark.parametrize("row_index", SAMPLE_ROW_INDICES)
def test_elo_explanation_is_additive(
    features_and_labels: tuple[pd.DataFrame, pd.Series], row_index: int
) -> None:
    features, labels = features_and_labels
    head = EloWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[row_index]])
    _assert_additive(explanation)


@pytest.mark.parametrize("row_index", SAMPLE_ROW_INDICES)
def test_logistic_explanation_is_additive(
    features_and_labels: tuple[pd.DataFrame, pd.Series], row_index: int
) -> None:
    features, labels = features_and_labels
    head = LogisticWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[row_index]])
    _assert_additive(explanation)


@pytest.mark.parametrize("row_index", SAMPLE_ROW_INDICES)
def test_lightgbm_explanation_is_additive_in_probability_points(
    features_and_labels: tuple[pd.DataFrame, pd.Series], row_index: int
) -> None:
    features, labels = features_and_labels
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[row_index]])
    assert explanation.units == ExplanationUnits.PROBABILITY_POINTS
    _assert_additive(explanation)


@pytest.mark.parametrize("row_index", SAMPLE_ROW_INDICES)
def test_lightgbm_explanation_is_additive_in_log_odds(
    features_and_labels: tuple[pd.DataFrame, pd.Series], row_index: int
) -> None:
    features, labels = features_and_labels
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    explanation = explain_lightgbm_classifier(
        result.model, features.iloc[[row_index]], units=ExplanationUnits.LOG_ODDS
    )
    assert explanation.units == ExplanationUnits.LOG_ODDS
    _assert_additive(explanation)
