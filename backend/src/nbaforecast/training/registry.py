"""MLflow tracking + champion/challenger promotion gate — modeling.md Prompt 6.

Wraps MLflow run logging (params, metrics, the model artifact) and the §7 promotion gate: a
challenger is promoted to champion only if it beats the current champion on the configured
primary metric by a margin and doesn't regress calibration. "No silent latest = live" — the API
(``ModelProvider``, T2.13) only ever loads whichever run carries the champion tag.

Champion tracking uses a simple ``champion`` run tag, one experiment per head (named after
``ModelHead.name``), rather than MLflow's Model Registry — the registry needs extra setup this
project doesn't use yet, and a tag is sufficient for "at most one champion run per head," since
runs are already scoped to that head's own experiment.

The model artifact is joblib-serialized rather than logged via an mlflow model flavor (e.g.
``mlflow.sklearn``) because heads wrap heterogeneous, sometimes-composite objects (an sklearn
``Pipeline``, a ``{"booster": ..., "calibrator": ...}`` dict) — one serialization path handles
all of them without per-flavor branching.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any

import joblib
import mlflow
from mlflow.entities import Run

from nbaforecast.config.settings import get_settings
from nbaforecast.models.base import ModelHead, TrainResult

logger = logging.getLogger(__name__)

CHAMPION_TAG = "champion"
MODEL_ARTIFACT_SUBPATH = "model"
MODEL_ARTIFACT_FILENAME = "model.joblib"


def configure_tracking() -> None:
    """Point the MLflow client at the configured tracking server (idempotent)."""
    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    settings.configure_mlflow_env()


def log_run(
    head: ModelHead[Any],
    train_result: TrainResult,
    *,
    lookback_seasons: int,
    extra_metrics: dict[str, float] | None = None,
    extra_params: dict[str, Any] | None = None,
) -> str:
    """Log a training run under the ``head.name`` experiment; returns the run id.

    Logs ``lookback_seasons`` and ``feature_version`` as params (plus any ``extra_params``),
    ``train_result.metrics`` merged with any ``extra_metrics`` (e.g. backtest aggregates), and
    the fitted model as a joblib artifact.
    """
    configure_tracking()
    mlflow.set_experiment(head.name)
    with mlflow.start_run() as run:
        params: dict[str, Any] = {
            "lookback_seasons": lookback_seasons,
            "feature_version": train_result.feature_version,
            **(extra_params or {}),
        }
        mlflow.log_params(params)

        metrics = {**train_result.metrics, **(extra_metrics or {})}
        if metrics:
            mlflow.log_metrics(metrics)

        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / MODEL_ARTIFACT_FILENAME
            joblib.dump(train_result.model, model_path)
            mlflow.log_artifact(str(model_path), artifact_path=MODEL_ARTIFACT_SUBPATH)

        return str(run.info.run_id)


def _experiment_id(head_name: str) -> str | None:
    experiment = mlflow.get_experiment_by_name(head_name)
    return experiment.experiment_id if experiment is not None else None


def get_champion_run(head_name: str) -> Run | None:
    """The current champion run for ``head_name``, or ``None`` if no champion exists yet."""
    configure_tracking()
    experiment_id = _experiment_id(head_name)
    if experiment_id is None:
        return None
    client = mlflow.tracking.MlflowClient()
    runs = client.search_runs([experiment_id], filter_string=f"tags.{CHAMPION_TAG} = 'true'")
    return runs[0] if runs else None


def load_champion_model(head_name: str) -> Any | None:
    """Download and deserialize the current champion's model artifact.

    Returns ``None`` if no champion has been promoted yet for this head.
    """
    champion = get_champion_run(head_name)
    if champion is None:
        return None
    client = mlflow.tracking.MlflowClient()
    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = client.download_artifacts(
            champion.info.run_id, f"{MODEL_ARTIFACT_SUBPATH}/{MODEL_ARTIFACT_FILENAME}", tmp_dir
        )
        return joblib.load(local_path)


def promote_if_better(
    head_name: str,
    challenger_run_id: str,
    *,
    metric_key: str,
    lower_is_better: bool = True,
    margin: float = 0.0,
    calibration_metric_key: str | None = None,
    calibration_max_regression: float = 0.0,
) -> bool:
    """The §7 champion/challenger gate. Returns whether the challenger was promoted.

    Promotes when no champion exists yet (the first run always becomes champion), or when the
    challenger beats the champion on ``metric_key`` by at least ``margin`` *and* — when
    ``calibration_metric_key`` is given and both runs logged it — doesn't regress calibration by
    more than ``calibration_max_regression``. Otherwise the champion is left untouched.
    """
    configure_tracking()
    client = mlflow.tracking.MlflowClient()
    challenger = client.get_run(challenger_run_id)
    champion = get_champion_run(head_name)

    if champion is None:
        client.set_tag(challenger_run_id, CHAMPION_TAG, "true")
        logger.info("no prior champion for %s; promoting %s", head_name, challenger_run_id)
        return True

    champion_metric = champion.data.metrics.get(metric_key)
    challenger_metric = challenger.data.metrics.get(metric_key)
    if champion_metric is None or challenger_metric is None:
        raise ValueError(f"metric {metric_key!r} missing from the champion or challenger run")

    improved = (
        challenger_metric <= champion_metric - margin
        if lower_is_better
        else challenger_metric >= champion_metric + margin
    )
    if not improved:
        return False

    if calibration_metric_key is not None:
        champion_calib = champion.data.metrics.get(calibration_metric_key)
        challenger_calib = challenger.data.metrics.get(calibration_metric_key)
        if champion_calib is not None and challenger_calib is not None:
            regressed = challenger_calib > champion_calib + calibration_max_regression
            if regressed:
                logger.info(
                    "%s beats %s on %s but regresses calibration; not promoting",
                    challenger_run_id,
                    head_name,
                    metric_key,
                )
                return False

    client.set_tag(champion.info.run_id, CHAMPION_TAG, "false")
    client.set_tag(challenger_run_id, CHAMPION_TAG, "true")
    logger.info(
        "promoted %s to champion for %s (was %s)",
        challenger_run_id,
        head_name,
        champion.info.run_id,
    )
    return True
