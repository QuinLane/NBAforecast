"""Game point-margin model — modeling.md Prompt 3b.

A LightGBM regressor sharing the exact same ``features_team_game`` inputs (and the same
``MODEL_FEATURE_COLUMNS``/``design_matrix`` selection) as the win-prob classifier in
``win_prob.py``. The target is this row's team's point margin (``team_score - opponent_score``,
see ``features/team_game.py``'s ``_build_history``) — i.e. margin is already expressed
"self-relative," consistent with how every other differential feature on this table
(``rating_diff``, ``elo_diff``, ...) is oriented, and with how ``is_home`` is a plain input
feature rather than baked into the target's sign. For the home team's row that's exactly the
home-team spread; for the away team's row on the same game it's the same margin negated, which
is what lets one shared design matrix serve both rows without a separate home/away target
convention.

Evaluated through the T2.5 backtest harness against the modeling.md §3 margin baselines
(``baseline.py``): a constant home-court edge and a rating-difference linear fit.
"""

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from nbaforecast.models.base import ModelHead, TrainResult
from nbaforecast.models.game_prediction.win_prob import design_matrix

GAME_MARGIN_FEATURE_VERSION = "game_margin_v1"

_EXPLANATION_NOTES = (
    "This explanation shows which factors moved the model's own prediction, and by how much — "
    "it reflects the model's reasoning, not a causal claim about why the game was won by that "
    "margin."
)


class LightGBMMarginHead(ModelHead[pd.Series]):
    """LightGBM regressor for a team's point margin, on the win-prob classifier's feature set.

    Shallow, regularized trees (mirroring ``LightGBMWinProbHead``'s param choices) — margin is a
    noisy target (final-score variance dwarfs any single feature's signal) so an unregularized
    fit overfits the same way the win-prob classifier's did.
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
        return "game_margin"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        booster = lgb.LGBMRegressor(**self._lgbm_params)
        booster.fit(design_matrix(features), labels)
        return TrainResult(
            model={"booster": booster, "explainer": shap.TreeExplainer(booster)},
            metrics={},
            feature_version=GAME_MARGIN_FEATURE_VERSION,
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        predictions = model["booster"].predict(design_matrix(features))
        return pd.Series(predictions, index=features.index, name="prediction")

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        """TreeSHAP explanation, additive in points — a regressor's raw output *is* the target
        scale, so (unlike the win-prob classifier) no log-odds-to-probability conversion is
        needed: SHAP values already sum exactly to ``prediction - baseline`` in points."""
        if len(features) != 1:
            raise ValueError("LightGBMMarginHead.explain explains exactly one row at a time")

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
