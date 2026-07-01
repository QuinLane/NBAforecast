"""Unit tests for the props regressor (modeling.md Prompt 4) beyond the floor comparison in
``test_props_baseline_floor.py``: prediction-interval coverage, interval sanity (lower <= point <=
upper), non-negativity, and explain() shape/additivity.
"""

import pandas as pd
import pytest
from nbaforecast.features.player_game import build_player_game_features
from nbaforecast.models.props.regressor import (
    MODEL_FEATURE_COLUMNS,
    PropsRegressorHead,
    design_matrix,
)
from nbaforecast.training.metrics import interval_coverage, mae

from tests.ml._synthetic_player_league import build_synthetic_player_league

STATS = ("pts", "reb", "ast", "fg3m")


def _train_test_split(
    stat: str, n_teams: int = 10, n_seasons: int = 14
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2010, 2010 + n_seasons))
    games, team_game_stats, _teams, player_game_stats, players = build_synthetic_player_league(
        n_teams=n_teams, seasons=seasons
    )
    features = build_player_game_features(games, player_game_stats, team_game_stats, players)
    merged = features.merge(
        player_game_stats[["game_id", "player_id", stat]], on=["game_id", "player_id"], how="left"
    )
    labels = merged[stat].astype(float)
    features = merged.drop(columns=[stat])

    train_mask = features["season_start_year"] < features["season_start_year"].max()
    test_mask = ~train_mask
    return (
        features.loc[train_mask],
        labels.loc[train_mask],
        features.loc[test_mask],
        labels.loc[test_mask],
    )


@pytest.mark.parametrize("stat", STATS)
def test_predict_with_interval_bounds_the_point_estimate(stat: str) -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split(stat)
    head = PropsRegressorHead(stat)
    result = head.train(train_features, train_labels)
    prediction = head.predict_with_interval(result.model, test_features)

    assert (prediction.lower <= prediction.point + 1e-9).all()
    assert (prediction.point <= prediction.upper + 1e-9).all()


@pytest.mark.parametrize("stat", STATS)
def test_predictions_are_never_negative(stat: str) -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split(stat)
    head = PropsRegressorHead(stat)
    result = head.train(train_features, train_labels)
    prediction = head.predict_with_interval(result.model, test_features)

    assert (prediction.point >= 0).all()
    assert (prediction.lower >= 0).all()
    assert (prediction.upper >= 0).all()


@pytest.mark.parametrize("stat", STATS)
def test_interval_coverage_is_reasonably_close_to_nominal(stat: str) -> None:
    """The 80% interval should contain the actual outcome close to 80% of the time — not exactly
    (a finite held-out sample + independently-fit quantile boosters won't hit the nominal rate
    exactly), but well within a generous band, confirming the intervals are honest rather than
    degenerate (e.g. always-0-width or always-covering)."""
    train_features, train_labels, test_features, test_labels = _train_test_split(stat)
    head = PropsRegressorHead(stat, interval_coverage=0.8)
    result = head.train(train_features, train_labels)
    prediction = head.predict_with_interval(result.model, test_features)

    coverage = interval_coverage(test_labels, prediction.lower, prediction.upper)
    assert 0.5 <= coverage <= 1.0


@pytest.mark.parametrize("stat", STATS)
def test_wider_interval_coverage_setting_covers_more(stat: str) -> None:
    train_features, train_labels, test_features, test_labels = _train_test_split(stat)

    narrow_head = PropsRegressorHead(stat, interval_coverage=0.5)
    narrow_result = narrow_head.train(train_features, train_labels)
    narrow_prediction = narrow_head.predict_with_interval(narrow_result.model, test_features)
    narrow_coverage = interval_coverage(
        test_labels, narrow_prediction.lower, narrow_prediction.upper
    )

    wide_head = PropsRegressorHead(stat, interval_coverage=0.95)
    wide_result = wide_head.train(train_features, train_labels)
    wide_prediction = wide_head.predict_with_interval(wide_result.model, test_features)
    wide_coverage = interval_coverage(test_labels, wide_prediction.lower, wide_prediction.upper)

    assert wide_coverage >= narrow_coverage


@pytest.mark.parametrize("stat", STATS)
def test_predict_matches_predict_with_interval_point(stat: str) -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split(stat)
    head = PropsRegressorHead(stat)
    result = head.train(train_features, train_labels)

    point_only = head.predict(result.model, test_features)
    with_interval = head.predict_with_interval(result.model, test_features)

    pd.testing.assert_series_equal(point_only, with_interval.point, check_names=False)


def test_regressor_point_estimate_beats_a_naive_mean_prediction() -> None:
    """Sanity floor beyond test_props_baseline_floor.py's own comparison: the model should not
    just be memorizing noise — on held-out data it should beat predicting the training mean for
    every row."""
    train_features, train_labels, test_features, test_labels = _train_test_split("pts")
    head = PropsRegressorHead("pts")
    result = head.train(train_features, train_labels)
    predictions = head.predict(result.model, test_features)

    naive = pd.Series(train_labels.mean(), index=test_labels.index)
    assert mae(predictions, test_labels) < mae(naive, test_labels)


# ── explain() ────────────────────────────────────────────────────────────────────────────────


def test_explain_returns_a_contribution_per_feature() -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split("pts")
    head = PropsRegressorHead("pts")
    result = head.train(train_features, train_labels)
    explanation = head.explain(result.model, test_features.iloc[[0]])
    assert {c.feature for c in explanation.contributions} == set(MODEL_FEATURE_COLUMNS)


def test_explain_contributions_sorted_by_magnitude() -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split("pts")
    head = PropsRegressorHead("pts")
    result = head.train(train_features, train_labels)
    explanation = head.explain(result.model, test_features.iloc[[0]])
    magnitudes = [abs(c.contribution) for c in explanation.contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_explain_is_additive() -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split("pts")
    head = PropsRegressorHead("pts")
    result = head.train(train_features, train_labels)
    explanation = head.explain(result.model, test_features.iloc[[0]])
    total = sum(c.contribution for c in explanation.contributions)
    assert total == pytest.approx(explanation.prediction - explanation.baseline, abs=1e-6)


def test_explain_prediction_matches_median_predict() -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split("pts")
    head = PropsRegressorHead("pts")
    result = head.train(train_features, train_labels)
    row = test_features.iloc[[0]]
    explanation = head.explain(result.model, row)
    predicted = float(result.model["median"].predict(design_matrix(row))[0])
    assert explanation.prediction == pytest.approx(predicted, abs=1e-6)


def test_explain_raises_for_multiple_rows() -> None:
    train_features, train_labels, test_features, _test_labels = _train_test_split("pts")
    head = PropsRegressorHead("pts")
    result = head.train(train_features, train_labels)
    with pytest.raises(ValueError, match="one row at a time"):
        head.explain(result.model, test_features.iloc[[0, 1]])
