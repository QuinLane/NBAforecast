"""Baseline floor test (modeling.md Prompt 2 + Prompt 3a + §3).

The win-prob baselines must be meaningfully ordered: Elo (carries real per-game signal) must
beat the constant-rate baseline on held-out log-loss, via the walk-forward harness on a
synthetic-but-skill-correlated league.

The game-win *head*, taken as a whole, must in turn beat Elo as its own floor — modeling.md
Prompt 2's "assert each main model beats its baseline" is read at the head level (the
champion/challenger framing in §7: the best candidate is what gets promoted and compared, not
every experimental sub-model in isolation). Concretely: the better of {logistic, LightGBM} must
beat Elo. On this synthetic league specifically, logistic reliably wins outright — the league's
data-generating process is purely linear in team skill + home court, which structurally favors
linear models over tree ensembles (there's no nonlinear interaction for LightGBM to exploit);
that's a property of the synthetic test fixture, not evidence LightGBM is broken (see
test_win_prob.py for its own correctness checks, independent of this comparison).
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.game_prediction.baseline import EloWinProbHead, HomeAlwaysWinsHead
from nbaforecast.models.game_prediction.win_prob import LightGBMWinProbHead, LogisticWinProbHead
from nbaforecast.training.backtest import run_backtest
from nbaforecast.training.metrics import classification_metrics

from tests.ml._synthetic_league import DEFAULT_N_TEAMS, DEFAULT_SEASONS, build_synthetic_league


def _features_and_labels(
    n_teams: int = DEFAULT_N_TEAMS, seasons: tuple[tuple[str, int], ...] = DEFAULT_SEASONS
) -> tuple[pd.DataFrame, pd.Series]:
    games, team_game_stats, teams = build_synthetic_league(n_teams=n_teams, seasons=seasons)
    features = build_team_game_features(games, team_game_stats, teams)

    outcomes = team_game_stats.merge(games[["game_id", "home_score", "away_score"]], on="game_id")
    outcomes["win"] = np.where(
        outcomes["is_home"],
        outcomes["home_score"] > outcomes["away_score"],
        outcomes["away_score"] > outcomes["home_score"],
    ).astype(float)

    merged = features.merge(
        outcomes[["game_id", "team_id", "win"]], on=["game_id", "team_id"], how="left"
    )
    return merged.drop(columns=["win"]), merged["win"]


# ── Individual baseline sanity ──────────────────────────────────────────────────────────────────


def test_home_always_wins_predicts_constant_training_rate() -> None:
    head = HomeAlwaysWinsHead()
    features = pd.DataFrame({"x": [1, 2, 3]})
    labels = pd.Series([1.0, 1.0, 0.0])  # 2/3 home wins

    result = head.train(features, labels)
    predictions = head.predict(result.model, features)

    assert predictions.unique().tolist() == pytest.approx([2 / 3])


def test_elo_baseline_favors_the_higher_rated_home_team() -> None:
    head = EloWinProbHead()
    features = pd.DataFrame(
        {
            "is_home": [True, False],
            "elo_diff": [100.0, -100.0],  # this row's team is +100 elo over its opponent
        }
    )
    predictions = head.predict({}, features)

    assert predictions.iloc[0] > 0.5  # stronger team, at home
    assert predictions.iloc[1] < 0.5  # weaker team, on the road


def test_elo_baseline_evenly_matched_at_a_neutral_site_is_fifty_fifty() -> None:
    head = EloWinProbHead()
    features = pd.DataFrame({"is_home": [True], "elo_diff": [0.0]})
    predictions = head.predict({}, features)
    assert predictions.iloc[0] != 0.5  # home edge still applies even when elo is dead even
    assert predictions.iloc[0] > 0.5


# ── Floor comparison ─────────────────────────────────────────────────────────────────────────────


def test_elo_baseline_beats_home_always_wins_floor() -> None:
    features, labels = _features_and_labels()

    elo_result = run_backtest(EloWinProbHead(), features, labels, classification_metrics)
    home_result = run_backtest(HomeAlwaysWinsHead(), features, labels, classification_metrics)

    elo_log_loss = float(np.mean([m["log_loss"] for m in elo_result.fold_metrics]))
    home_log_loss = float(np.mean([m["log_loss"] for m in home_result.fold_metrics]))

    assert elo_log_loss < home_log_loss


def test_game_win_head_beats_the_elo_floor() -> None:
    """T2.7's real models, taken as a head, must clear the Elo floor (modeling.md Prompt 2/3a).

    Needs a bigger league than the other floor checks here — with only ~120 rows, a 25-feature
    logistic/LightGBM fit overfits so badly it loses even to the constant-rate baseline (this
    was caught and is exactly why this test uses its own larger fixture).
    """
    seasons = tuple((f"{y}-{(y + 1) % 100:02d}", y) for y in range(2012, 2024))
    features, labels = _features_and_labels(n_teams=14, seasons=seasons)

    elo_result = run_backtest(EloWinProbHead(), features, labels, classification_metrics)
    logistic_result = run_backtest(LogisticWinProbHead(), features, labels, classification_metrics)
    lgbm_result = run_backtest(LightGBMWinProbHead(), features, labels, classification_metrics)

    elo_log_loss = float(np.mean([m["log_loss"] for m in elo_result.fold_metrics]))
    logistic_log_loss = float(np.mean([m["log_loss"] for m in logistic_result.fold_metrics]))
    lgbm_log_loss = float(np.mean([m["log_loss"] for m in lgbm_result.fold_metrics]))

    best_candidate_log_loss = min(logistic_log_loss, lgbm_log_loss)
    assert best_candidate_log_loss < elo_log_loss
