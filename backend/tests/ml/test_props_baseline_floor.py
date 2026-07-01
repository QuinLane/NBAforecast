"""Props baseline floor test (modeling.md Prompt 2 + Prompt 4 + §3).

Each real props regressor (T3.3) must beat its own two baselines — the player's season average
and last-10-game average — on held-out MAE via the walk-forward harness, for every stat
(PTS/REB/AST/3PM). Mirrors ``test_baseline_floor.py``'s game-win floor test.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.player_game import build_player_game_features
from nbaforecast.models.props.baseline import LastTenGameAverageHead, SeasonAverageHead
from nbaforecast.models.props.regressor import PropsRegressorHead
from nbaforecast.training.backtest import run_backtest
from nbaforecast.training.metrics import regression_metrics

from tests.ml._synthetic_player_league import build_synthetic_player_league

STATS = ("pts", "reb", "ast", "fg3m")


def _features_and_labels(
    n_teams: int = 10, n_seasons: int = 14
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2010, 2010 + n_seasons))
    games, team_game_stats, _teams, player_game_stats, players = build_synthetic_player_league(
        n_teams=n_teams, seasons=seasons
    )
    features = build_player_game_features(games, player_game_stats, team_game_stats, players)
    merged = features.merge(
        player_game_stats[["game_id", "player_id", *STATS]], on=["game_id", "player_id"], how="left"
    )
    labels = {stat: merged[stat].astype(float) for stat in STATS}
    return merged.drop(columns=list(STATS)), labels


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    return _features_and_labels()


@pytest.mark.parametrize("stat", STATS)
def test_props_regressor_beats_both_baselines_on_mae(
    data: tuple[pd.DataFrame, dict[str, pd.Series]], stat: str
) -> None:
    features, labels = data
    labels_for_stat = labels[stat]

    season_avg_result = run_backtest(
        SeasonAverageHead(stat), features, labels_for_stat, regression_metrics
    )
    last10_result = run_backtest(
        LastTenGameAverageHead(stat), features, labels_for_stat, regression_metrics
    )
    regressor_result = run_backtest(
        PropsRegressorHead(stat), features, labels_for_stat, regression_metrics
    )

    season_avg_mae = float(np.mean([m["mae"] for m in season_avg_result.fold_metrics]))
    last10_mae = float(np.mean([m["mae"] for m in last10_result.fold_metrics]))
    regressor_mae = float(np.mean([m["mae"] for m in regressor_result.fold_metrics]))

    assert regressor_mae < season_avg_mae
    assert regressor_mae < last10_mae
