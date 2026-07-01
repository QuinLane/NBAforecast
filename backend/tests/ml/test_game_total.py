"""Unit + baseline-floor tests for the game total-points models (modeling.md Prompt 3c).

Mirrors ``test_win_prob.py``/``test_baseline_floor.py``'s fixtures and structure: a synthetic
league where ``total`` (``home_score + away_score``, identical for both teams' rows on a game)
carries genuine pace-driven signal, evaluated through the walk-forward backtest harness.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.baseline import (
    LeagueAverageTotalHead,
    TeamAverageTotalHead,
)
from nbaforecast.models.game_prediction.total import LightGBMTotalHead
from nbaforecast.models.game_prediction.win_prob import MODEL_FEATURE_COLUMNS
from nbaforecast.training.backtest import run_backtest
from nbaforecast.training.metrics import regression_metrics

from tests.ml._synthetic_league import build_synthetic_league


def _with_pace_driven_totals(
    games: pd.DataFrame, team_game_stats: pd.DataFrame, seed: int = 7
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Overlay per-team-per-season pace-driven total-points variance onto the shared synthetic
    league.

    ``_synthetic_league.py``'s scores are symmetric around 100 (``home_net``/``-home_net``), so
    ``home_score + away_score`` is a constant 200 in every game — no signal at all for a total
    model to learn, which would make every baseline/candidate here tie at MAE 0. This helper
    ties each team's scoring-pace offset (drifting season to season, mirroring how the shared
    fixture drifts skill — see its module docstring) to its already-present ``pace`` column in
    ``team_game_stats``, so the LightGBM head's ``roll{5,10}_pace``/``season_pace`` features
    actually carry the signal. The season-to-season drift matters here specifically: a *static*
    per-team pace offset would make a plain career-average lookup baseline recover it almost
    perfectly (it has nothing to track), understating what a recency-aware model like LightGBM
    actually buys over that baseline — with drift, only features that reflect *current* form
    (rolling/season-to-date pace) track the signal, the way real teams change roster/style.
    """
    rng = np.random.default_rng(seed)
    team_ids = sorted(set(games["home_team_id"]) | set(games["away_team_id"]))
    seasons = sorted(games["season_start_year"].unique())

    pace_factor: dict[tuple[int, int], float] = {}
    for team_id in team_ids:
        level = rng.normal(0, 1)
        for season in seasons:
            level += rng.normal(0, 0.6)
            pace_factor[(team_id, season)] = level

    games = games.copy()
    team_game_stats = team_game_stats.copy()
    home_factor = games.apply(
        lambda row: pace_factor[(row["home_team_id"], row["season_start_year"])], axis=1
    )
    away_factor = games.apply(
        lambda row: pace_factor[(row["away_team_id"], row["season_start_year"])], axis=1
    )
    extra_points = (home_factor + away_factor) * 10.0
    # Per-game shot-variance noise on top of the pace-driven signal — without it, a team's
    # total is a noise-free function of pace and a lookup-table baseline recovers it exactly.
    game_noise = rng.normal(0, 6, size=len(games))
    half_extra = ((extra_points + game_noise) / 2.0).round()
    games["home_score"] = games["home_score"] + half_extra
    games["away_score"] = games["away_score"] + half_extra

    # Reflect the same pace factor into team_game_stats.pace so roll/season pace features
    # (computed from this column, not from games) actually carry the signal too.
    game_season = games.set_index("game_id")["season_start_year"]
    stats_season = team_game_stats["game_id"].map(game_season)
    stats_factor = [
        pace_factor[(team_id, season)]
        for team_id, season in zip(team_game_stats["team_id"], stats_season, strict=True)
    ]
    team_game_stats["pace"] = (
        team_game_stats["pace"] + pd.Series(stats_factor, index=team_game_stats.index) * 10.0
    )
    return games, team_game_stats


def _features_and_labels(n_teams: int = 8, n_seasons: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2020, 2020 + n_seasons))
    games, team_game_stats, teams = build_synthetic_league(n_teams=n_teams, seasons=seasons)
    games, team_game_stats = _with_pace_driven_totals(games, team_game_stats)
    features = build_team_game_features(games, team_game_stats, teams)

    outcomes = team_game_stats.merge(games[["game_id", "home_score", "away_score"]], on="game_id")
    outcomes["total"] = (outcomes["home_score"] + outcomes["away_score"]).astype(float)
    merged = features.merge(
        outcomes[["game_id", "team_id", "total"]], on=["game_id", "team_id"], how="left"
    )
    return merged.drop(columns=["total"]), merged["total"]


