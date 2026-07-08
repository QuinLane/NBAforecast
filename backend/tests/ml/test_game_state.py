"""Game-state features for the in-game win-prob head — clock math, drops, and labels."""

from datetime import date

import pandas as pd
from nbaforecast.features.game_state import (
    build_game_state_features,
    in_game_win_labels,
    seconds_remaining,
)


def test_seconds_remaining_regulation_and_ot() -> None:
    period = pd.Series([1, 4, 5])
    left = pd.Series([720, 0, 200])
    out = seconds_remaining(period, left).tolist()
    # Q1 with 12:00 left = whole game; end of Q4 = 0; OT counts only the OT time left.
    assert out == [2880, 0, 200]


def _games() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": ["g1", "g2"],
            "game_date": [date(2025, 11, 1), date(2025, 11, 2)],
            "season_start_year": [2025, 2025],
            "home_score": [110, None],  # g2 not final yet
            "away_score": [104, None],
        }
    )


def _pbp() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": ["g1", "g1", "g1"],
            "event_num": [1, 2, 3],
            "period": [1, 4, 4],
            "seconds_remaining_period": [720, 300, None],  # last row unusable (no clock)
            "home_score": [0, 100, 100],
            "away_score": [0, 98, None],  # last row unusable (no score)
        }
    )


def test_build_drops_unusable_rows_and_computes_state() -> None:
    features = build_game_state_features(_games(), _pbp())
    assert len(features) == 2  # third pbp row dropped (missing clock/score)
    first = features.iloc[0]
    assert first["score_margin"] == 0.0
    assert first["seconds_remaining"] == 2880.0
    second = features.iloc[1]
    assert second["score_margin"] == 2.0  # 100 - 98
    assert second["seconds_remaining"] == 300.0  # 5:00 left in Q4


def test_labels_broadcast_final_outcome_and_nan_when_unfinished() -> None:
    features = build_game_state_features(_games(), _pbp())
    labels = in_game_win_labels(features, _games())
    # g1 home won (110 > 104) → 1.0 for every g1 event.
    assert set(labels.dropna()) == {1.0}
    assert len(labels) == len(features)
