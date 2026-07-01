"""RAPM snapshots + storage — rapm.md Prompt 4 / §5.

Computes RAPM at a fixed cadence over a rolling multi-season window (rapm.md §9: 3 seasons by
default) rather than refitting per game — refitting ridge for every historical game is too
expensive, and downstream features only ever need the latest snapshot strictly before the game
being featurized (point-in-time correctness, feature-engineering.md §2).

A snapshot's ``as_of_date`` is the point in time the window is computed as of. Only possessions
from games whose ``game_date`` is **strictly before** ``as_of_date`` are used to fit that
snapshot — this is what keeps the snapshot leakage-safe when later consumed as a pre-game
feature.
"""

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd
from prefect import task
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.models.rapm.design import build_design_matrix
from nbaforecast.models.rapm.fit import PlayerRapmRating, fit_rapm, select_alpha
from nbaforecast.models.rapm.stints import build_stints, stints_to_dataframe
from nbaforecast.storage.database import get_sessionmaker
from nbaforecast.storage.models.serving import PlayerRapm
from nbaforecast.storage.models.silver import Game, Possession
from nbaforecast.storage.parquet_io import write_parquet
from nbaforecast.storage.parquet_schemas import GOLD_PARQUET_SCHEMAS
from nbaforecast.storage.repositories import load_table_as_dataframe, to_db_records, upsert_rows

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SEASONS = 3
PLAYER_RAPM_UPSERT_KEY = ("player_id", "as_of_date", "window")


@dataclass(slots=True)
class RapmSnapshot:
    """One cadence run's worth of per-player RAPM ratings, as of ``as_of_date``."""

    as_of_date: date
    window_seasons: int
    alpha: float
    ratings: list[PlayerRapmRating]
    possessions_by_player: dict[int, int]


def _possessions_by_player(stints: pd.DataFrame) -> dict[int, int]:
    """Total possessions each player appeared in (offense + defense), for the snapshot's
    ``possessions`` column (sample-size context, rapm.md §5)."""
    counts: dict[int, int] = {}
    for record in stints.to_dict("records"):
        possessions = int(record["possessions"])
        for player_id in (*record["off_player_ids"], *record["def_player_ids"]):
            counts[int(player_id)] = counts.get(int(player_id), 0) + possessions
    return counts


def compute_snapshot(
    possessions: pd.DataFrame,
    games: pd.DataFrame,
    *,
    as_of_date: date,
    window_seasons: int = DEFAULT_WINDOW_SEASONS,
) -> RapmSnapshot:
    """Fit one RAPM snapshot as of ``as_of_date`` over the trailing ``window_seasons``.

    Args:
        possessions: Full possession history (``storage.models.silver.Possession`` shape).
        games: Game metadata with at least ``game_id, game_date, season_start_year`` — used to
            restrict ``possessions`` to games strictly before ``as_of_date`` and within the
            rolling window.
        as_of_date: The snapshot's point-in-time cutoff. Only games with ``game_date <
            as_of_date`` are used — this is the leakage boundary (rapm.md §5).
        window_seasons: How many trailing NBA seasons of games to include (rapm.md §9 default 3).

    Returns:
        A :class:`RapmSnapshot`. If no eligible games exist, returns an empty snapshot (no
        ratings) rather than raising — callers should skip writing empty snapshots.
    """
    if games.empty or possessions.empty:
        return RapmSnapshot(
            as_of_date=as_of_date,
            window_seasons=window_seasons,
            alpha=float("nan"),
            ratings=[],
            possessions_by_player={},
        )

    games = games.copy()
    games["game_date"] = pd.to_datetime(games["game_date"]).dt.date
    eligible_games = games.loc[games["game_date"] < as_of_date]

    if not eligible_games.empty:
        cutoff_start_year = int(eligible_games["season_start_year"].max()) - (window_seasons - 1)
        eligible_games = eligible_games.loc[
            eligible_games["season_start_year"] >= cutoff_start_year
        ]

    eligible_game_ids = set(eligible_games["game_id"])
    window_possessions = possessions.loc[possessions["game_id"].isin(eligible_game_ids)]

    if window_possessions.empty:
        return RapmSnapshot(
            as_of_date=as_of_date,
            window_seasons=window_seasons,
            alpha=float("nan"),
            ratings=[],
            possessions_by_player={},
        )

    stints = stints_to_dataframe(build_stints(window_possessions))
    alpha = select_alpha(stints)
    design = build_design_matrix(stints)
    fit_result = fit_rapm(design, alpha)

    return RapmSnapshot(
        as_of_date=as_of_date,
        window_seasons=window_seasons,
        alpha=alpha,
        ratings=fit_result.ratings,
        possessions_by_player=_possessions_by_player(stints),
    )


