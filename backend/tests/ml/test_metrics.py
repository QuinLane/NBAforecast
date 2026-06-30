"""Unit tests for the evaluation metrics module (modeling.md §5 + Prompt 8).

Every metric is checked against a hand-computed known value, per the build prompt's explicit
instruction ("unit-test against known values"), not just structural/shape assertions.
"""

import math

import pandas as pd
import pytest
from nbaforecast.training.metrics import (
    accuracy,
    auc,
    brier_score,
    calibration_curve,
    classification_metrics,
    interval_coverage,
    log_loss,
    mae,
    regression_metrics,
    rmse,
)

# ── log_loss ─────────────────────────────────────────────────────────────────────────────────────


def test_log_loss_perfect_predictions_near_zero() -> None:
    predictions = pd.Series([0.999999, 0.000001])
    actuals = pd.Series([1.0, 0.0])
    assert log_loss(predictions, actuals) == pytest.approx(0.0, abs=1e-4)


def test_log_loss_coin_flip_equals_log_2() -> None:
    predictions = pd.Series([0.5, 0.5])
    actuals = pd.Series([1.0, 0.0])
    assert log_loss(predictions, actuals) == pytest.approx(math.log(2))


def test_log_loss_confidently_wrong_is_heavily_penalized() -> None:
    confident_right = log_loss(pd.Series([0.99]), pd.Series([1.0]))
    confident_wrong = log_loss(pd.Series([0.01]), pd.Series([1.0]))
    assert confident_wrong > confident_right * 100


# ── brier_score ──────────────────────────────────────────────────────────────────────────────────


def test_brier_score_perfect_predictions_is_zero() -> None:
    assert brier_score(pd.Series([1.0, 0.0]), pd.Series([1.0, 0.0])) == 0.0


def test_brier_score_known_value() -> None:
    predictions = pd.Series([0.5, 0.5])
    actuals = pd.Series([1.0, 0.0])
    assert brier_score(predictions, actuals) == pytest.approx(0.25)


# ── auc ──────────────────────────────────────────────────────────────────────────────────────────


def test_auc_known_value() -> None:
    # Hand-computable via the rank-sum formula: ranks [1,3,2,4], positives at ranks {2,4}.
    predictions = pd.Series([0.1, 0.4, 0.35, 0.8])
    actuals = pd.Series([0.0, 0.0, 1.0, 1.0])
    assert auc(predictions, actuals) == pytest.approx(0.75)


def test_auc_perfect_separation_is_one() -> None:
    predictions = pd.Series([0.1, 0.2, 0.8, 0.9])
    actuals = pd.Series([0.0, 0.0, 1.0, 1.0])
    assert auc(predictions, actuals) == pytest.approx(1.0)


def test_auc_perfectly_inverted_is_zero() -> None:
    predictions = pd.Series([0.9, 0.8, 0.2, 0.1])
    actuals = pd.Series([0.0, 0.0, 1.0, 1.0])
    assert auc(predictions, actuals) == pytest.approx(0.0)


def test_auc_raises_with_only_one_class() -> None:
    with pytest.raises(ValueError, match="one class"):
        auc(pd.Series([0.1, 0.9]), pd.Series([1.0, 1.0]))


# ── accuracy ─────────────────────────────────────────────────────────────────────────────────────


def test_accuracy_known_value() -> None:
    predictions = pd.Series([0.6, 0.4, 0.9, 0.1])
    actuals = pd.Series([1.0, 1.0, 1.0, 0.0])
    assert accuracy(predictions, actuals) == pytest.approx(0.75)


def test_accuracy_respects_custom_threshold() -> None:
    predictions = pd.Series([0.3, 0.3])
    actuals = pd.Series([1.0, 0.0])
    assert accuracy(predictions, actuals, threshold=0.2) == pytest.approx(0.5)
    assert accuracy(predictions, actuals, threshold=0.5) == pytest.approx(0.5)


# ── calibration_curve ────────────────────────────────────────────────────────────────────────────


def test_calibration_curve_bins_match_expected_means() -> None:
    # n_bins=2 -> edges [0, 0.5, 1.0]: 0.05/0.15 fall in the low bin, 0.85/0.95 in the high bin.
    predictions = pd.Series([0.05, 0.15, 0.85, 0.95])
    actuals = pd.Series([0.0, 1.0, 1.0, 1.0])
    curve = calibration_curve(predictions, actuals, n_bins=2)

    low_bin = curve.iloc[0]
    assert low_bin["count"] == 2
    assert low_bin["mean_predicted"] == pytest.approx(0.10)
    assert low_bin["mean_actual"] == pytest.approx(0.5)

    high_bin = curve.iloc[-1]
    assert high_bin["count"] == 2
    assert high_bin["mean_predicted"] == pytest.approx(0.90)
    assert high_bin["mean_actual"] == pytest.approx(1.0)


def test_calibration_curve_drops_empty_bins() -> None:
    predictions = pd.Series([0.05, 0.95])
    actuals = pd.Series([0.0, 1.0])
    curve = calibration_curve(predictions, actuals, n_bins=10)
    assert len(curve) == 2  # not 10 — empty bins are dropped, not zero-filled


# ── mae / rmse ───────────────────────────────────────────────────────────────────────────────────


def test_mae_known_value() -> None:
    predictions = pd.Series([1.0, 2.0, 3.0])
    actuals = pd.Series([1.0, 2.0, 5.0])
    assert mae(predictions, actuals) == pytest.approx(2 / 3)


def test_rmse_known_value() -> None:
    predictions = pd.Series([1.0, 2.0, 3.0])
    actuals = pd.Series([1.0, 2.0, 5.0])
    assert rmse(predictions, actuals) == pytest.approx(math.sqrt(4 / 3))


def test_rmse_penalizes_large_errors_more_than_mae() -> None:
    predictions = pd.Series([0.0, 0.0])
    actuals = pd.Series([1.0, 9.0])  # one small, one large error
    assert rmse(predictions, actuals) > mae(predictions, actuals)


# ── interval_coverage ────────────────────────────────────────────────────────────────────────────


def test_interval_coverage_known_value() -> None:
    actuals = pd.Series([1.0, 2.0, 3.0, 10.0])
    lower = pd.Series([0.0, 0.0, 0.0, 0.0])
    upper = pd.Series([5.0, 5.0, 5.0, 5.0])
    assert interval_coverage(actuals, lower, upper) == pytest.approx(0.75)


def test_interval_coverage_boundary_inclusive() -> None:
    actuals = pd.Series([5.0])
    lower = pd.Series([0.0])
    upper = pd.Series([5.0])
    assert interval_coverage(actuals, lower, upper) == pytest.approx(1.0)


# ── bundles ──────────────────────────────────────────────────────────────────────────────────────


def test_classification_metrics_bundle_has_all_keys() -> None:
    predictions = pd.Series([0.1, 0.9])
    actuals = pd.Series([0.0, 1.0])
    metrics = classification_metrics(predictions, actuals)
    assert set(metrics) == {"log_loss", "brier_score", "accuracy", "auc"}


def test_classification_metrics_omits_auc_for_single_class_fold() -> None:
    predictions = pd.Series([0.1, 0.2])
    actuals = pd.Series([1.0, 1.0])
    metrics = classification_metrics(predictions, actuals)
    assert "auc" not in metrics
    assert "log_loss" in metrics  # other metrics still computed


def test_regression_metrics_bundle_has_all_keys() -> None:
    predictions = pd.Series([1.0, 2.0])
    actuals = pd.Series([1.5, 2.5])
    metrics = regression_metrics(predictions, actuals)
    assert set(metrics) == {"mae", "rmse"}
