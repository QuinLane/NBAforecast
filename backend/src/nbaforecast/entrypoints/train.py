"""CLI entrypoint to train heads on the real backfilled data and promote champions (T3.14).

For each requested head: walk-forward backtest (honest out-of-sample metrics), a final fit on
the trailing ``--lookback-seasons`` window, an MLflow run (params + backtest metrics + model +
global SHAP artifact), then the champion/challenger promotion gate. Labels are constructed with
the same per-team-perspective convention the heads were built against (see
``tests/ml/test_win_prob.py``); features come from the same builders the API serves with, so
train/serve parity holds by construction.

Examples:
    nbaforecast-train                                  # every registered head
    nbaforecast-train --heads game_win game_margin
    nbaforecast-train --lookback-seasons 5
    nbaforecast-train --rapm-snapshots                 # also build historical player_rapm

Prerequisites: the local stack is up (``docker compose up``), migrations are applied, and the
backfill has landed games (plus player stats for props heads, possessions for RAPM).
"""

import argparse
import asyncio
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nbaforecast.config.settings import get_settings
from nbaforecast.features.player_game import build_player_game_features
from nbaforecast.features.team_game import build_team_game_features
from nbaforecast.models.heads import HEAD_REGISTRY, PROPS_STATS
from nbaforecast.models.rapm.snapshots import (
    DEFAULT_WINDOW_SEASONS,
    compute_snapshot,
    snapshot_dates,
    snapshot_to_dataframe,
    upsert_player_rapm,
    write_player_rapm_parquet,
)
from nbaforecast.storage.database import get_sessionmaker
from nbaforecast.storage.models import (
    Game,
    Player,
    PlayerGameStats,
    Possession,
    Team,
    TeamGameStats,
)
from nbaforecast.storage.repositories import load_table_as_dataframe
from nbaforecast.training import registry
from nbaforecast.training.backtest import run_backtest
from nbaforecast.training.global_explanations import log_global_explanation
from nbaforecast.training.metrics import classification_metrics, regression_metrics

logger = logging.getLogger(__name__)

GAME_HEADS: tuple[str, ...] = ("game_win", "game_margin", "game_total")
BACKTEST_METRIC_PREFIX = "backtest_"


@dataclass(slots=True, frozen=True)
class PromotionGate:
    """Per-head promotion config for ``registry.promote_if_better`` (all metrics lower-better)."""

    metric_key: str
    calibration_metric_key: str | None = None


# game_win gates on out-of-sample log-loss and refuses calibration (Brier) regressions;
# the regressor heads (margin/total/props) gate on out-of-sample MAE.
PROMOTION_GATES: dict[str, PromotionGate] = {
    "game_win": PromotionGate("backtest_log_loss", calibration_metric_key="backtest_brier_score"),
    "game_margin": PromotionGate("backtest_mae"),
    "game_total": PromotionGate("backtest_mae"),
    **{f"props_{stat}": PromotionGate("backtest_mae") for stat in PROPS_STATS},
}


def game_labels(features: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, pd.Series]:
    """Per-team-perspective labels aligned to ``features``' index, one series per game head.

    ``outcomes`` is ``team_game_stats`` merged with the games' final scores; each feature row's
    label is from *that team's* perspective (its win, its margin) — the convention every game
    head was trained against in tests, with serving predicting the home row.
    """
    outcomes = outcomes.assign(
        win=np.where(
            outcomes["is_home"],
            outcomes["home_score"] > outcomes["away_score"],
            outcomes["away_score"] > outcomes["home_score"],
        ).astype(float),
        margin=np.where(
            outcomes["is_home"],
            outcomes["home_score"] - outcomes["away_score"],
            outcomes["away_score"] - outcomes["home_score"],
        ).astype(float),
        total=(outcomes["home_score"] + outcomes["away_score"]).astype(float),
    )
    merged = features[["game_id", "team_id"]].merge(
        outcomes[["game_id", "team_id", "win", "margin", "total"]],
        on=["game_id", "team_id"],
        how="left",
    )
    merged.index = features.index
    return {
        "game_win": merged["win"],
        "game_margin": merged["margin"],
        "game_total": merged["total"],
    }


def _aggregate_fold_metrics(fold_metrics: tuple[dict[str, float], ...]) -> dict[str, float]:
    """Mean of each metric across walk-forward folds, prefixed ``backtest_``."""
    frame = pd.DataFrame(list(fold_metrics))
    if frame.empty:
        return {}
    return {f"{BACKTEST_METRIC_PREFIX}{key}": float(value) for key, value in frame.mean().items()}


