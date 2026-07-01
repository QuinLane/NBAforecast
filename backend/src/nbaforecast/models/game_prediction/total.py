"""Game total-points model — modeling.md Prompt 3c.

A LightGBM regressor sharing the exact same ``features_team_game`` inputs (and the same
``MODEL_FEATURE_COLUMNS``/``design_matrix`` selection) as the win-prob classifier in
``win_prob.py`` and the margin regressor in ``margin.py``. The target is the game's combined
score (``home_score + away_score``) — identical for both teams' rows on the same game, so
either row's features can be used to predict it; the model simply gets to see the game twice
(once from each team's feature perspective), which is consistent with how every other game-
prediction head on this table is trained (one row per team per game).

Evaluated through the T2.5 backtest harness against the modeling.md §3 total baselines
(``baseline.py``): the league-average total, and the two teams' average totals.
"""

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from nbaforecast.models.base import ModelHead, TrainResult
from nbaforecast.models.game_prediction.win_prob import design_matrix

GAME_TOTAL_FEATURE_VERSION = "game_total_v1"

_EXPLANATION_NOTES = (
    "This explanation shows which factors moved the model's own prediction, and by how much — "
    "it reflects the model's reasoning, not a causal claim about why the game finished with "
    "that combined score."
)


class LightGBMTotalHead(ModelHead[pd.Series]):
    """LightGBM regressor for a game's combined total points, on the win-prob classifier's
    feature set.

    Shallow, regularized trees (mirroring ``LightGBMWinProbHead``'s param choices) — the same
    overfitting risk that motivated those choices for margin applies here: total is a noisy,
    pace-driven target and a deep/unregularized fit would memorize noise rather than learn the
    genuine pace/rating signal.
    """

    def __init__(self, **lgbm_params: Any) -> None:
        self._lgbm_params: dict[str, Any] = {
            "n_estimators": 100,
            "max_depth": 2,
            "learning_rate": 0.05,
            "min_child_samples": 20,
            "reg_lambda": 1.5,
            "subsample": 0.8,
            "colsample_bytree": 0.5,
            "random_state": 42,
            "verbose": -1,
            **lgbm_params,
        }

    @property
    def name(self) -> str:
        return "game_total"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        booster = lgb.LGBMRegressor(**self._lgbm_params)
        booster.fit(design_matrix(features), labels)
        return TrainResult(
            model={"booster": booster, "explainer": shap.TreeExplainer(booster)},
            metrics={},
            feature_version=GAME_TOTAL_FEATURE_VERSION,
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        predictions = model["booster"].predict(design_matrix(features))
        return pd.Series(predictions, index=features.index, name="prediction")

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        """TreeSHAP explanation, additive in points — a regressor's raw output *is* the target
        scale, so (unlike the win-prob classifier) no log-odds-to-probability conversion is
        needed: SHAP values already sum exactly to ``prediction - baseline`` in points."""
        if len(features) != 1:
            raise ValueError("LightGBMTotalHead.explain explains exactly one row at a time")

        design = design_matrix(features)
        explainer = model.get("explainer") or shap.TreeExplainer(model["booster"])
        raw_shap = np.asarray(explainer.shap_values(design))
        shap_row = raw_shap[0]
        baseline = float(np.asarray(explainer.expected_value).reshape(-1)[-1])

        order = np.argsort(-np.abs(shap_row))
        raw_values = design.iloc[0]
        contributions = [
            Contribution(
                feature=str(design.columns[i]),
                display_label=str(design.columns[i]),
                raw_value=raw_values.iloc[i],
                formatted_value=str(raw_values.iloc[i]),
                contribution=float(shap_row[i]),
                direction="up" if shap_row[i] >= 0 else "down",
            )
            for i in order
        ]

        return Explanation(
            baseline=baseline,
            prediction=baseline + float(shap_row.sum()),
            contributions=contributions,
            units=ExplanationUnits.POINTS,
            notes=_EXPLANATION_NOTES,
        )
