"""Global SHAP explanation tests — explainability.md Prompt 4.

Assert the train-time global explanation is well-formed: mean |SHAP| importance over every
design-matrix feature, ordered by importance, with dependence data for the top features. Computed
on the shared synthetic leagues with real trained heads (no MLflow needed for the compute path).
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.models.game_prediction.win_prob import (
    MODEL_FEATURE_COLUMNS as GAME_FEATURES,
)
from nbaforecast.models.game_prediction.win_prob import LightGBMWinProbHead
from nbaforecast.models.props.regressor import MODEL_FEATURE_COLUMNS as PROPS_FEATURES
from nbaforecast.models.props.regressor import PropsRegressorHead
from nbaforecast.training.global_explanations import (
    TOP_DEPENDENCE_FEATURES,
    compute_global_explanation,
)

from tests.ml._synthetic_league import build_synthetic_league
from tests.ml._synthetic_player_league import build_synthetic_player_league


def _game_head_and_features() -> tuple[LightGBMWinProbHead, pd.DataFrame, object]:
    from nbaforecast.features.team_game import build_team_game_features

    games, team_game_stats, teams = build_synthetic_league(n_teams=6)
    features = build_team_game_features(games, team_game_stats, teams)
    outcomes = team_game_stats.merge(games[["game_id", "home_score", "away_score"]], on="game_id")
    outcomes["win"] = np.where(
        outcomes["is_home"],
        outcomes["home_score"] > outcomes["away_score"],
        outcomes["away_score"] > outcomes["home_score"],
    ).astype(float)
    labels = features.merge(outcomes[["game_id", "team_id", "win"]], on=["game_id", "team_id"])[
        "win"
    ]
    head = LightGBMWinProbHead()
    result = head.train(features, labels)
    return head, features, result.model


def _props_head_and_features() -> tuple[PropsRegressorHead, pd.DataFrame, object]:
    from nbaforecast.features.player_game import build_player_game_features

    games, team_game_stats, teams, pgs, players = build_synthetic_player_league(n_teams=6)
    features = build_player_game_features(games, pgs, team_game_stats, players)
    labels = features.merge(pgs[["game_id", "player_id", "pts"]], on=["game_id", "player_id"])[
        "pts"
    ].astype(float)
    head = PropsRegressorHead("pts")
    result = head.train(features, labels)
    return head, features, result.model


def test_game_global_importance_covers_all_features() -> None:
    head, features, model = _game_head_and_features()
    explanation = compute_global_explanation(head, model, features, feature_version="v1")
    assert set(explanation.mean_abs_shap) == set(GAME_FEATURES)
    assert all(v >= 0 for v in explanation.mean_abs_shap.values())
    assert explanation.n_samples == len(features)


def test_importance_is_sorted_descending() -> None:
    head, features, model = _game_head_and_features()
    explanation = compute_global_explanation(head, model, features, feature_version="v1")
    values = list(explanation.mean_abs_shap.values())
    assert values == sorted(values, reverse=True)


def test_dependence_data_present_for_top_features() -> None:
    head, features, model = _game_head_and_features()
    explanation = compute_global_explanation(head, model, features, feature_version="v1")
    assert len(explanation.dependence) == min(TOP_DEPENDENCE_FEATURES, len(GAME_FEATURES))
    for points in explanation.dependence.values():
        assert points  # non-empty
        assert {"value", "shap"} <= set(points[0])
    # Dependence features are the highest-importance ones.
    top = list(explanation.mean_abs_shap)[:TOP_DEPENDENCE_FEATURES]
    assert set(explanation.dependence) == set(top)


def test_props_global_importance_covers_all_features() -> None:
    head, features, model = _props_head_and_features()
    explanation = compute_global_explanation(head, model, features, feature_version="props_v1")
    assert set(explanation.mean_abs_shap) == set(PROPS_FEATURES)


def test_empty_features_raises() -> None:
    head, features, model = _game_head_and_features()
    with pytest.raises(ValueError, match="zero rows"):
        compute_global_explanation(head, model, features.iloc[:0], feature_version="v1")
