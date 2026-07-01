"""Props baselines — modeling.md §3 + Prompt 2.

The floor a real per-stat props regressor (T3.3) must clear: the player's own season average and
last-10-game average, for each of PTS/REB/AST/3PM. Both are zero-parameter — they read an
already-materialized rolling/expanding column straight off ``features_player_game`` rather than
fitting anything, mirroring ``models/game_prediction/baseline.py``'s "predict a pre-computed
column" shape.
"""

from typing import Any

import pandas as pd

from nbaforecast.explain.schema import Explanation, ExplanationUnits
from nbaforecast.models.base import ModelHead, TrainResult

# Stat -> (season-to-date column, last-10-game rolling column) on features_player_game.
STAT_BASELINE_COLUMNS: dict[str, tuple[str, str]] = {
    "pts": ("season_avg_pts", "roll10_pts"),
    "reb": ("season_avg_reb", "roll10_reb"),
    "ast": ("season_avg_ast", "roll10_ast"),
    "fg3m": ("season_avg_fg3m", "roll10_fg3m"),
}

_STAT_UNITS = {
    "pts": ExplanationUnits.POINTS,
    "reb": ExplanationUnits.REBOUNDS,
    "ast": ExplanationUnits.ASSISTS,
    "fg3m": ExplanationUnits.THREE_POINTERS_MADE,
}

_EXPLANATION_NOTES = (
    "This explanation shows which factors moved the model's own prediction, and by how much — "
    "it reflects the model's reasoning, not a causal claim about the player's performance."
)


class SeasonAverageHead(ModelHead[pd.Series]):
    """Predicts each row's already-materialized season-to-date average for ``stat``.

    No fitting: ``features_player_game``'s ``season_avg_{stat}`` column already is this
    prediction (leakage-safe by construction — feature-engineering.md §2). A player's very first
    game of a season has no prior average (``NaN``); callers fall back to the training fold's
    overall mean, mirroring how the game-win constant baseline handles a cold start.
    """

    def __init__(self, stat: str) -> None:
        if stat not in STAT_BASELINE_COLUMNS:
            raise ValueError(f"unknown props stat: {stat!r}")
        self._stat = stat
        self._season_col, _ = STAT_BASELINE_COLUMNS[stat]

    @property
    def name(self) -> str:
        return f"props_{self._stat}_baseline_season_avg"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_player_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(
            model={"fallback_mean": float(labels.mean())}, metrics={}, feature_version="baseline"
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        predictions = features[self._season_col].fillna(model["fallback_mean"])
        predictions.name = "prediction"
        return predictions

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        if len(features) != 1:
            raise ValueError("SeasonAverageHead.explain explains exactly one row at a time")
        value = float(features[self._season_col].fillna(model["fallback_mean"]).iloc[0])
        return Explanation(
            baseline=value,
            prediction=value,
            contributions=[],  # a single pre-computed column, nothing to decompose
            units=_STAT_UNITS[self._stat],
            notes=_EXPLANATION_NOTES,
        )


class LastTenGameAverageHead(ModelHead[pd.Series]):
    """Predicts each row's already-materialized last-10-game rolling average for ``stat``.

    Same shape as :class:`SeasonAverageHead` but reads ``roll10_{stat}`` — the "hot hand" /
    recent-form baseline (modeling.md §3).
    """

    def __init__(self, stat: str) -> None:
        if stat not in STAT_BASELINE_COLUMNS:
            raise ValueError(f"unknown props stat: {stat!r}")
        self._stat = stat
        _, self._roll10_col = STAT_BASELINE_COLUMNS[stat]

    @property
    def name(self) -> str:
        return f"props_{self._stat}_baseline_last10"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_player_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(
            model={"fallback_mean": float(labels.mean())}, metrics={}, feature_version="baseline"
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        predictions = features[self._roll10_col].fillna(model["fallback_mean"])
        predictions.name = "prediction"
        return predictions

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        if len(features) != 1:
            raise ValueError("LastTenGameAverageHead.explain explains exactly one row at a time")
        value = float(features[self._roll10_col].fillna(model["fallback_mean"]).iloc[0])
        return Explanation(
            baseline=value,
            prediction=value,
            contributions=[],
            units=_STAT_UNITS[self._stat],
            notes=_EXPLANATION_NOTES,
        )
