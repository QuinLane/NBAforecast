"""Per-head explainers — explainability.md Prompt 2.

A unified ``explain(...) -> Explanation`` per technique, dispatched by each ``ModelHead``'s own
``explain()`` method (T2.5's contract): TreeSHAP for the LightGBM game-win model, and a
coefficient-based explainer for the linear logistic baseline — "self-explaining," the same
treatment RAPM's ridge coefficients get (explainability.md §1). The live NN's gradient-based
explainer and RAPM's own dispatch branch land with those heads in M3/M4.

Every ``display_label``/``formatted_value`` here is a placeholder (the raw feature name and
``str(raw_value)``) — T2.11's feature humanizer decorates them into the real human-readable form
described in explainability.md §6; that task hasn't landed yet, so this one produces
schema-valid, structurally-correct explanations now and gets prettier later, deliberately.
"""

from typing import Any

import numpy as np
import pandas as pd
import shap

from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from nbaforecast.models.game_prediction.win_prob import design_matrix

_NOTES = (
    "This explanation shows which factors moved the model's own prediction, and by how much — "
    "it reflects the model's reasoning, not a causal claim about why the game was won."
)


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def _to_python_scalar(value: Any) -> float | int | str | bool | None:
    if isinstance(value, np.generic):
        result: float | int | str | bool = value.item()
        return result
    return value  # type: ignore[no-any-return]


def _sorted_by_magnitude(
    feature_names: list[str], values: np.ndarray, raw_values: pd.Series
) -> list[tuple[str, float, Any]]:
    """Pair each feature with its contribution value, sorted by |value| descending (§5)."""
    order = np.argsort(-np.abs(values))
    return [(feature_names[i], float(values[i]), raw_values.iloc[i]) for i in order]


def _placeholder_contribution(feature: str, value: float, raw_value: Any) -> Contribution:
    return Contribution(
        feature=feature,
        display_label=feature,
        raw_value=_to_python_scalar(raw_value),
        formatted_value=str(raw_value),
        contribution=value,
        direction="up" if value >= 0 else "down",
    )


def explain_lightgbm_classifier(
    model: dict[str, Any],
    features: pd.DataFrame,
    *,
    units: ExplanationUnits = ExplanationUnits.PROBABILITY_POINTS,
) -> Explanation:
    """TreeSHAP explanation for one row of a LightGBM binary classifier (e.g. game win-prob).

    SHAP values for a tree classifier come out in log-odds (margin) space (explainability.md
    §3). For ``units=PROBABILITY_POINTS``, contributions are converted via a *cumulative*
    logistic mapping in magnitude order: each feature's probability-point contribution is the
    change in ``sigmoid(running log-odds total)`` when that feature is added — a telescoping sum
    that preserves additivity (``sum(contributions) == prediction - baseline``) exactly, unlike a
    naive per-feature ``sigmoid(shap_value)``. ``units=LOG_ODDS`` skips the conversion.
    """
    if len(features) != 1:
        raise ValueError("explain_lightgbm_classifier explains exactly one row at a time")

    design = design_matrix(features)
    explainer = model.get("explainer") or shap.TreeExplainer(model["booster"])
    raw_shap = explainer.shap_values(design)
    # Some shap/LightGBM version combinations return a [class0, class1] list for binary
    # classifiers instead of a single margin-space array; always take the positive class.
    shap_row = raw_shap[1][0] if isinstance(raw_shap, list) else raw_shap[0]
    baseline_log_odds = float(np.asarray(explainer.expected_value).reshape(-1)[-1])

    ordered = _sorted_by_magnitude(list(design.columns), shap_row, design.iloc[0])

    if units is ExplanationUnits.LOG_ODDS:
        contributions = [_placeholder_contribution(f, v, r) for f, v, r in ordered]
        prediction_log_odds = baseline_log_odds + sum(value for _, value, _ in ordered)
        return Explanation(
            baseline=baseline_log_odds,
            prediction=prediction_log_odds,
            contributions=contributions,
            units=ExplanationUnits.LOG_ODDS,
            notes=_NOTES,
        )

    running_log_odds = baseline_log_odds
    contributions = []
    for feature, shap_value, raw_value in ordered:
        prev_prob = _sigmoid(running_log_odds)
        running_log_odds += shap_value
        new_prob = _sigmoid(running_log_odds)
        contributions.append(
            Contribution(
                feature=feature,
                display_label=feature,
                raw_value=_to_python_scalar(raw_value),
                formatted_value=str(raw_value),
                contribution=new_prob - prev_prob,
                direction="up" if new_prob >= prev_prob else "down",
            )
        )

    return Explanation(
        baseline=_sigmoid(baseline_log_odds),
        prediction=_sigmoid(running_log_odds),
        contributions=contributions,
        units=ExplanationUnits.PROBABILITY_POINTS,
        notes=_NOTES,
    )


def explain_linear_classifier(model: Any, features: pd.DataFrame) -> Explanation:
    """Self-explaining coefficient-based explanation for a linear classifier pipeline.

    A linear model is its own explainer: each standardized feature's contribution to the
    log-odds prediction is exactly ``coefficient * standardized_value`` — no SHAP needed. This
    is the same treatment explainability.md §1 gives RAPM's ridge coefficients. Always in
    log-odds space — the probability-point conversion (see ``explain_lightgbm_classifier``)
    isn't implemented here, as it's not needed for a baseline-tier model.
    """
    if len(features) != 1:
        raise ValueError("explain_linear_classifier explains exactly one row at a time")

    design = design_matrix(features)
    imputer = model.named_steps["simpleimputer"]
    scaler = model.named_steps["standardscaler"]
    classifier = model.named_steps["logisticregression"]

    imputed = imputer.transform(design)
    standardized = scaler.transform(imputed)[0]
    contribution_values = classifier.coef_[0] * standardized
    raw_values = design.iloc[0]  # the actual (pre-imputation) values, for display

    ordered = _sorted_by_magnitude(list(design.columns), contribution_values, raw_values)
    contributions = [_placeholder_contribution(f, v, r) for f, v, r in ordered]

    baseline_log_odds = float(classifier.intercept_[0])
    prediction_log_odds = baseline_log_odds + float(contribution_values.sum())

    return Explanation(
        baseline=baseline_log_odds,
        prediction=prediction_log_odds,
        contributions=contributions,
        units=ExplanationUnits.LOG_ODDS,
        notes=_NOTES,
    )
