"""Unit tests for the props baselines (modeling.md §3 + Prompt 2), mirroring
``test_baseline_floor.py``'s individual-baseline sanity checks for game-win.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.models.props.baseline import LastTenGameAverageHead, SeasonAverageHead


def test_season_average_head_predicts_the_materialized_column() -> None:
    head = SeasonAverageHead("pts")
    features = pd.DataFrame({"season_avg_pts": [10.0, 20.0, np.nan]})
    labels = pd.Series([12.0, 18.0, 15.0])

    result = head.train(features, labels)
    predictions = head.predict(result.model, features)

    assert predictions.iloc[0] == 10.0
    assert predictions.iloc[1] == 20.0
    assert predictions.iloc[2] == pytest.approx(labels.mean())  # cold-start fallback


def test_last_ten_game_average_head_predicts_the_materialized_column() -> None:
    head = LastTenGameAverageHead("reb")
    features = pd.DataFrame({"roll10_reb": [5.0, 7.0, np.nan]})
    labels = pd.Series([6.0, 8.0, 4.0])

    result = head.train(features, labels)
    predictions = head.predict(result.model, features)

    assert predictions.iloc[0] == 5.0
    assert predictions.iloc[1] == 7.0
    assert predictions.iloc[2] == pytest.approx(labels.mean())


def test_unknown_stat_raises() -> None:
    with pytest.raises(ValueError, match="unknown props stat"):
        SeasonAverageHead("blocks")
    with pytest.raises(ValueError, match="unknown props stat"):
        LastTenGameAverageHead("blocks")


def test_season_average_explain_is_a_single_unattributed_value() -> None:
    head = SeasonAverageHead("ast")
    features = pd.DataFrame({"season_avg_ast": [5.0]})
    result = head.train(features, pd.Series([5.0]))
    explanation = head.explain(result.model, features)

    assert explanation.contributions == []
    assert explanation.baseline == explanation.prediction == 5.0
