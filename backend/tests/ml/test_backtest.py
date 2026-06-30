"""Unit tests for the walk-forward backtest harness (modeling.md Prompt 1).

Two correctness properties the build prompt calls for explicitly:
(a) no test-fold row's data predates training incorrectly — folds are always chronological.
(b) random k-fold is impossible to invoke by accident — there is no shuffle/random_state
    parameter anywhere in this module's public surface.
"""

import inspect
from typing import Any

import pandas as pd
import pytest
from nbaforecast.explain.schema import Explanation, ExplanationUnits
from nbaforecast.models.base import ModelHead, TrainResult
from nbaforecast.training.backtest import Fold, make_folds, run_backtest

# ── Fold construction is always chronological ──────────────────────────────────────────────────


def test_folds_are_chronological() -> None:
    folds = make_folds([2020, 2021, 2022, 2023], lookback_seasons=15)
    for fold in folds:
        assert all(season < fold.test_season for season in fold.train_seasons)


def test_no_fold_for_the_first_season() -> None:
    # The earliest season has no prior data to train on — it must never appear as a test_season.
    folds = make_folds([2020, 2021, 2022], lookback_seasons=15)
    assert 2020 not in {fold.test_season for fold in folds}
    assert {fold.test_season for fold in folds} == {2021, 2022}


def test_lookback_seasons_caps_the_training_window() -> None:
    folds = make_folds([2018, 2019, 2020, 2021, 2022], lookback_seasons=2)
    last_fold = next(f for f in folds if f.test_season == 2022)
    assert last_fold.train_seasons == (2020, 2021)  # only the most recent 2, not all of history


def test_lookback_window_expands_until_full() -> None:
    # Early on (fewer prior seasons than lookback_seasons), the window uses everything available
    # rather than padding or erroring.
    folds = make_folds([2020, 2021, 2022], lookback_seasons=15)
    fold_2021 = next(f for f in folds if f.test_season == 2021)
    assert fold_2021.train_seasons == (2020,)


def test_duplicate_season_values_are_deduplicated() -> None:
    # features has one row per game, so season_start_year repeats many times in the raw column.
    folds = make_folds([2020, 2020, 2020, 2021, 2021], lookback_seasons=15)
    assert folds == [Fold(train_seasons=(2020,), test_season=2021)]


# ── No accidental random k-fold ─────────────────────────────────────────────────────────────────


def test_no_shuffle_or_random_state_parameter_exists() -> None:
    for fn in (make_folds, run_backtest):
        params = inspect.signature(fn).parameters
        assert "shuffle" not in params
        assert "random_state" not in params
        assert "k" not in params  # no generic k-fold count either


# ── run_backtest end-to-end ──────────────────────────────────────────────────────────────────────


class _ConstantHead(ModelHead[float]):
    """Predicts a fixed value regardless of input — isolates the harness's wiring from any real
    model logic, so these tests are about fold/data-flow correctness, not modeling quality.
    """

    @property
    def name(self) -> str:
        return "constant"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(model={"value": 1.0}, metrics={}, feature_version="v1")

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        return pd.Series([model["value"]] * len(features), index=features.index)

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        return Explanation(
            baseline=model["value"],
            prediction=model["value"],
            contributions=[],
            units=ExplanationUnits.POINTS,
            notes="",
        )


def _toy_features_and_labels() -> tuple[pd.DataFrame, pd.Series]:
    seasons = [2020] * 4 + [2021] * 4 + [2022] * 4
    features = pd.DataFrame({"season_start_year": seasons, "x": range(len(seasons))})
    labels = pd.Series([float(s) for s in seasons])
    return features, labels


def _mean_absolute_error(predictions: pd.Series, actuals: pd.Series) -> dict[str, float]:
    return {"mae": float((predictions - actuals).abs().mean())}


def test_run_backtest_covers_every_row_outside_the_first_season() -> None:
    features, labels = _toy_features_and_labels()
    result = run_backtest(_ConstantHead(), features, labels, _mean_absolute_error)

    # 2020 (the first season) is never a test fold, so its 4 rows are excluded; 2021 + 2022's
    # 8 rows are all covered exactly once.
    assert len(result.predictions) == 8
    assert set(result.predictions.index) == set(features.index[4:])
    assert len(result.folds) == 2
    assert len(result.fold_metrics) == 2


def test_run_backtest_predictions_only_use_that_folds_fitted_model() -> None:
    features, labels = _toy_features_and_labels()
    result = run_backtest(_ConstantHead(), features, labels, _mean_absolute_error)
    assert (result.predictions == 1.0).all()


def test_run_backtest_metrics_match_known_mae() -> None:
    features, labels = _toy_features_and_labels()
    result = run_backtest(_ConstantHead(), features, labels, _mean_absolute_error)

    # Fold 1: train on 2020, test on 2021. Constant prediction = 1.0, actual = 2021.0.
    assert result.fold_metrics[0]["mae"] == pytest.approx(2020.0)
