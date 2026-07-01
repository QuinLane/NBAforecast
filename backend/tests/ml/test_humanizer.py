"""Unit tests for the feature humanizer (explainability.md Prompt 3 + §6).

The coverage test is the one the build prompt explicitly calls for: "a test fails if any
feature lacks one."
"""

import math

import pytest
from nbaforecast.explain.humanizer import FEATURE_REGISTRY, humanize, humanize_contribution
from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from nbaforecast.models.game_prediction.win_prob import (
    MODEL_FEATURE_COLUMNS as GAME_WIN_FEATURES,
)
from nbaforecast.models.props.regressor import MODEL_FEATURE_COLUMNS as PROPS_FEATURES

# The humanizer registry must cover every feature any batch head with a humanized explanation
# produces — game-win/margin/total (team-game features) and props (player-game features).
MODEL_FEATURE_COLUMNS = tuple({*GAME_WIN_FEATURES, *PROPS_FEATURES})


def _contribution(feature: str, raw_value: object) -> Contribution:
    return Contribution(
        feature=feature,
        display_label=feature,  # placeholder, as explainers.py produces today
        raw_value=raw_value,  # type: ignore[arg-type]
        formatted_value=str(raw_value),
        contribution=0.05,
        direction="up",
    )


# ── Coverage ─────────────────────────────────────────────────────────────────────────────────────


def test_every_model_feature_has_a_registry_entry() -> None:
    missing = set(MODEL_FEATURE_COLUMNS) - set(FEATURE_REGISTRY)
    assert missing == set(), f"missing humanizer entries: {sorted(missing)}"


def test_registry_has_no_entries_for_unknown_features() -> None:
    # Guards against the registry silently drifting ahead of MODEL_FEATURE_COLUMNS too —
    # every entry should map to a feature the model actually produces.
    extra = set(FEATURE_REGISTRY) - set(MODEL_FEATURE_COLUMNS)
    assert extra == set(), (
        f"registry entries for features the model doesn't produce: {sorted(extra)}"
    )


def test_every_registry_entry_has_non_empty_fields() -> None:
    for feature, meta in FEATURE_REGISTRY.items():
        assert meta.display_label, feature
        assert meta.description, feature
        assert meta.unit, feature
        assert callable(meta.value_formatter), feature


# ── humanize_contribution ────────────────────────────────────────────────────────────────────────


def test_humanize_contribution_sets_display_label_and_formatted_value() -> None:
    contribution = _contribution("days_rest", 2.0)
    humanized = humanize_contribution(contribution)
    assert humanized.display_label == "Days of rest"
    assert humanized.formatted_value == "2 days"


def test_humanize_contribution_singular_day() -> None:
    humanized = humanize_contribution(_contribution("days_rest", 1.0))
    assert humanized.formatted_value == "1 day"


def test_humanize_contribution_handles_missing_value() -> None:
    humanized = humanize_contribution(_contribution("days_rest", math.nan))
    assert humanized.formatted_value == "N/A"


def test_humanize_contribution_raises_for_unknown_feature() -> None:
    contribution = _contribution("not_a_real_feature", 1.0)
    with pytest.raises(RuntimeError):
        humanize_contribution(contribution)


def test_humanize_contribution_does_not_mutate_raw_value_or_contribution() -> None:
    original = _contribution("elo_diff", 42.0)
    humanized = humanize_contribution(original)
    assert humanized.raw_value == original.raw_value == 42.0
    assert humanized.contribution == original.contribution
    assert humanized.feature == original.feature


# ── Format spot checks (one per formatter family) ───────────────────────────────────────────────


def test_format_percent() -> None:
    assert humanize_contribution(_contribution("win_pct_to_date", 0.625)).formatted_value == "62%"


def test_format_signed_rating_positive_and_negative() -> None:
    assert humanize_contribution(_contribution("season_net_rating", 4.2)).formatted_value == "+4.2"
    assert humanize_contribution(_contribution("season_net_rating", -3.1)).formatted_value == "-3.1"


def test_format_boolean() -> None:
    assert humanize_contribution(_contribution("is_home", True)).formatted_value == "yes"
    assert humanize_contribution(_contribution("is_home", False)).formatted_value == "no"


def test_format_km() -> None:
    assert (
        humanize_contribution(_contribution("travel_distance_km", 3936.4)).formatted_value
        == "3936 km"
    )


def test_format_elo_signed_and_unsigned() -> None:
    assert humanize_contribution(_contribution("elo", 1523.4)).formatted_value == "1523"
    assert humanize_contribution(_contribution("elo_diff", -87.0)).formatted_value == "-87"


# ── humanize(Explanation) ────────────────────────────────────────────────────────────────────────


def test_humanize_decorates_every_contribution_in_an_explanation() -> None:
    explanation = Explanation(
        baseline=0.5,
        prediction=0.6,
        contributions=[
            _contribution("days_rest", 2.0),
            _contribution("elo_diff", 50.0),
        ],
        units=ExplanationUnits.PROBABILITY_POINTS,
        notes="",
    )
    humanized = humanize(explanation)
    assert humanized.contributions[0].display_label == "Days of rest"
    assert humanized.contributions[1].display_label == "Elo advantage"
    # Non-contribution fields pass through unchanged.
    assert humanized.baseline == explanation.baseline
    assert humanized.prediction == explanation.prediction
