"""Evaluation metrics — modeling.md §5 + Prompt 8.

Classification metrics for games/live (log-loss primary, Brier, AUC, accuracy, a calibration/
reliability curve) and regression metrics for props (MAE, RMSE, prediction-interval coverage).
Pure functions over predictions/actuals, no framework dependency beyond numpy/pandas, so they
compose directly with ``training/backtest.py``'s ``metric_fn`` callable via
:func:`classification_metrics` / :func:`regression_metrics`.
"""

import numpy as np
import pandas as pd

_LOG_LOSS_EPS = 1e-15


def log_loss(predictions: pd.Series, actuals: pd.Series) -> float:
    """Binary cross-entropy — the primary classification metric (modeling.md §5). 0 is perfect;
    lower is better. Rewards honest probabilities, unlike accuracy."""
    clipped = predictions.clip(_LOG_LOSS_EPS, 1 - _LOG_LOSS_EPS)
    return float(-(actuals * np.log(clipped) + (1 - actuals) * np.log(1 - clipped)).mean())


def brier_score(predictions: pd.Series, actuals: pd.Series) -> float:
    """Mean squared error of probabilistic predictions. 0 is perfect; lower is better."""
    return float(((predictions - actuals) ** 2).mean())


def auc(predictions: pd.Series, actuals: pd.Series) -> float:
    """Area under the ROC curve via the rank-sum (Mann-Whitney U) formula — avoids needing
    scikit-learn's ``roc_auc_score`` just for this. 0.5 = no better than random; 1.0 = perfect
    separation; 0.0 = perfectly *inverted* separation.
    """
    n_positive = int((actuals == 1).sum())
    n_negative = int((actuals == 0).sum())
    if n_positive == 0 or n_negative == 0:
        raise ValueError("AUC is undefined when actuals contains only one class")
    ranks = predictions.rank()  # ties get the average rank, as the standard formula expects
    sum_positive_ranks = float(ranks[actuals == 1].sum())
    return (sum_positive_ranks - n_positive * (n_positive + 1) / 2) / (n_positive * n_negative)


def accuracy(predictions: pd.Series, actuals: pd.Series, *, threshold: float = 0.5) -> float:
    """Fraction of predictions on the correct side of ``threshold``."""
    predicted_class = (predictions >= threshold).astype(float)
    return float((predicted_class == actuals).mean())


def calibration_curve(
    predictions: pd.Series, actuals: pd.Series, *, n_bins: int = 10
) -> pd.DataFrame:
    """Reliability curve: mean predicted probability vs. observed frequency, per equal-width bin.

    A well-calibrated model has ``mean_actual`` ≈ ``mean_predicted`` in every bin (a 65%
    prediction should win ~65% of the time — modeling.md §1). Empty bins are dropped.
    """
    bin_edges = np.linspace(0, 1, n_bins + 1).tolist()
    bins = pd.cut(predictions, bins=bin_edges, include_lowest=True)
    frame = pd.DataFrame(
        {"prediction": predictions.to_numpy(), "actual": actuals.to_numpy(), "bin": bins}
    )
    grouped = frame.groupby("bin", observed=True)
    curve = grouped.agg(
        mean_predicted=("prediction", "mean"),
        mean_actual=("actual", "mean"),
        count=("actual", "size"),
    )
    return curve.reset_index(drop=True)


def mae(predictions: pd.Series, actuals: pd.Series) -> float:
    """Mean absolute error — a props regression metric (modeling.md §5)."""
    return float((predictions - actuals).abs().mean())


def rmse(predictions: pd.Series, actuals: pd.Series) -> float:
    """Root mean squared error — penalizes large misses more than MAE."""
    return float(np.sqrt(((predictions - actuals) ** 2).mean()))


def interval_coverage(actuals: pd.Series, lower: pd.Series, upper: pd.Series) -> float:
    """Fraction of actuals falling within ``[lower, upper]``.

    Compare against the interval's nominal coverage (e.g. ~0.8 for an 80% interval) — an honest
    interval contains the outcome about that often, not more, not less (modeling.md §5).
    """
    within_interval = (actuals >= lower) & (actuals <= upper)
    return float(within_interval.mean())


def classification_metrics(predictions: pd.Series, actuals: pd.Series) -> dict[str, float]:
    """Bundle of the §5 classification metrics — drop-in ``training/backtest.py`` ``metric_fn``."""
    metrics = {
        "log_loss": log_loss(predictions, actuals),
        "brier_score": brier_score(predictions, actuals),
        "accuracy": accuracy(predictions, actuals),
    }
    if actuals.nunique() > 1:
        metrics["auc"] = auc(predictions, actuals)
    return metrics


def regression_metrics(predictions: pd.Series, actuals: pd.Series) -> dict[str, float]:
    """Bundle of the §5 regression metrics — drop-in ``training/backtest.py`` ``metric_fn``."""
    return {"mae": mae(predictions, actuals), "rmse": rmse(predictions, actuals)}
