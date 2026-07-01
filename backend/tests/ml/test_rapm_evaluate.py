"""Unit tests for RAPM evaluation (rapm.md Prompt 5 / §6)."""

from pathlib import Path

import pandas as pd
import pytest
from nbaforecast.models.rapm import evaluate
from nbaforecast.models.rapm.evaluate import (
    cross_window_stability,
    leaderboard,
    log_evaluation_to_mlflow,
    retrodiction_rmse,
)
from nbaforecast.models.rapm.fit import PlayerRapmRating


def _ratings(values: dict[int, tuple[float, float]]) -> list[PlayerRapmRating]:
    return [
        PlayerRapmRating(player_id=p, orapm=o, drapm=d, rapm=o + d) for p, (o, d) in values.items()
    ]


def test_retrodiction_rmse_perfect_fit_is_zero() -> None:
    # Player 1's RAPM (5.0) vs. player 2's RAPM (-5.0), padded with zero-rated players so each
    # side has 5 "on court" — predicted margin = 5.0 - (-5.0) = 10.0.
    ratings = _ratings({1: (5.0, 0.0), 2: (0.0, -5.0), 3: (0.0, 0.0), 4: (0.0, 0.0)})
    holdout = pd.DataFrame(
        [{"home_player_ids": [1, 3, 3, 3, 3], "away_player_ids": [2, 4, 4, 4, 4], "margin": 10.0}]
    )
    result = retrodiction_rmse(ratings, holdout)
    assert result.rapm_rmse == pytest.approx(0.0, abs=1e-9)


def test_retrodiction_rmse_beats_baselines_true_when_strictly_lower() -> None:
    result = evaluate.RetrodictionResult(
        rapm_rmse=1.0, raw_plus_minus_rmse=2.0, box_plus_minus_rmse=3.0
    )
    assert result.beats_baselines() is True


def test_retrodiction_rmse_beats_baselines_false_when_not_strictly_lower() -> None:
    result = evaluate.RetrodictionResult(
        rapm_rmse=2.5, raw_plus_minus_rmse=2.0, box_plus_minus_rmse=3.0
    )
    assert result.beats_baselines() is False


def test_retrodiction_rmse_beats_baselines_false_with_no_baselines() -> None:
    result = evaluate.RetrodictionResult(
        rapm_rmse=1.0, raw_plus_minus_rmse=None, box_plus_minus_rmse=None
    )
    assert result.beats_baselines() is False


def test_cross_window_stability_perfect_correlation() -> None:
    ratings_a = _ratings({1: (1.0, 1.0), 2: (2.0, 2.0), 3: (3.0, 3.0)})
    ratings_b = _ratings({1: (2.0, 2.0), 2: (4.0, 4.0), 3: (6.0, 6.0)})  # perfectly scaled
    stability = cross_window_stability(ratings_a, ratings_b)
    assert stability == pytest.approx(1.0)


def test_cross_window_stability_nan_with_insufficient_overlap() -> None:
    ratings_a = _ratings({1: (1.0, 1.0)})
    ratings_b = _ratings({1: (1.0, 1.0)})
    stability = cross_window_stability(ratings_a, ratings_b)
    assert stability != stability  # NaN != NaN


def test_leaderboard_returns_top_n_sorted_by_rapm() -> None:
    ratings = _ratings({1: (1.0, 1.0), 2: (10.0, 0.0), 3: (-5.0, -5.0)})
    board = leaderboard(ratings, top_n=2)
    assert list(board["player_id"]) == [2, 1]
    assert list(board["rapm"]) == [10.0, 2.0]


def test_leaderboard_uses_player_names_when_given() -> None:
    ratings = _ratings({1: (1.0, 1.0)})
    board = leaderboard(ratings, player_names={1: "Test Player"})
    assert board.iloc[0]["player_name"] == "Test Player"


def test_log_evaluation_to_mlflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSettings:
        mlflow_tracking_uri = f"sqlite:///{tmp_path}/mlflow.db"

        def configure_mlflow_env(self) -> None:
            pass

    monkeypatch.setattr("nbaforecast.training.registry.get_settings", lambda: FakeSettings())

    result = evaluate.RetrodictionResult(
        rapm_rmse=1.5, raw_plus_minus_rmse=2.0, box_plus_minus_rmse=2.5
    )
    run_id = log_evaluation_to_mlflow(result, 0.9, alpha=500.0, window_seasons=3)
    assert run_id
