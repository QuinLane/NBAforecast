"""``ModelHead`` — the uniform contract every prediction head implements (roadmap.md §1).

A drop-in interface so adding a new head (props, RAPM, live, a future v2 head) is "implement
this + register," not "rewire the system." The backtest harness (``training/backtest.py``), the
champion/challenger gate (``training/registry.py``, T2.8), and the API's ``ModelProvider``
(backend-api.md §2, T2.13) all depend only on this interface, never on a head's internals.

Heads are **stateless wrt fitted parameters**: ``train()`` returns the fitted estimator rather
than storing it on ``self``, and ``predict``/``explain`` take it as an explicit argument. This
lets one ``ModelHead`` instance serve many walk-forward folds in the backtest harness (a fresh
fit per fold) and lets the API hold a single long-lived head wrapping whichever MLflow champion
artifact is currently loaded — without the two use cases fighting over mutable instance state.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

from nbaforecast.explain.schema import Explanation


@dataclass(slots=True, frozen=True)
class TrainResult:
    """What ``ModelHead.train()`` produces: the fitted estimator plus train-time metrics.

    ``model`` is intentionally untyped — heads wrap different underlying libraries (LightGBM,
    scikit-learn, a small PyTorch net for live win-prob, ridge for RAPM).
    """

    model: Any
    metrics: dict[str, float]
    feature_version: str


class ModelHead[PredictionT](ABC):
    """Uniform contract for every prediction head.

    Subclasses implement ``train``/``predict``/``explain`` over their own feature table and
    prediction shape (``PredictionT``); callers never need to know which library a head wraps.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """MLflow experiment/model name (engineering-standards.md §5), e.g. ``"game_win"``."""

    @property
    @abstractmethod
    def feature_dependencies(self) -> tuple[str, ...]:
        """Gold feature table name(s) this head reads (``features/materialize.py`` tables)."""

    @abstractmethod
    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        """Fit on a training slice; returns the fitted model + train-time metrics.

        Does not mutate ``self`` — the caller (backtest harness, retraining flow) owns the
        returned :class:`TrainResult` and passes its ``model`` to ``predict``/``explain``.
        """

    @abstractmethod
    def predict(self, model: Any, features: pd.DataFrame) -> PredictionT:
        """Predict from an already-fitted ``model`` (a backtest fold's fit, or the loaded
        MLflow champion) for already-materialized feature rows."""

    @abstractmethod
    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        """Per-row explanation from an already-fitted ``model`` (explain.schema.Explanation)."""