def snapshot_to_dataframe(snapshot: RapmSnapshot) -> pd.DataFrame:
    """``RapmSnapshot`` -> the ``player_rapm`` row shape (Postgres + Parquet)."""
    if not snapshot.ratings:
        return pd.DataFrame(
            columns=[
                "player_id",
                "as_of_date",
                "window",
                "orapm",
                "drapm",
                "rapm",
                "possessions",
            ]
        )
    return pd.DataFrame(
        [
            {
                "player_id": rating.player_id,
                "as_of_date": snapshot.as_of_date,
                "window": snapshot.window_seasons,
                "orapm": rating.orapm,
                "drapm": rating.drapm,
                "rapm": rating.rapm,
                "possessions": snapshot.possessions_by_player.get(rating.player_id, 0),
            }
            for rating in snapshot.ratings
        ]
    )


async def upsert_player_rapm(session: AsyncSession, rows: pd.DataFrame) -> int:
    """Upsert snapshot rows into Postgres (``player_rapm``)."""
    if rows.empty:
        return 0
    return await upsert_rows(session, PlayerRapm, to_db_records(rows), PLAYER_RAPM_UPSERT_KEY)


def write_player_rapm_parquet(rows: pd.DataFrame, root: str | None = None) -> list[str]:
    """Write snapshot rows to the Parquet gold store, partitioned by season (of ``as_of_date``).

    One part-file per ``(as_of_date, window)`` pair, mirroring the idempotent-by-key layout used
    for ``features_team_game`` (``features/materialize.py``).
    """
    if rows.empty:
        return []
    schema = GOLD_PARQUET_SCHEMAS["player_rapm"]
    rows = rows.copy()
    rows["season_start_year"] = pd.to_datetime(rows["as_of_date"]).apply(
        lambda d: d.year if d.month >= 8 else d.year - 1
    )
    paths = []
    for (season_start_year, as_of_date, window), group in rows.groupby(
        ["season_start_year", "as_of_date", "window"], sort=False
    ):
        partition_key = f"{as_of_date}_{window}"
        paths.append(
            str(
                write_parquet(
                    "player_rapm",
                    group,
                    int(season_start_year),  # type: ignore[call-overload]
                    partition_key=partition_key,
                    root=root,
                    schema=schema,
                )
            )
        )
    return paths


def snapshot_dates(games: pd.DataFrame, *, monthly: bool = True) -> list[date]:
    """The cadence of snapshot dates for a games history — rapm.md §5/§10: per-season-to-date
    (the day after each season's last game date seen) plus, when ``monthly``, the first of each
    calendar month that has eligible games in-between.

    This is a scheduling helper for the Prefect refresh task; ``compute_snapshot`` itself just
    needs a single ``as_of_date``.
    """
    if games.empty:
        return []
    game_dates = pd.to_datetime(games["game_date"]).dt.date
    season_ends = (
        games.assign(game_date=game_dates)
        .groupby("season_start_year")["game_date"]
        .max()
        .sort_index()
    )
    dates = {end + pd.Timedelta(days=1) for end in season_ends}
    dates = {d if isinstance(d, date) else d.date() for d in dates}

    if monthly:
        min_date, max_date = min(game_dates), max(game_dates)
        month_starts = pd.date_range(min_date, max_date, freq="MS").date
        dates.update(month_starts.tolist())

    return sorted(dates)


@task(name="refresh-latest-rapm-snapshot")
async def refresh_latest_rapm_snapshot(
    as_of_date: date, *, window_seasons: int = DEFAULT_WINDOW_SEASONS
) -> int:
    """Compute and persist (Postgres + Parquet) the RAPM snapshot for ``as_of_date``.

    Run after ingestion lands a day's games/possessions (mirrors
    ``features/flows.py::refresh_team_game_features``'s wiring) so ``player_rapm`` never drifts
    behind silver by more than one cadence step. A no-op (returns 0, no writes) when there are no
    eligible possessions yet — e.g. very early in a fresh backfill.
    """
    async with get_sessionmaker()() as session:
        games = await load_table_as_dataframe(session, Game)
        possessions = await load_table_as_dataframe(session, Possession)
        snapshot = compute_snapshot(
            possessions, games, as_of_date=as_of_date, window_seasons=window_seasons
        )
        rows = snapshot_to_dataframe(snapshot)
        count = await upsert_player_rapm(session, rows)
        await session.commit()
        write_player_rapm_parquet(rows)
    logger.info(
        "refreshed player_rapm as_of=%s window=%d seasons, %d player rows",
        as_of_date,
        window_seasons,
        count,
    )
    return count