def train_and_promote(
    head_name: str,
    features: pd.DataFrame,
    labels: pd.Series,
    *,
    lookback_seasons: int,
) -> str:
    """Backtest, final-fit, log, and gate one head. Returns the MLflow run id."""
    head = HEAD_REGISTRY[head_name]
    gate = PROMOTION_GATES[head_name]
    metric_fn = classification_metrics if head_name == "game_win" else regression_metrics

    labeled = labels.notna()
    features, labels = features.loc[labeled], labels.loc[labeled]
    if features.empty:
        raise ValueError(f"no labeled training rows for head {head_name!r} — backfill first?")

    backtest = run_backtest(head, features, labels, metric_fn, lookback_seasons=lookback_seasons)
    backtest_metrics = _aggregate_fold_metrics(backtest.fold_metrics)
    if not backtest_metrics:
        logger.warning(
            "%s: only one season of data — no walk-forward folds, no backtest metrics", head_name
        )

    seasons = sorted(set(features["season_start_year"]))
    train_seasons = seasons[-lookback_seasons:]
    train_mask = features["season_start_year"].isin(train_seasons)
    result = head.train(features.loc[train_mask], labels.loc[train_mask])

    run_id = registry.log_run(
        head,
        result,
        lookback_seasons=lookback_seasons,
        extra_metrics=backtest_metrics,
        extra_params={"train_seasons": ",".join(str(season) for season in train_seasons)},
    )
    log_global_explanation(
        run_id, head, result.model, features.loc[train_mask], feature_version=result.feature_version
    )

    try:
        promoted = registry.promote_if_better(
            head.name,
            run_id,
            metric_key=gate.metric_key,
            lower_is_better=True,
            calibration_metric_key=gate.calibration_metric_key,
        )
    except ValueError:
        # A champion exists but one side is missing the gate metric (e.g. a single-season run
        # with no folds) — keep the incumbent rather than promoting blind.
        logger.warning("%s: promotion gate metric missing; keeping current champion", head_name)
        promoted = False

    logger.info(
        "%s: run %s over seasons %s-%s (%d rows) — %s",
        head_name,
        run_id,
        train_seasons[0],
        train_seasons[-1],
        int(train_mask.sum()),
        "PROMOTED to champion" if promoted else "champion unchanged",
    )
    return run_id


async def train_game_heads(head_names: list[str], *, lookback_seasons: int) -> None:
    """Train/gate the game heads off one shared feature build."""
    async with get_sessionmaker()() as session:
        games = await load_table_as_dataframe(session, Game)
        team_game_stats = await load_table_as_dataframe(session, TeamGameStats)
        teams = await load_table_as_dataframe(session, Team)

    features = build_team_game_features(games, team_game_stats, teams)
    outcomes = team_game_stats.merge(games[["game_id", "home_score", "away_score"]], on="game_id")
    labels = game_labels(features, outcomes)
    for head_name in head_names:
        train_and_promote(head_name, features, labels[head_name], lookback_seasons=lookback_seasons)


async def train_props_heads(head_names: list[str], *, lookback_seasons: int) -> None:
    """Train/gate the props heads off one shared player-game feature build."""
    async with get_sessionmaker()() as session:
        games = await load_table_as_dataframe(session, Game)
        player_game_stats = await load_table_as_dataframe(session, PlayerGameStats)
        team_game_stats = await load_table_as_dataframe(session, TeamGameStats)
        players = await load_table_as_dataframe(session, Player)

    features = build_player_game_features(games, player_game_stats, team_game_stats, players)
    for head_name in head_names:
        stat = head_name.removeprefix("props_")
        merged = features[["game_id", "player_id"]].merge(
            player_game_stats[["game_id", "player_id", stat]],
            on=["game_id", "player_id"],
            how="left",
        )
        merged.index = features.index
        train_and_promote(
            head_name, features, merged[stat].astype(float), lookback_seasons=lookback_seasons
        )


async def build_rapm_snapshots(*, window_seasons: int, monthly: bool) -> int:
    """Compute + persist the historical ``player_rapm`` snapshot cadence over all landed games.

    Season-end snapshots by default; ``monthly`` adds month-start snapshots (much slower over a
    long era — each snapshot is a full ridge fit with λ cross-validation).
    """
    async with get_sessionmaker()() as session:
        games = await load_table_as_dataframe(session, Game)
        possessions = await load_table_as_dataframe(session, Possession)

        total_rows = 0
        dates = snapshot_dates(games, monthly=monthly)
        logger.info("building %d RAPM snapshots (monthly=%s)", len(dates), monthly)
        for as_of in dates:
            snapshot = compute_snapshot(
                possessions, games, as_of_date=as_of, window_seasons=window_seasons
            )
            rows = snapshot_to_dataframe(snapshot)
            if rows.empty:
                continue
            total_rows += await upsert_player_rapm(session, rows)
            await session.commit()
            write_player_rapm_parquet(rows)
            logger.info("player_rapm snapshot as_of=%s: %d players", as_of, len(rows))
    return total_rows


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train model heads on backfilled data and run the champion promotion gate."
    )
    parser.add_argument(
        "--heads",
        nargs="+",
        choices=sorted(HEAD_REGISTRY),
        default=sorted(HEAD_REGISTRY),
        help="Heads to train (default: all registered heads).",
    )
    parser.add_argument(
        "--lookback-seasons",
        type=int,
        default=15,
        help="Trailing training-window size in seasons (data-pipeline.md §9 default).",
    )
    parser.add_argument(
        "--rapm-snapshots",
        action="store_true",
        help="Also build the historical player_rapm snapshot cadence before training.",
    )
    parser.add_argument("--rapm-window-seasons", type=int, default=DEFAULT_WINDOW_SEASONS)
    parser.add_argument(
        "--rapm-monthly",
        action="store_true",
        help="Snapshot at month starts too, not just season ends (slow over the full era).",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    if args.rapm_snapshots:
        rows = await build_rapm_snapshots(
            window_seasons=args.rapm_window_seasons, monthly=args.rapm_monthly
        )
        logger.info("RAPM snapshots complete: %d player rows", rows)

    game_heads = [name for name in args.heads if name in GAME_HEADS]
    props_heads = [name for name in args.heads if name.startswith("props_")]
    if game_heads:
        await train_game_heads(game_heads, lookback_seasons=args.lookback_seasons)
    if props_heads:
        await train_props_heads(props_heads, lookback_seasons=args.lookback_seasons)


def main() -> None:
    """Parse args and run training + promotion to completion."""
    args = _parse_args()
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
