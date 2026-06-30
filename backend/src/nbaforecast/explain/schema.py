"""Explanation schema — explainability.md Prompt 1 + §5.

A single typed contract every model head's explanation conforms to, so the API and frontend
render one component for all of them regardless of which head or explainer technique produced
it (TreeSHAP, a gradient-based explainer for the live NN, or RAPM's self-explaining
coefficients).
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class ExplanationUnits(StrEnum):
    """What scale ``Explanation.baseline``/``prediction``/``Contribution.contribution`` are in."""

    PROBABILITY_POINTS = "probability_points"
    LOG_ODDS = "log_odds"
    POINTS = "points"
    REBOUNDS = "rebounds"
    ASSISTS = "assists"
    THREE_POINTERS_MADE = "three_pointers_made"


class Contribution(BaseModel):
    """One feature's signed contribution to a single prediction.

    ``display_label``/``formatted_value`` are placeholders (the raw feature name and
    ``str(raw_value)``) until T2.11's humanizer decorates them — see
    ``explain/explainers.py``'s module docstring.
    """

    feature: str
    display_label: str
    raw_value: float | int | str | bool | None
    formatted_value: str
    contribution: float
    direction: Literal["up", "down"]


class Explanation(BaseModel):
    """The §5 explanation contract — every model head's ``explain()`` returns this shape.

    ``contributions`` is sorted by ``abs(contribution)`` descending (§5: "sorted by magnitude")
    so the frontend can show the top-N headline drivers with the rest expandable. Additivity
    holds in whichever ``units`` the explanation was computed in:
    ``sum(c.contribution for c in contributions) == prediction - baseline`` (T2.12 verifies this
    for the SHAP path within floating-point tolerance).
    """

    baseline: float
    prediction: float
    contributions: list[Contribution]
    units: ExplanationUnits
    notes: str
