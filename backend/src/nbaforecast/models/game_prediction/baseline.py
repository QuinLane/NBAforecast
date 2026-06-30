"""Game-win baselines — modeling.md §3 + Prompt 2.

The floor a real game-win model (T2.7) must clear. Both are zero-or-near-zero-parameter:
predicting the training fold's empirical home win rate, and a closed-form Elo-to-probability
conversion. Neither "trains" in the gradient-descent sense — that's the point of a baseline.
"""

from typing import Any, overload

import pandas as pd

from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from nbaforecast.models.base import ModelHead, TrainResult

# Mirrors features/team_game.py's ELO_HOME_ADVANTAGE. Kept as its own constant rather than
# imported: a baseline's calibration is deliberately independent of the feature pipeline's
# internal Elo bookkeeping — it only ever consumes the already-materialized elo_diff column.
ELO_HOME_ADVANTAGE = 100.0

_EXPLANATION_NOTES = (
    "This explanation shows which factors moved the model's own prediction, and by how much — "
    "it reflects the model's reasoning, not a causal claim about why the game was won."
)


@overload
def _elo_win_prob(score: float) -> float: ...
@overload
def _elo_win_prob(score: pd.Series) -> pd.Series: ...
def _elo_win_prob(score: float | pd.Series) -> float | pd.Series:
    """The standard base-10 logistic Elo formula, ``score`` in units of (rating diff / 400)."""
    return 1.0 / (1.0 + 10.0 ** (-score))


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

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        rate = float(model["home_win_rate"])
        return Explanation(
            baseline=rate,
            prediction=rate,
            contributions=[],  # genuinely no per-row features — the whole model is one constant
            units=ExplanationUnits.PROBABILITY_POINTS,
            notes=_EXPLANATION_NOTES,
        )


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
        win_prob = _elo_win_prob((features["elo_diff"] + home_edge) / 400.0)
        win_prob.name = "prediction"
        return win_prob

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        """Splits the closed-form formula into its two terms (rating gap, home court) via the
        same cumulative-logistic telescoping trick the TreeSHAP explainer uses (T2.10): exactly
        additive in probability-points, in magnitude order.
        """
        if len(features) != 1:
            raise ValueError("EloWinProbHead.explain explains exactly one row at a time")
        row = features.iloc[0]
        elo_diff = float(row["elo_diff"])
        is_home = bool(row["is_home"])
        home_edge = ELO_HOME_ADVANTAGE if is_home else -ELO_HOME_ADVANTAGE

        terms = [
            ("elo_diff", elo_diff / 400.0, elo_diff),
            ("is_home", home_edge / 400.0, is_home),
        ]
        terms.sort(key=lambda t: -abs(t[1]))

        baseline = _elo_win_prob(0.0)  # no rating gap, no home edge -> 50/50
        running_score = 0.0
        contributions = []
        for feature, score_term, raw_value in terms:
            prev_prob = _elo_win_prob(running_score)
            running_score += score_term
            new_prob = _elo_win_prob(running_score)
            contributions.append(
                Contribution(
                    feature=feature,
                    display_label=feature,
                    raw_value=raw_value,
                    formatted_value=str(raw_value),
                    contribution=new_prob - prev_prob,
                    direction="up" if new_prob >= prev_prob else "down",
                )
            )

        return Explanation(
            baseline=baseline,
            prediction=_elo_win_prob(running_score),
            contributions=contributions,
            units=ExplanationUnits.PROBABILITY_POINTS,
            notes=_EXPLANATION_NOTES,
        )
