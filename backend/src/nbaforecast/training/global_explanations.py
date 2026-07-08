"""Global SHAP explanations at train time — explainability.md Prompt 4 / §4.

Where the per-prediction explainers (``explain/explainers.py``) answer "why *this* prediction,"
this module answers "what does the model rely on *overall*": mean |SHAP| feature importance
across the training set, plus per-feature dependence data (feature value vs. SHAP value) for the
top drivers. Both are logged to the model's MLflow run as a JSON artifact tied to its
``feature_version`` — the data behind a "How this model works" page (frontend.md stats hub),
emitted as data rather than server-rendered PNGs so the frontend renders it with its own D3/
Recharts stack (no matplotlib dependency on the training path).

Covers the TreeSHAP-explainable LightGBM batch heads (game win/margin/total, props). The linear
baseline is self-explaining (coefficients) and the live NN head lands in M4 — neither goes
through here.
"""

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd
import shap

from nbaforecast.models.base import ModelHead
from nbaforecast.models.game_prediction.margin import LightGBMMarginHead
from nbaforecast.models.game_prediction.total import LightGBMTotalHead
from nbaforecast.models.game_prediction.win_prob import LightGBMWinProbHead
from nbaforecast.models.game_prediction.win_prob import design_matrix as game_design_matrix
from nbaforecast.models.props.regressor import PropsRegressorHead
from nbaforecast.models.props.regressor import design_matrix as props_design_matrix
from nbaforecast.models.win_probability.in_game import LightGBMInGameWinProbHead
from nbaforecast.models.win_probability.in_game import design_matrix as in_game_design_matrix
from nbaforecast.training.registry import configure_tracking

logger = logging.getLogger(__name__)

GLOBAL_EXPLANATION_ARTIFACT_DIR = "explanations"
GLOBAL_EXPLANATION_FILENAME = "global_explanation.json"
TOP_DEPENDENCE_FEATURES = 6
MAX_DEPENDENCE_POINTS = 300
# TreeSHAP is O(rows); the in-game head trains on hundreds of thousands of per-event rows, so cap
# how many the global-importance pass explains. A few thousand rows estimate mean|SHAP| fine.
MAX_SHAP_ROWS = 5000


@dataclass(slots=True, frozen=True)
class GlobalExplanation:
    """A model's global feature importance + top-feature dependence data."""

    head: str
    feature_version: str
    n_samples: int
    mean_abs_shap: dict[str, float]
    dependence: dict[str, list[dict[str, float]]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "head": self.head,
            "feature_version": self.feature_version,
            "n_samples": self.n_samples,
            "mean_abs_shap": self.mean_abs_shap,
            "dependence": self.dependence,
        }


def _design_for_head(head: ModelHead[Any], features: pd.DataFrame) -> pd.DataFrame:
    """The exact design matrix ``head`` trains/predicts on — so importance aligns with the model."""
    if isinstance(head, PropsRegressorHead):
        return props_design_matrix(features)
    if isinstance(head, LightGBMInGameWinProbHead):
        return in_game_design_matrix(features)
    if isinstance(head, LightGBMWinProbHead | LightGBMMarginHead | LightGBMTotalHead):
        return game_design_matrix(features)
    raise TypeError(f"no global-explanation design matrix for head type {type(head).__name__}")


def _booster(model: Any) -> Any:
    """The tree model to explain — win/margin/total store it under ``booster``, props the median
    quantile booster under ``median``."""
    booster = model.get("booster") if isinstance(model, dict) else None
    if booster is None and isinstance(model, dict):
        booster = model.get("median")
    if booster is None:
        raise TypeError("model has no TreeSHAP-explainable booster ('booster' or 'median')")
    return booster


def _shap_matrix(explainer: shap.TreeExplainer, design: pd.DataFrame) -> np.ndarray:
    """SHAP values as a ``(n_rows, n_features)`` array, handling the binary-classifier list form."""
    raw = explainer.shap_values(design)
    # A binary classifier's TreeExplainer may return [class0, class1]; take the positive class.
    values = raw[1] if isinstance(raw, list) else raw
    return np.asarray(values)


def compute_global_explanation(
    head: ModelHead[Any],
    model: Any,
    features: pd.DataFrame,
    *,
    feature_version: str,
    top_dependence_features: int = TOP_DEPENDENCE_FEATURES,
    max_dependence_points: int = MAX_DEPENDENCE_POINTS,
) -> GlobalExplanation:
    """Mean |SHAP| importance + top-feature dependence data over ``features``.

    Args:
        head: The trained head (dispatches to the right design matrix).
        model: The head's fitted model object (``TrainResult.model``).
        features: The rows to compute global importance over (e.g. the training slice).
        feature_version: Stamped onto the artifact so importance ties to the exact feature defs.
        top_dependence_features: How many highest-importance features get dependence data.
        max_dependence_points: Row cap for the dependence scatter (keeps the artifact small).

    Returns:
        A :class:`GlobalExplanation`. ``mean_abs_shap`` is ordered by importance descending.
    """
    if features.empty:
        raise ValueError("cannot compute a global explanation over zero rows")

    # Cap the TreeSHAP pass: mean|SHAP| over a random sample estimates global importance fine and
    # keeps hundreds-of-thousands-of-rows heads (in-game win prob) from taking minutes here.
    if len(features) > MAX_SHAP_ROWS:
        features = features.sample(n=MAX_SHAP_ROWS, random_state=42)

    design = _design_for_head(head, features)
    explainer = model.get("explainer") if isinstance(model, dict) else None
    if explainer is None:
        explainer = shap.TreeExplainer(_booster(model))

    shap_matrix = _shap_matrix(explainer, design)
    mean_abs = np.abs(shap_matrix).mean(axis=0)
    columns = list(design.columns)
    ranked = sorted(
        zip(columns, mean_abs.tolist(), strict=True), key=lambda kv: kv[1], reverse=True
    )
    mean_abs_shap = {feature: float(value) for feature, value in ranked}

    limit = min(max_dependence_points, len(design))
    dependence: dict[str, list[dict[str, float]]] = {}
    for feature, _importance in ranked[:top_dependence_features]:
        col_index = columns.index(feature)
        feature_values = design[feature].to_numpy(dtype="float64")[:limit]
        shap_values = shap_matrix[:limit, col_index]
        dependence[feature] = [
            {"value": float(v), "shap": float(s)}
            for v, s in zip(feature_values, shap_values, strict=True)
        ]

    return GlobalExplanation(
        head=head.name,
        feature_version=feature_version,
        n_samples=len(design),
        mean_abs_shap=mean_abs_shap,
        dependence=dependence,
    )


def log_global_explanation(
    run_id: str,
    head: ModelHead[Any],
    model: Any,
    features: pd.DataFrame,
    *,
    feature_version: str,
) -> GlobalExplanation:
    """Compute the global explanation and log it as a JSON artifact on ``run_id``.

    Attaches to the already-closed training run via ``MlflowClient.log_artifact`` (mirrors how
    ``registry.log_run`` writes the model artifact), under ``explanations/``.
    """
    explanation = compute_global_explanation(head, model, features, feature_version=feature_version)
    configure_tracking()
    client = mlflow.tracking.MlflowClient()
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / GLOBAL_EXPLANATION_FILENAME
        path.write_text(json.dumps(explanation.to_payload(), indent=2))
        client.log_artifact(run_id, str(path), artifact_path=GLOBAL_EXPLANATION_ARTIFACT_DIR)
    logger.info(
        "logged global explanation for head %r (%d features, %d samples)",
        head.name,
        len(explanation.mean_abs_shap),
        explanation.n_samples,
    )
    return explanation
