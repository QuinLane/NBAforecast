"""Tests for the training driver (``entrypoints/train.py``, T3.14).

Runs the real train→backtest→log→promote path against the synthetic league with a local
sqlite MLflow store — the same trip the CLI makes against Postgres data, minus the DB load.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from nbaforecast.entrypoints.train import game_labels, train_and_promote
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.training import registry

from tests.ml._synthetic_league import build_synthetic_league


@pytest.fixture(autouse=True)
def _local_tracking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSettings:
        mlflow_tracking_uri = f"sqlite:///{tmp_path}/mlflow.db"

        def configure_mlflow_env(self) -> None:
            pass

    monkeypatch.setattr("nbaforecast.training.registry.get_settings", lambda: FakeSettings())


def _league() -> tuple[pd.DataFrame, pd.DataFrame]:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2020, 2023))
    games, team_game_stats, teams = build_synthetic_league(n_teams=6, seasons=seasons)
    features = build_team_game_features(games, team_game_stats, teams)
    outcomes = team_game_stats.merge(games[["game_id", "home_score", "away_score"]], on="game_id")
    return features, outcomes


def test_game_labels_match_head_test_convention() -> None:
    features, outcomes = _league()
    labels = game_labels(features, outcomes)

    assert set(labels) == {"game_win", "game_margin", "game_total"}
    for series in labels.values():
        assert series.index.equals(features.index)

    # Cross-check one game against the raw scores from both team perspectives.
    game_id = features["game_id"].iloc[0]
    game_rows = features.loc[features["game_id"] == game_id]
    outcome = outcomes.loc[outcomes["game_id"] == game_id].iloc[0]
    home_margin = float(outcome["home_score"] - outcome["away_score"])
    margins = labels["game_margin"].loc[game_rows.index]
    assert set(np.round(margins, 6)) == {home_margin, -home_margin}
    wins = labels["game_win"].loc[game_rows.index]
    assert sorted(wins) == [0.0, 1.0]
    totals = labels["game_total"].loc[game_rows.index]
    assert (totals == float(outcome["home_score"] + outcome["away_score"])).all()


def test_train_and_promote_creates_champion_with_backtest_metrics() -> None:
    features, outcomes = _league()
    labels = game_labels(features, outcomes)

    run_id = train_and_promote("game_win", features, labels["game_win"], lookback_seasons=2)

    champion = registry.get_champion_run("game_win")
    assert champion is not None
    assert champion.info.run_id == run_id
    assert "backtest_log_loss" in champion.data.metrics
    assert champion.data.params["train_seasons"] == "2021,2022"

    # The logged artifact must round-trip into a model the head can predict with.
    model = registry.load_champion_model("game_win")
    assert model is not None

    # A second, identical run ties on the gate metric — the registry's `<=` deliberately
    # hands ties to the challenger (on equal quality the fresher model serves), and exactly
    # one champion remains tagged.
    second_run_id = train_and_promote("game_win", features, labels["game_win"], lookback_seasons=2)
    champion_after = registry.get_champion_run("game_win")
    assert champion_after is not None
    assert second_run_id != run_id
    assert champion_after.info.run_id == second_run_id
