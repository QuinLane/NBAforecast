"""RAPM evaluation — rapm.md Prompt 5 / §6.

RAPM has no clean supervised label, so evaluation is indirect, standard-in-the-field:

1. **Retrodiction test** (headline metric): do ratings fit on one period predict *another*
   period's game margins with lower RMSE than baselines (raw plus-minus, box plus-minus)?
2. **Cross-window stability**: correlation of a player's RAPM across two adjacent snapshot
   windows — noisy ratings bounce around; stable ones don't.
3. **Face validity**: a leaderboard report (not a metric) — the top of the list should be
   recognizable stars, a basic sanity check a metric alone can't catch.

Results are logged to MLflow via ``training/registry.py``'s conventions (one experiment per
"head" — here, the RAPM model itself).
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nbaforecast.models.rapm.fit import PlayerRapmRating

logger = logging.getLogger(__name__)

MLFLOW_EXPERIMENT_NAME = "rapm"


@dataclass(slots=True)
class RetrodictionResult:
    """RMSE of a rating source's retrodiction of held-out game margins, plus the raw predictions
    (for inspection/debugging)."""

    rapm_rmse: float
    raw_plus_minus_rmse: float | None
    box_plus_minus_rmse: float | None

    def beats_baselines(self) -> bool:
        """Whether RAPM's retrodiction RMSE is strictly lower than every available baseline."""
        candidates = (self.raw_plus_minus_rmse, self.box_plus_minus_rmse)
        baselines = [b for b in candidates if b is not None]
        return bool(baselines) and all(self.rapm_rmse < b for b in baselines)


def _team_margin_from_player_ratings(
    ratings_by_player: dict[int, float], home_player_ids: list[int], away_player_ids: list[int]
) -> float:
    """Sum individual player ratings on each side to predict a game's point margin (home minus
    away), scaled implicitly per-100-possessions — a simple, standard way to roll individual RAPM
    up to a team-level retrodiction target."""
    home_sum = sum(ratings_by_player.get(int(p), 0.0) for p in home_player_ids)
    away_sum = sum(ratings_by_player.get(int(p), 0.0) for p in away_player_ids)
    return home_sum - away_sum


def retrodiction_rmse(
    ratings: list[PlayerRapmRating],
    holdout_games: pd.DataFrame,
    *,
    raw_plus_minus: dict[int, float] | None = None,
    box_plus_minus: dict[int, float] | None = None,
) -> RetrodictionResult:
    """Score RAPM's (and, optionally, baselines') retrodiction of ``holdout_games`` margins.

    Args:
        ratings: Fitted RAPM ratings (from a period *before* ``holdout_games``).
        holdout_games: Must have ``home_player_ids, away_player_ids`` (lists of player ids on
            court, e.g. starters/rotation) and ``margin`` (actual home-minus-away point margin).
        raw_plus_minus: Optional ``player_id -> raw plus-minus`` baseline, same aggregation.
        box_plus_minus: Optional ``player_id -> box plus-minus`` baseline, same aggregation.

    Returns:
        A :class:`RetrodictionResult` with RMSE for RAPM and any baselines supplied.
    """
    rapm_by_player = {r.player_id: r.rapm for r in ratings}
    actual = holdout_games["margin"].to_numpy(dtype=float)

    def _score(ratings_by_player: dict[int, float]) -> float:
        predicted = np.array(
            [
                _team_margin_from_player_ratings(
                    ratings_by_player, record["home_player_ids"], record["away_player_ids"]
                )
                for record in holdout_games.to_dict("records")
            ]
        )
        return float(np.sqrt(np.mean((predicted - actual) ** 2)))

    rapm_rmse = _score(rapm_by_player)
    raw_pm_rmse = _score(raw_plus_minus) if raw_plus_minus else None
    box_pm_rmse = _score(box_plus_minus) if box_plus_minus else None

    return RetrodictionResult(
        rapm_rmse=rapm_rmse, raw_plus_minus_rmse=raw_pm_rmse, box_plus_minus_rmse=box_pm_rmse
    )


def cross_window_stability(
    ratings_a: list[PlayerRapmRating], ratings_b: list[PlayerRapmRating]
) -> float:
    """Pearson correlation of RAPM ratings for players present in both windows.

    Two adjacent snapshot windows sharing enough roster overlap should produce fairly correlated
    ratings (rapm.md §6) — a large drop signals an unstable fit (e.g. too small an ``alpha``).
    Returns ``nan`` if fewer than 2 players overlap (correlation undefined).
    """
    a_by_player = {r.player_id: r.rapm for r in ratings_a}
    b_by_player = {r.player_id: r.rapm for r in ratings_b}
    shared = sorted(set(a_by_player) & set(b_by_player))
    if len(shared) < 2:
        return float("nan")
    a_values = np.array([a_by_player[p] for p in shared])
    b_values = np.array([b_by_player[p] for p in shared])
    if np.std(a_values) == 0 or np.std(b_values) == 0:
        return float("nan")
    return float(np.corrcoef(a_values, b_values)[0, 1])


def leaderboard(
    ratings: list[PlayerRapmRating], *, top_n: int = 25, player_names: dict[int, str] | None = None
) -> pd.DataFrame:
    """Face-validity report (rapm.md §6): top ``top_n`` players by overall RAPM.

    Not a metric — a human-readable sanity check that the top of the list is recognizable
    talent. ``player_names`` is optional (``player_id -> display name``); when absent, the
    ``player_name`` column falls back to the raw id.
    """
    rows = sorted(ratings, key=lambda r: r.rapm, reverse=True)[:top_n]
    return pd.DataFrame(
        [
            {
                "player_id": r.player_id,
                "player_name": (player_names or {}).get(r.player_id, str(r.player_id)),
                "orapm": r.orapm,
                "drapm": r.drapm,
                "rapm": r.rapm,
            }
            for r in rows
        ]
    )


def log_evaluation_to_mlflow(
    retrodiction: RetrodictionResult,
    stability: float,
    *,
    alpha: float,
    window_seasons: int,
    extra_params: dict[str, object] | None = None,
) -> str:
    """Log the retrodiction RMSE, baseline comparison, and stability correlation to MLflow.

    Mirrors ``training/registry.py::log_run``'s conventions (one experiment, params + metrics,
    no model artifact here since RAPM's "model" is the per-player rating table rather than a
    single estimator worth serializing per evaluation run).
    """
    import mlflow

    from nbaforecast.training.registry import configure_tracking

    configure_tracking()
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
    with mlflow.start_run() as run:
        mlflow.log_params(
            {"alpha": alpha, "window_seasons": window_seasons, **(extra_params or {})}
        )
        metrics = {"retrodiction_rmse": retrodiction.rapm_rmse, "cross_window_stability": stability}
        if retrodiction.raw_plus_minus_rmse is not None:
            metrics["raw_plus_minus_rmse"] = retrodiction.raw_plus_minus_rmse
        if retrodiction.box_plus_minus_rmse is not None:
            metrics["box_plus_minus_rmse"] = retrodiction.box_plus_minus_rmse
        mlflow.log_metrics(metrics)
        logger.info(
            "RAPM eval: retrodiction_rmse=%.3f beats_baselines=%s stability=%.3f",
            retrodiction.rapm_rmse,
            retrodiction.beats_baselines(),
            stability,
        )
        return str(run.info.run_id)
