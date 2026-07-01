"""Game-win/margin/total baselines — modeling.md §3 + Prompt 2/3b/3c.

The floor a real game-win model (T2.7) — and the T3.1 margin/total regressors — must clear.
All are zero-or-near-zero-parameter: predicting the training fold's empirical home win rate, a
closed-form Elo-to-probability conversion, a constant home-court margin, a rating-difference
linear fit, and the league/team-average total. None "trains" in the gradient-descent sense —
that's the point of a baseline.
"""

from typing import Any, overload

import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline

from nbaforecast.explain.schema import Contribution, Explanation, ExplanationUnits
from nbaforecast.models.base import ModelHead, TrainResult

# Mirrors features/team_game.py's ELO_HOME_ADVANTAGE. Kept as its own constant rather than
# imported: a baseline's calibration is deliberately independent of the feature pipeline's
# internal Elo bookkeeping — it only ever consumes the already-materialized elo_diff column.
ELO_HOME_ADVANTAGE = 100.0

# modeling.md §3: "constant home-court edge (~+2.5)" — the margin baseline's fixed prediction.
CONSTANT_HOME_COURT_MARGIN = 2.5

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


class ConstantHomeCourtMarginHead(ModelHead[pd.Series]):
    """Predicts a fixed home-court margin for every row, ignoring features and labels alike.

    The textbook margin floor per modeling.md §3: a home row always gets
    ``+CONSTANT_HOME_COURT_MARGIN``, an away row the same figure negated — margin here is
    self-relative (``team_score - opponent_score``, see ``features/team_game.py``), so an away
    team's "home-court edge" is a road disadvantage of the same magnitude.
    """

    @property
    def name(self) -> str:
        return "game_margin_baseline_constant_home_court"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(model={}, metrics={}, feature_version="baseline")

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        margin = features["is_home"].map(
            {True: CONSTANT_HOME_COURT_MARGIN, False: -CONSTANT_HOME_COURT_MARGIN}
        )
        margin.name = "prediction"
        return margin

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        if len(features) != 1:
            raise ValueError(
                "ConstantHomeCourtMarginHead.explain explains exactly one row at a time"
            )
        is_home = bool(features.iloc[0]["is_home"])
        margin = CONSTANT_HOME_COURT_MARGIN if is_home else -CONSTANT_HOME_COURT_MARGIN
        return Explanation(
            baseline=0.0,
            prediction=margin,
            contributions=[
                Contribution(
                    feature="is_home",
                    display_label="is_home",
                    raw_value=is_home,
                    formatted_value=str(is_home),
                    contribution=margin,
                    direction="up" if margin >= 0 else "down",
                )
            ],
            units=ExplanationUnits.POINTS,
            notes=_EXPLANATION_NOTES,
        )


class RatingDiffMarginHead(ModelHead[pd.Series]):
    """Linear fit of margin on ``rating_diff`` (+ ``is_home``) — the "rating-difference linear
    fit" margin baseline (modeling.md §3), one notch above the constant-margin floor.

    Ordinary least squares on two columns, median-imputed the same way
    ``LogisticWinProbHead`` imputes its design matrix: a team's very first game of a season has
    no prior ``rating_diff`` yet (see ``features/team_game.py``'s expanding season-to-date
    aggregates), and OLS can't fit through a NaN. No regularization or scaling needed at this
    scale — it's meant to be a simple, fully transparent step up from the constant baseline, not
    a competitor to the LightGBM regressor in ``margin.py``.
    """

    _COLUMNS = ("rating_diff", "is_home")

    def _design(self, features: pd.DataFrame) -> pd.DataFrame:
        design = features[list(self._COLUMNS)].copy()
        design["is_home"] = design["is_home"].astype(float)
        return design

    @property
    def name(self) -> str:
        return "game_margin_baseline_rating_diff"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        pipeline = make_pipeline(SimpleImputer(strategy="median"), LinearRegression())
        pipeline.fit(self._design(features), labels)
        return TrainResult(model=pipeline, metrics={}, feature_version="baseline")

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        predictions = model.predict(self._design(features))
        return pd.Series(predictions, index=features.index, name="prediction")

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        if len(features) != 1:
            raise ValueError("RatingDiffMarginHead.explain explains exactly one row at a time")
        design = self._design(features)
        imputer = model.named_steps["simpleimputer"]
        regressor = model.named_steps["linearregression"]

        imputed_values = imputer.transform(design)[0]
        raw_values = design.iloc[0]  # the actual (pre-imputation) values, for display
        coefficients = regressor.coef_
        contribution_values = coefficients * imputed_values

        order = sorted(range(len(self._COLUMNS)), key=lambda i: -abs(contribution_values[i]))
        contributions = [
            Contribution(
                feature=self._COLUMNS[i],
                display_label=self._COLUMNS[i],
                raw_value=raw_values.iloc[i],
                formatted_value=str(raw_values.iloc[i]),
                contribution=float(contribution_values[i]),
                direction="up" if contribution_values[i] >= 0 else "down",
            )
            for i in order
        ]

        baseline = float(regressor.intercept_)
        return Explanation(
            baseline=baseline,
            prediction=baseline + float(contribution_values.sum()),
            contributions=contributions,
            units=ExplanationUnits.POINTS,
            notes=_EXPLANATION_NOTES,
        )


