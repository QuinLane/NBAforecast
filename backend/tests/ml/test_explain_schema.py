"""Unit tests for the Explanation/Contribution schema (explainability.md Prompt 1 + §5)."""

import pytest
from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from pydantic import ValidationError


def _contribution(**overrides: object) -> Contribution:
    defaults: dict[str, object] = {
        "feature": "elo_diff",
        "display_label": "elo_diff",
        "raw_value": 42.0,
        "formatted_value": "42.0",
        "contribution": 0.05,
        "direction": "up",
    }
    return Contribution(**{**defaults, **overrides})


def test_contribution_accepts_valid_direction_values() -> None:
    assert _contribution(direction="up").direction == "up"
    assert _contribution(direction="down").direction == "down"


def test_contribution_rejects_invalid_direction() -> None:
    with pytest.raises(ValidationError):
        _contribution(direction="sideways")


def test_contribution_accepts_heterogeneous_raw_value_types() -> None:
    assert _contribution(raw_value=1).raw_value == 1
    assert _contribution(raw_value=1.5).raw_value == 1.5
    assert _contribution(raw_value=True).raw_value is True
    assert _contribution(raw_value="2024-01-01").raw_value == "2024-01-01"
    assert _contribution(raw_value=None).raw_value is None


def test_explanation_units_enum_values_match_spec() -> None:
    assert ExplanationUnits.PROBABILITY_POINTS == "probability_points"
    assert ExplanationUnits.LOG_ODDS == "log_odds"
    assert ExplanationUnits.POINTS == "points"
    assert ExplanationUnits.REBOUNDS == "rebounds"
    assert ExplanationUnits.ASSISTS == "assists"
    assert ExplanationUnits.THREE_POINTERS_MADE == "three_pointers_made"


def test_explanation_rejects_invalid_units() -> None:
    with pytest.raises(ValidationError):
        Explanation(
            baseline=0.5,
            prediction=0.6,
            contributions=[],
            units="not_a_real_unit",
            notes="",
        )


def test_explanation_round_trips_through_json() -> None:
    explanation = Explanation(
        baseline=0.5,
        prediction=0.62,
        contributions=[_contribution()],
        units=ExplanationUnits.PROBABILITY_POINTS,
        notes="honesty caveat",
    )
    restored = Explanation.model_validate_json(explanation.model_dump_json())
    assert restored == explanation
