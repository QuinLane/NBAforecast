"""In-game (live/replay) win-probability head — roadmap M3.9.

A LightGBM classifier over :mod:`nbaforecast.features.game_state`: given the score margin, time
remaining, and period at a moment in the game, how likely is the home team to win? This is the
model behind the game-page win-probability timeline — replaying a finished game's stored
play-by-play through it draws the curve, and TreeSHAP explains each moment. Same ``ModelHead``
contract and TreeSHAP explainer as the pre-game head, so it serves through the same
``ModelProvider`` and renders in the same ``PredictionExplainer``.
"""

from typing import Any

import lightgbm as lgb
import pandas as pd
import shap

from nbaforecast.explain.schema import Explanation
from nbaforecast.features.game_state import GAME_STATE_FEATURE_COLUMNS
from nbaforecast.models.base import ModelHead, TrainResult

IN_GAME_WIN_FEATURE_VERSION = "in_game_win_v1"


def design_matrix(features: pd.DataFrame) -> pd.DataFrame:
    """Select + cast the game-state columns the model reads (public: the explainer reuses it)."""
    return features[list(GAME_STATE_FEATURE_COLUMNS)].astype(float)


class LightGBMInGameWinProbHead(ModelHead[pd.Series]):
    """LightGBM home-win-probability classifier over in-game state.

    Deeper/wider than the pre-game head: with only three strong, monotone-ish inputs and a huge
    per-event row count, the model can afford more trees to capture the sharp margin-by-time
    interaction (a 5-point lead means very different things with 20 minutes vs. 20 seconds left).
    """

    def __init__(self, **lgbm_params: Any) -> None:
        self._lgbm_params: dict[str, Any] = {
            "n_estimators": 300,
            "max_depth": 4,
            "learning_rate": 0.05,
            "min_child_samples": 200,
            "reg_lambda": 1.0,
            "subsample": 0.8,
            "colsample_bytree": 0.9,
            "random_state": 42,
            "verbose": -1,
            **lgbm_params,
        }

    @property
    def name(self) -> str:
        return "in_game_win"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("play_by_play",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        booster = lgb.LGBMClassifier(**self._lgbm_params)
        booster.fit(design_matrix(features), labels)
        return TrainResult(
            model={"booster": booster, "explainer": shap.TreeExplainer(booster)},
            metrics={},
            feature_version=IN_GAME_WIN_FEATURE_VERSION,
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        probs = model["booster"].predict_proba(design_matrix(features))[:, 1]
        return pd.Series(probs, index=features.index, name="prediction")

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        # Deferred import avoids a cycle: explain.explainers imports design_matrix helpers.
        from nbaforecast.explain.explainers import explain_lightgbm_classifier

        return explain_lightgbm_classifier(model, features, design_fn=design_matrix)