class LeagueAverageTotalHead(ModelHead[pd.Series]):
    """Predicts the training fold's league-average total for every row, ignoring features.

    The first modeling.md §3 total baseline: "league-average total."
    """

    @property
    def name(self) -> str:
        return "game_total_baseline_league_average"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(
            model={"league_avg_total": float(labels.mean())},
            metrics={},
            feature_version="baseline",
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        return pd.Series(
            [model["league_avg_total"]] * len(features), index=features.index, name="prediction"
        )

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        total = float(model["league_avg_total"])
        return Explanation(
            baseline=total,
            prediction=total,
            contributions=[],  # genuinely no per-row features — the whole model is one constant
            units=ExplanationUnits.POINTS,
            notes=_EXPLANATION_NOTES,
        )


class TeamAverageTotalHead(ModelHead[pd.Series]):
    """Predicts the mean of the two teams' own historical average total points.

    A single per-team lookup (each team's average *game total* across the rows where it's
    ``team_id``, i.e. from its own perspective) fit at train time, applied to both this row's
    ``team_id`` and its ``opponent_team_id`` — since every team appears as ``team_id`` on its
    own rows, the same table answers "what does this opponent's own scoring environment usually
    look like" too, without needing a second groupby. The second modeling.md §3 total baseline:
    "the two teams' average totals."
    """

    @property
    def name(self) -> str:
        return "game_total_baseline_team_average"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        per_team_avg = labels.groupby(features["team_id"]).mean()
        league_avg_total = float(labels.mean())
        return TrainResult(
            model={"per_team_avg": per_team_avg, "league_avg_total": league_avg_total},
            metrics={},
            feature_version="baseline",
        )

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        league_avg = model["league_avg_total"]
        per_team_avg = model["per_team_avg"]
        team_avg = features["team_id"].map(per_team_avg).fillna(league_avg)
        opponent_avg = features["opponent_team_id"].map(per_team_avg).fillna(league_avg)
        predictions = (team_avg + opponent_avg) / 2.0
        predictions.name = "prediction"
        return predictions

    def explain(self, model: Any, features: pd.DataFrame) -> Explanation:
        if len(features) != 1:
            raise ValueError("TeamAverageTotalHead.explain explains exactly one row at a time")
        row = features.iloc[0]
        league_avg = float(model["league_avg_total"])
        per_team_avg = model["per_team_avg"]
        team_avg = float(per_team_avg.get(row["team_id"], league_avg))
        opponent_avg = float(per_team_avg.get(row["opponent_team_id"], league_avg))

        terms = [
            ("team_avg_total", (team_avg - league_avg) / 2.0, team_avg),
            ("opponent_avg_total", (opponent_avg - league_avg) / 2.0, opponent_avg),
        ]
        terms.sort(key=lambda t: -abs(t[1]))
        contributions = [
            Contribution(
                feature=feature,
                display_label=feature,
                raw_value=raw_value,
                formatted_value=str(raw_value),
                contribution=value,
                direction="up" if value >= 0 else "down",
            )
            for feature, value, raw_value in terms
        ]

        return Explanation(
            baseline=league_avg,
            prediction=league_avg + sum(value for _, value, _ in terms),
            contributions=contributions,
            units=ExplanationUnits.POINTS,
            notes=_EXPLANATION_NOTES,
        )
