"""Unit tests for the ModelHead interface (roadmap.md §1)."""

from typing import Any

import pandas as pd
import pytest
from nbaforecast.models.base import ModelHead, TrainResult


def test_model_head_is_not_directly_instantiable() -> None:
    with pytest.raises(TypeError):
        ModelHead()  # type: ignore[abstract]


def test_subclass_missing_a_method_cannot_be_instantiated() -> None:
    class Incomplete(ModelHead[float]):
        @property
        def name(self) -> str:
            return "incomplete"

        @property
        def feature_dependencies(self) -> tuple[str, ...]:
            return ("features_team_game",)

        def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
            return TrainResult(model=None, metrics={}, feature_version="v1")

        # predict/explain deliberately omitted

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


class MeanPredictorHead(ModelHead[float]):
    """A trivial concrete head for testing: predicts the training label mean."""

    @property
    def name(self) -> str:
        return "mean_predictor"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(model={"mean": float(labels.mean())}, metrics={}, feature_version="v1")

    def predict(self, model: Any, features: pd.DataFrame) -> pd.Series:
        return pd.Series([model["mean"]] * len(features), index=features.index)

    def explain(self, model: Any, features: pd.DataFrame) -> dict[str, Any]:
        return {"baseline": model["mean"], "contributions": {}}


def test_concrete_head_train_does_not_mutate_self() -> None:
    head = MeanPredictorHead()
    features = pd.DataFrame({"x": [1, 2, 3]})
    labels = pd.Series([10.0, 20.0, 30.0])

    result = head.train(features, labels)

    assert result.model == {"mean": 20.0}
    assert not hasattr(head, "_model")  # no fitted state leaked onto the head instance


def test_concrete_head_predict_uses_passed_in_model_not_shared_state() -> None:
    head = MeanPredictorHead()
    features = pd.DataFrame({"x": [1, 2]})

    result_a = head.train(features, pd.Series([0.0, 0.0]))
    result_b = head.train(features, pd.Series([100.0, 100.0]))

    # The same head instance, used for two different fits, must not let the second fit's state
    # bleed into predictions made against the first fit's result (this is what makes a single
    # ModelHead instance safe to reuse across walk-forward folds).
    assert head.predict(result_a.model, features).iloc[0] == 0.0
    assert head.predict(result_b.model, features).iloc[0] == 100.0


def test_explain_returns_dict_with_baseline_and_contributions() -> None:
    head = MeanPredictorHead()
    result = head.train(pd.DataFrame({"x": [1]}), pd.Series([5.0]))
    explanation = head.explain(result.model, pd.DataFrame({"x": [1]}))
    assert explanation["baseline"] == 5.0
    assert "contributions" in explanation
