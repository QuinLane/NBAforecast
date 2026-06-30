"""Walk-forward backtesting harness — modeling.md Prompt 1.

The single most important component for correctness: get this wrong and every metric is a lie.
**Walk-forward (expanding/rolling window) validation only** — train on seasons ≤ T, predict the
next season, roll forward in time. There is deliberately no shuffle/random_state parameter
anywhere in this module: random k-fold (shuffling future and past together) is leakage, and the
absence of that parameter is what makes it impossible to invoke by accident, not a runtime check.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from nbaforecast.models.base import ModelHead

MetricFn = Callable[[pd.Series, pd.Series], dict[str, float]]


@dataclass(slots=True, frozen=True)
class Fold:
    """One walk-forward fold: the season(s) trained on vs. the season predicted next.

    ``test_season`` is always strictly after every season in ``train_seasons`` — the structural
    invariant that makes leakage across a fold boundary impossible (see
    ``test_folds_are_chronological`` in ``backend/tests/ml/test_backtest.py``).
    """

    train_seasons: tuple[int, ...]
    test_season: int


@dataclass(slots=True, frozen=True)
class BacktestResult:
    """Out-of-sample predictions + per-fold metrics from a full walk-forward run."""

    folds: tuple[Fold, ...]
    predictions: pd.Series
    fold_metrics: tuple[dict[str, float], ...]


def make_folds(season_start_years: list[int], *, lookback_seasons: int) -> list[Fold]:
    """Build the walk-forward fold schedule from the distinct seasons present in the data.

    Each season (after the first, which has no prior data to train on) is predicted using only
    the ``lookback_seasons`` seasons immediately before it — an expanding window until enough
    history accumulates, then a fixed rolling window of size ``lookback_seasons``.
    """
    ordered = sorted(set(season_start_years))
    folds = []
    for i in range(1, len(ordered)):
        train_seasons = tuple(ordered[max(0, i - lookback_seasons) : i])
        folds.append(Fold(train_seasons=train_seasons, test_season=ordered[i]))
    return folds


def run_backtest(
    head: ModelHead[Any],
    features: pd.DataFrame,
    labels: pd.Series,
    metric_fn: MetricFn,
    *,
    season_col: str = "season_start_year",
    lookback_seasons: int = 15,
) -> BacktestResult:
    """Walk-forward validation: train on each fold's seasons, predict the next, roll forward.

    Args:
        head: The model head to evaluate (a fresh fit per fold — see ``models/base.py``).
        features: Feature rows, must include ``season_col``. Indexed like ``labels``.
        labels: Target values aligned to ``features`` by index.
        metric_fn: ``(predictions, actuals) -> metrics`` — pluggable so this harness doesn't
            need ``training/metrics.py`` (T2.9) to exist yet.
        season_col: Column in ``features`` carrying the season-start-year used to fold on.
        lookback_seasons: Training window size in seasons (data-pipeline.md §9 default ~15).

    Returns:
        Honest out-of-sample predictions across every fold, plus each fold's metrics.
    """
    folds = make_folds(features[season_col].tolist(), lookback_seasons=lookback_seasons)
    prediction_parts: list[pd.Series] = []
    fold_metrics: list[dict[str, float]] = []

    for fold in folds:
        train_mask = features[season_col].isin(fold.train_seasons)
        test_mask = features[season_col] == fold.test_season
        result = head.train(features.loc[train_mask], labels.loc[train_mask])
        test_features = features.loc[test_mask]
        predictions = head.predict(result.model, test_features)
        prediction_series = pd.Series(predictions, index=test_features.index, name="prediction")
        prediction_parts.append(prediction_series)
        fold_metrics.append(metric_fn(prediction_series, labels.loc[test_mask]))

    all_predictions = (
        pd.concat(prediction_parts).sort_index() if prediction_parts else pd.Series(dtype="float64")
    )
    return BacktestResult(
        folds=tuple(folds), predictions=all_predictions, fold_metrics=tuple(fold_metrics)
    )
