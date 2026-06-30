"""Unit tests for MLflow tracking + the champion/challenger promotion gate (modeling.md
Prompt 6 / §7).

Uses a local sqlite-backed tracking URI (mlflow's filesystem store is deprecated for new
projects; sqlite is the standard lightweight substitute and supports everything this module
needs — runs, tags, artifacts — without a live tracking server).
"""

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from nbaforecast.models.base import ModelHead, TrainResult
from nbaforecast.training import registry


class _DummyHead(ModelHead[float]):
    @property
    def name(self) -> str:
        return "test_head"

    @property
    def feature_dependencies(self) -> tuple[str, ...]:
        return ("features_team_game",)

    def train(self, features: pd.DataFrame, labels: pd.Series) -> TrainResult:
        return TrainResult(model={"value": 1.0}, metrics={}, feature_version="v1")

    def predict(self, model: Any, features: pd.DataFrame) -> float:
        return model["value"]

    def explain(self, model: Any, features: pd.DataFrame) -> dict[str, Any]:
        return {}


@pytest.fixture(autouse=True)
def _local_tracking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSettings:
        mlflow_tracking_uri = f"sqlite:///{tmp_path}/mlflow.db"

        def configure_mlflow_env(self) -> None:
            pass

    monkeypatch.setattr("nbaforecast.training.registry.get_settings", lambda: FakeSettings())


def _log(head_name: str = "test_head", *, metric: float, model: Any = None) -> str:
    head = _DummyHead()
    train_result = TrainResult(
        model=model if model is not None else {"value": 1.0},
        metrics={"log_loss": metric},
        feature_version="v1",
    )
    return registry.log_run(head, train_result, lookback_seasons=15)


def test_log_run_records_params_and_metrics() -> None:
    run_id = _log(metric=0.5)
    client_run = registry.mlflow.tracking.MlflowClient().get_run(run_id)
    assert client_run.data.params["lookback_seasons"] == "15"
    assert client_run.data.params["feature_version"] == "v1"
    assert client_run.data.metrics["log_loss"] == 0.5


def test_get_champion_run_is_none_before_any_promotion() -> None:
    _log(metric=0.5)
    assert registry.get_champion_run("test_head") is None


def test_get_champion_run_is_none_for_unknown_head() -> None:
    assert registry.get_champion_run("never_logged_anything") is None


def test_first_run_is_always_promoted() -> None:
    run_id = _log(metric=0.9)  # a bad metric — still becomes champion, nothing to compare to
    promoted = registry.promote_if_better("test_head", run_id, metric_key="log_loss")
    assert promoted is True
    assert registry.get_champion_run("test_head").info.run_id == run_id


def test_challenger_beating_champion_by_margin_is_promoted() -> None:
    champion_run = _log(metric=0.5)
    registry.promote_if_better("test_head", champion_run, metric_key="log_loss")

    challenger_run = _log(metric=0.3)
    promoted = registry.promote_if_better(
        "test_head", challenger_run, metric_key="log_loss", margin=0.1
    )

    assert promoted is True
    assert registry.get_champion_run("test_head").info.run_id == challenger_run


def test_challenger_not_beating_margin_keeps_champion() -> None:
    champion_run = _log(metric=0.5)
    registry.promote_if_better("test_head", champion_run, metric_key="log_loss")

    challenger_run = _log(metric=0.45)  # better, but not by the required margin
    promoted = registry.promote_if_better(
        "test_head", challenger_run, metric_key="log_loss", margin=0.1
    )

    assert promoted is False
    assert registry.get_champion_run("test_head").info.run_id == champion_run


def test_worse_challenger_keeps_champion() -> None:
    champion_run = _log(metric=0.3)
    registry.promote_if_better("test_head", champion_run, metric_key="log_loss")

    challenger_run = _log(metric=0.6)
    promoted = registry.promote_if_better("test_head", challenger_run, metric_key="log_loss")

    assert promoted is False
    assert registry.get_champion_run("test_head").info.run_id == champion_run


def test_calibration_regression_blocks_an_otherwise_winning_challenger() -> None:
    head = _DummyHead()
    champion_result = TrainResult(
        model={"value": 1.0}, metrics={"log_loss": 0.5, "ece": 0.02}, feature_version="v1"
    )
    champion_run = registry.log_run(head, champion_result, lookback_seasons=15)
    registry.promote_if_better("test_head", champion_run, metric_key="log_loss")

    challenger_result = TrainResult(
        model={"value": 1.0}, metrics={"log_loss": 0.3, "ece": 0.10}, feature_version="v1"
    )
    challenger_run = registry.log_run(head, challenger_result, lookback_seasons=15)

    promoted = registry.promote_if_better(
        "test_head",
        challenger_run,
        metric_key="log_loss",
        calibration_metric_key="ece",
        calibration_max_regression=0.01,
    )

    assert promoted is False
    assert registry.get_champion_run("test_head").info.run_id == champion_run


def test_promote_if_better_raises_when_metric_key_missing() -> None:
    champion_run = _log(metric=0.5)
    registry.promote_if_better("test_head", champion_run, metric_key="log_loss")
    challenger_run = _log(metric=0.3)

    with pytest.raises(ValueError, match="missing"):
        registry.promote_if_better("test_head", challenger_run, metric_key="not_a_real_metric")


def test_load_champion_model_round_trips_the_artifact() -> None:
    run_id = _log(metric=0.5, model={"booster": "fake", "calibrator": None})
    registry.promote_if_better("test_head", run_id, metric_key="log_loss")

    loaded = registry.load_champion_model("test_head")
    assert loaded == {"booster": "fake", "calibrator": None}


def test_load_champion_model_returns_none_before_any_promotion() -> None:
    _log(metric=0.5)
    assert registry.load_champion_model("test_head") is None


def test_lower_is_better_false_promotes_higher_metric() -> None:
    champion_run = _log(metric=0.5)
    registry.promote_if_better(
        "test_head", champion_run, metric_key="log_loss", lower_is_better=False
    )

    challenger_run = _log(metric=0.8)
    promoted = registry.promote_if_better(
        "test_head", challenger_run, metric_key="log_loss", lower_is_better=False
    )

    assert promoted is True
