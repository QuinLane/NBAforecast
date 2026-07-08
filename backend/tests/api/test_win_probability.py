"""Unit tests for the in-game win-probability timeline helpers (services/games.py).

The HTTP path is verified end-to-end against the live stack; here we pin the pure logic: the
clock/value formatting and the per-moment driver math (prob-point telescoping + additivity).
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.api.services.games import (
    _clock,
    _format_feature,
    _win_prob_drivers,
)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def test_clock_formats_minutes_seconds() -> None:
    assert _clock(300.0) == "5:00"
    assert _clock(68.0) == "1:08"
    assert _clock(0.0) == "0:00"
    assert _clock(None) == ""


def test_format_feature() -> None:
    assert _format_feature("score_margin", 6) == "+6"
    assert _format_feature("score_margin", -4) == "-4"
    assert _format_feature("period", 4) == "Q4"
    assert _format_feature("period", 5) == "OT1"
    assert _format_feature("seconds_remaining", 130) == "2:10 left"


def test_win_prob_drivers_sorted_and_additive() -> None:
    columns = ["score_margin", "seconds_remaining", "period"]
    shap_row = np.array([1.0, -0.2, 0.05])  # log-odds contributions
    feature_row = pd.Series({"score_margin": 6.0, "seconds_remaining": 300.0, "period": 4.0})
    baseline = 0.0

    drivers = _win_prob_drivers(shap_row, columns, feature_row, baseline)

    # Sorted by |contribution| descending → score margin leads.
    assert [d.label for d in drivers] == ["Score margin", "Time remaining", "Period"]
    assert drivers[0].value == "+6"
    assert drivers[0].direction == "up"
    # Telescoping preserves additivity: sum of prob-point contributions == prediction - baseline.
    expected = _sigmoid(baseline + float(shap_row.sum())) - _sigmoid(baseline)
    assert sum(d.contribution for d in drivers) == pytest.approx(expected, abs=1e-9)