# ── Baseline sanity ─────────────────────────────────────────────────────────────────────────────


def test_league_average_total_predicts_constant_training_mean() -> None:
    head = LeagueAverageTotalHead()
    features = pd.DataFrame({"x": [1, 2, 3]})
    labels = pd.Series([200.0, 210.0, 220.0])

    result = head.train(features, labels)
    predictions = head.predict(result.model, features)

    assert predictions.unique().tolist() == pytest.approx([210.0])


def test_team_average_total_uses_both_teams_history() -> None:
    # team_id's own per-team average: team 1 -> 210.0, team 2 -> 210.0, team 3 -> 190.0.
    features = pd.DataFrame(
        {"team_id": [1, 2, 3], "opponent_team_id": [2, 1, 1]},
    )
    labels = pd.Series([210.0, 210.0, 190.0])

    head = TeamAverageTotalHead()
    result = head.train(features, labels)

    # New matchup: team 2 (avg 210) vs team 3 (avg 190) -> predicted (210+190)/2 = 200
    prediction = head.predict(result.model, pd.DataFrame({"team_id": [2], "opponent_team_id": [3]}))
    assert prediction.iloc[0] == pytest.approx(200.0)


# ── Floor comparison ─────────────────────────────────────────────────────────────────────────────


def test_team_average_beats_league_average_floor() -> None:
    features, labels = _features_and_labels()

    team_result = run_backtest(TeamAverageTotalHead(), features, labels, regression_metrics)
    league_result = run_backtest(LeagueAverageTotalHead(), features, labels, regression_metrics)

    team_mae = float(np.mean([m["mae"] for m in team_result.fold_metrics]))
    league_mae = float(np.mean([m["mae"] for m in league_result.fold_metrics]))

    assert team_mae < league_mae


def test_lightgbm_total_head_beats_both_baselines() -> None:
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2012, 2024))
    features, labels = _features_and_labels(n_teams=14, n_seasons=len(seasons))

    league_result = run_backtest(LeagueAverageTotalHead(), features, labels, regression_metrics)
    team_result = run_backtest(TeamAverageTotalHead(), features, labels, regression_metrics)
    lgbm_result = run_backtest(LightGBMTotalHead(), features, labels, regression_metrics)

    league_mae = float(np.mean([m["mae"] for m in league_result.fold_metrics]))
    team_mae = float(np.mean([m["mae"] for m in team_result.fold_metrics]))
    lgbm_mae = float(np.mean([m["mae"] for m in lgbm_result.fold_metrics]))

    assert lgbm_mae < league_mae
    assert lgbm_mae < team_mae


# ── LightGBMTotalHead correctness ────────────────────────────────────────────────────────────────


def test_lightgbm_total_explain_returns_a_contribution_per_feature() -> None:
    features, labels = _features_and_labels()
    head = LightGBMTotalHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    assert {c.feature for c in explanation.contributions} == set(MODEL_FEATURE_COLUMNS)


def test_lightgbm_total_explain_contributions_sorted_by_magnitude() -> None:
    features, labels = _features_and_labels()
    head = LightGBMTotalHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    magnitudes = [abs(c.contribution) for c in explanation.contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_lightgbm_total_explain_is_additive() -> None:
    features, labels = _features_and_labels()
    head = LightGBMTotalHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    total = sum(c.contribution for c in explanation.contributions)
    assert total == pytest.approx(explanation.prediction - explanation.baseline, abs=1e-6)


def test_lightgbm_total_explain_prediction_matches_predict() -> None:
    features, labels = _features_and_labels()
    head = LightGBMTotalHead()
    result = head.train(features, labels)
    explanation = head.explain(result.model, features.iloc[[0]])
    predicted = head.predict(result.model, features.iloc[[0]]).iloc[0]
    assert explanation.prediction == pytest.approx(predicted, abs=1e-6)


def test_lightgbm_total_explain_rejects_multi_row_input() -> None:
    features, labels = _features_and_labels()
    head = LightGBMTotalHead()
    result = head.train(features, labels)
    with pytest.raises(ValueError, match="one row"):
        head.explain(result.model, features)
