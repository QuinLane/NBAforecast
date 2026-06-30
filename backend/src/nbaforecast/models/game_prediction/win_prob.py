"""Game win-probability models — modeling.md Prompt 3a.

Two sub-models sharing the same ``features_team_game`` inputs: a logistic-regression classifier
(the first real, multi-feature model — stronger than the single-feature Elo baseline) and a
LightGBM classifier with optional isotonic calibration (the hero model). Both implement
``ModelHead`` so they run through the T2.5 backtest harness, and both are held to the T2.6 Elo
baseline as their floor (``backend/tests/ml/test_baseline_floor.py``).
"""

from typing import Any

import lightgbm as lgb
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nbaforecast.features.team_game import FEATURE_COLUMNS
from nbaforecast.models.base import ModelHead, TrainResult

GAME_WIN_FEATURE_VERSION = "game_win_v1"

# is_home isn't in FEATURE_COLUMNS (it's a key/context column on features_team_game) but is
# genuinely predictive — let the model learn the home-court effect from data instead of
# hardcoding it the way the Elo baseline's fixed +/-100 adjustment does.
MODEL_FEATURE_COLUMNS: tuple[str, ...] = (*FEATURE_COLUMNS, "is_home")


def _design_matrix(features: pd.DataFrame) -> pd.DataFrame:
    matrix = features[list(MODEL_FEATURE_COLUMNS)].copy()
    matrix["is_home"] = matrix["is_home"].astype(float)
    return matrix


class LogisticWinProbHead(ModelHead[pd.Series]):
    """Multi-feature logistic regression — the first real model above the Elo/constant baselines.

    L1-regularized (``liblinear``) on standardized, median-imputed features. With 25+ inputs and
    a modest number of rows per walk-forward fold, an unregularized fit overfits badly (verified
    empirically: it scored *worse* than the constant-rate baseline); L1's sparsity is what lets
    this model actually beat Elo rather than just memorize noise in the extra features.
    """

    def __init__(self, *, C: float = 0.1) -> None:
        self._C = C

    @property
    def name(self) -> str:
        return "game_win_logistic"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        design = _design_matrix(features)
        pipeline = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=2000, C=self._C, penalty="l1", solver="liblinear"),
        )
        pipeline.fit(design, labels)
        return TrainResult(model=pipeline, metrics={}, feature_version=GAME_WIN_FEATURE_VERSION)

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        probs = model.predict_proba(_design_matrix(features))[:, 1]
        return pd.Series(probs, index=features.index, name="prediction")

    def explain(self, model: Any, features: pd.DataFrame) -> dict[str, Any]:
        logistic = model.named_steps["logisticregression"]
        coefficients = dict(zip(MODEL_FEATURE_COLUMNS, logistic.coef_[0].tolist(), strict=True))
        return {"contributions": coefficients}


class LightGBMWinProbHead(ModelHead[pd.Series]):
    """LightGBM classifier, the hero model, with optional post-hoc isotonic calibration.

    Calibration fits an :class:`~sklearn.isotonic.IsotonicRegression` mapping raw predicted
    probabilities to calibrated ones, using a chronological holdout *carved out of the training
    fold itself* — the booster never sees the calibration rows, and neither ever sees the
    harness's test fold. **Off by default**: modeling.md §6 says to apply it "when the
    reliability curve warrants it," not unconditionally, and isotonic regression is fully
    non-parametric — it easily overfits a small or unrepresentative calibration sample (verified
    empirically while building this: it roughly doubled held-out log-loss on this project's own
    floor test even with 1000+ calibration rows). Enable it explicitly once T2.9's reliability
    curve confirms the raw booster is actually miscalibrated enough to be worth correcting;
    ``min_rows_to_calibrate`` is a backstop, not a substitute for that check.
    """

    def __init__(
        self,
        *,
        calibrate: bool = False,
        calibration_holdout_frac: float = 0.2,
        min_rows_to_calibrate: int = 2000,
        **lgbm_params: Any,
    ) -> None:
        self._calibrate = calibrate
        self._calibration_holdout_frac = calibration_holdout_frac
        self._min_rows_to_calibrate = min_rows_to_calibrate
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
        return "game_win"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        ordered = features.sort_values("game_date", kind="mergesort")

        if self._calibrate and len(ordered) >= self._min_rows_to_calibrate:
            split = int(len(ordered) * (1 - self._calibration_holdout_frac))
            fit_index, calib_index = ordered.index[:split], ordered.index[split:]
        else:
            fit_index, calib_index = ordered.index, pd.Index([])

        booster = lgb.LGBMClassifier(**self._lgbm_params)
        booster.fit(_design_matrix(features.loc[fit_index]), labels.loc[fit_index])

        calibrator: IsotonicRegression | None = None
        if len(calib_index) > 0:
            raw_calib_probs = booster.predict_proba(_design_matrix(features.loc[calib_index]))[:, 1]
            calibrator = IsotonicRegression(out_of_bounds="clip")
            calibrator.fit(raw_calib_probs, labels.loc[calib_index])

        return TrainResult(
            model={"booster": booster, "calibrator": calibrator},
            metrics={},
            feature_version=GAME_WIN_FEATURE_VERSION,
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        raw_probs = model["booster"].predict_proba(_design_matrix(features))[:, 1]
        if model["calibrator"] is not None:
            raw_probs = model["calibrator"].predict(raw_probs)
        return pd.Series(raw_probs, index=features.index, name="prediction")

    def explain(self, model: Any, features: pd.DataFrame) -> dict[str, Any]:
        importances = dict(
            zip(
                MODEL_FEATURE_COLUMNS,
                model["booster"].feature_importances_.tolist(),
                strict=True,
            )
        )
        return {"contributions": importances}
