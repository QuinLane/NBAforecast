"""Props regressors — modeling.md Prompt 4.

One LightGBM regressor per stat (PTS/REB/AST/3PM) over ``features_player_game``, each producing a
point estimate *and* a quantile-based prediction interval: three boosters per stat (lower, median,
upper quantile) sharing the same feature set and hyperparameters, differing only in LightGBM's
``objective="quantile"`` + ``alpha``. The median booster's prediction is the point estimate (median
absolute error is what MAE actually measures); the lower/upper boosters bound the interval —
modeling.md §6's "quantile regression ... to produce honest prediction intervals."
"""

from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from nbaforecast.features.player_game import FEATURE_COLUMNS
from nbaforecast.models.base import ModelHead, TrainResult

PROPS_FEATURE_VERSION = "props_v1"

# is_home isn't in FEATURE_COLUMNS (it's a key/context column on features_player_game) but is
# genuinely predictive for props too (home/road scoring splits) — same rationale as
# models/game_prediction/win_prob.py's MODEL_FEATURE_COLUMNS.
MODEL_FEATURE_COLUMNS: tuple[str, ...] = (*FEATURE_COLUMNS, "is_home")

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


@dataclass(slots=True, frozen=True)
class PropsPrediction:
    """A props point estimate plus its quantile-based prediction interval."""

    point: pd.Series
    lower: pd.Series
    upper: pd.Series


def design_matrix(features: pd.DataFrame) -> pd.DataFrame:
    """Select + cast ``MODEL_FEATURE_COLUMNS`` from a ``features_player_game`` row.

    Public (not module-private) so ``explain()`` can align a TreeSHAP explanation with exactly
    what the model saw — mirrors ``models/game_prediction/win_prob.py``'s ``design_matrix``.
    """
    matrix = features[list(MODEL_FEATURE_COLUMNS)].copy()
    matrix["is_home"] = matrix["is_home"].astype(float)
    return matrix


class PropsRegressorHead(ModelHead[pd.Series]):
    """LightGBM quantile regressor trio (lower/median/upper) for one props stat.

    ``predict()`` returns only the median booster's point estimate — a plain ``pd.Series``, the
    ``ModelHead`` contract's ``PredictionT``, consumed directly by the backtest harness's
    ``metric_fn``. The full :class:`PropsPrediction` — point + interval — is available via
    :meth:`predict_with_interval` for callers (the props service, interval-coverage evaluation)
    that need the interval too.
    """

    def __init__(
        self,
        stat: str,
        *,
        interval_coverage: float = 0.8,
        **lgbm_params: Any,
    ) -> None:
        if stat not in _STAT_UNITS:
            raise ValueError(f"unknown props stat: {stat!r}")
        self._stat = stat
        self._lower_alpha = (1 - interval_coverage) / 2
        self._upper_alpha = 1 - self._lower_alpha
        self._lgbm_params: dict[str, Any] = {
            "n_estimators": 100,
            "max_depth": 3,
            "learning_rate": 0.05,
            "min_child_samples": 20,
            "reg_lambda": 1.5,
            "subsample": 0.8,
            "colsample_bytree": 0.7,
            "random_state": 42,
            "verbose": -1,
            **lgbm_params,
        }

    @property
    def name(self) -> str:
        return f"props_{self._stat}"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_player_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        design = design_matrix(features)

        median = lgb.LGBMRegressor(objective="quantile", alpha=0.5, **self._lgbm_params).fit(
            design, labels
        )
        lower = lgb.LGBMRegressor(
            objective="quantile", alpha=self._lower_alpha, **self._lgbm_params
        ).fit(design, labels)
        upper = lgb.LGBMRegressor(
            objective="quantile", alpha=self._upper_alpha, **self._lgbm_params
        ).fit(design, labels)

        return TrainResult(
            model={
                "median": median,
                "lower": lower,
                "upper": upper,
                "explainer": shap.TreeExplainer(median),
            },
            metrics={},
            feature_version=PROPS_FEATURE_VERSION,
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        design = design_matrix(features)
        point = pd.Series(model["median"].predict(design), index=features.index, name="prediction")
        return point.clip(lower=0.0)  # counting stats are never negative

    def predict_with_interval(self, model: Any, features: pd.DataFrame) -> PropsPrediction:
        """Point estimate + the quantile-based ``[lower, upper]`` prediction interval."""
        design = design_matrix(features)
        point = self.predict(model, features)
        lower = pd.Series(model["lower"].predict(design), index=features.index, name="lower").clip(
            lower=0.0
        )
        upper = pd.Series(model["upper"].predict(design), index=features.index, name="upper").clip(
            lower=0.0
        )
        # A quantile booster's lower/upper trees are fit independently, so on a small or noisy
        # fold they can occasionally cross the point estimate — clip to keep the interval sane.
        lower = pd.Series(np.minimum(lower, point), index=features.index, name="lower")
        upper = pd.Series(np.maximum(upper, point), index=features.index, name="upper")
        return PropsPrediction(point=point, lower=lower, upper=upper)

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        """TreeSHAP explanation of the median booster's point estimate, in the stat's own units."""
        if len(features) != 1:
            raise ValueError("PropsRegressorHead.explain explains exactly one row at a time")

        design = design_matrix(features)
        explainer = model.get("explainer") or shap.TreeExplainer(model["median"])
        raw_shap = explainer.shap_values(design)
        # A LightGBM regressor's TreeExplainer always returns a single array (unlike a
        # classifier's [class0, class1] list) — one row per input, taken here.
        shap_row = raw_shap[0]
        baseline = float(np.asarray(explainer.expected_value).reshape(-1)[-1])

        order = np.argsort(-np.abs(shap_row))
        contributions = []
        for i in order:
            raw_value = design.iloc[0, i]
            value = _to_python_scalar(raw_value)
            contributions.append(
                Contribution(
                    feature=design.columns[i],
                    display_label=design.columns[i],
                    raw_value=value,
                    formatted_value=str(raw_value),
                    contribution=float(shap_row[i]),
                    direction="up" if shap_row[i] >= 0 else "down",
                )
            )

        return Explanation(
            baseline=baseline,
            prediction=baseline + float(shap_row.sum()),
            contributions=contributions,
            units=_STAT_UNITS[self._stat],
            notes=_EXPLANATION_NOTES,
        )


def _to_python_scalar(value: Any) -> float | int | str | bool | None:
    if isinstance(value, np.generic):
        result: float | int | str | bool = value.item()
        return result
    return value  # type: ignore[no-any-return]
