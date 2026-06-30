"""Game-win baselines — modeling.md §3 + Prompt 2.

The floor a real game-win model (T2.7) must clear. Both are zero-or-near-zero-parameter:
predicting the training fold's empirical home win rate, and a closed-form Elo-to-probability
conversion. Neither "trains" in the gradient-descent sense — that's the point of a baseline.
"""

from typing import Any

import pandas as pd

from nbaforecast.models.base import ModelHead, TrainResult

# Mirrors features/team_game.py's ELO_HOME_ADVANTAGE. Kept as its own constant rather than
# imported: a baseline's calibration is deliberately independent of the feature pipeline's
# internal Elo bookkeeping — it only ever consumes the already-materialized elo_diff column.
ELO_HOME_ADVANTAGE = 100.0


class HomeAlwaysWinsHead(ModelHead[pd.Series]):
    """Predicts the training fold's empirical home win rate for every row, ignoring features.

    The textbook probabilistic floor: "home team always wins" (~57-60% historically) expressed
    as a constant probability rather than a hard 100% call, so it scores on log-loss like any
    other head instead of producing an undefined loss whenever the home team loses.
    """

    @property
    def name(self) -> str:
        return "game_win_baseline_home_always_wins"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(
            model={"home_win_rate": float(labels.mean())}, metrics={}, feature_version="baseline"
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        return pd.Series([model["home_win_rate"]] * len(features), index=features.index)

    def explain(self, model: Any, features: pd.DataFrame) -> dict[str, Any]:
        return {"baseline": model["home_win_rate"], "contributions": {}}


class EloWinProbHead(ModelHead[pd.Series]):
    """Closed-form Elo win probability from the already-materialized elo_diff/is_home features.

    No fitting: the standard logistic Elo formula, home-court adjusted, applied directly to each
    row's own elo_diff ("self minus opponent" — see features/team_game.py) — "a plain Elo model"
    per modeling.md §3.
    """

    @property
    def name(self) -> str:
        return "game_win_baseline_elo"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(model={}, metrics={}, feature_version="baseline")

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        home_edge = features["is_home"].map({True: ELO_HOME_ADVANTAGE, False: -ELO_HOME_ADVANTAGE})
        exponent = -(features["elo_diff"] + home_edge) / 400.0
        win_prob = 1.0 / (1.0 + 10.0**exponent)
        win_prob.name = "prediction"
        return win_prob

    def explain(self, model: Any, features: pd.DataFrame) -> dict[str, Any]:
        return {"contributions": {"elo_diff": features["elo_diff"].to_dict()}}
