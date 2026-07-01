"""RAPM → feature aggregations — rapm.md Prompt 6 / feature-engineering.md §5.

Turns ``player_rapm`` snapshots into the leakage-safe feature columns the model heads read:
``player_rapm`` on ``features_player_game`` (player quality for props) and
``team_orapm``/``team_drapm`` on ``features_team_game`` (team strength for game prediction).

**The cardinal rule (feature-engineering.md §2):** a feature for game G may only use information
available strictly before tip-off of G. Every join here is an *as-of* lookup that picks the most
recent snapshot whose ``as_of_date`` is on or before G's ``game_date`` — and because a snapshot
dated D was itself fit using only possessions from games strictly before D
(``models/rapm/snapshots.py``), such a snapshot never saw G. That two-step boundary (snapshot
excludes its own date; feature picks a snapshot dated ≤ G) is what keeps RAPM-as-a-feature
leakage-safe.

Team aggregation is **possession-weighted** over each team's *prior* roster (players who already
appeared for the team earlier in the same season — never G's own box score, which isn't known
pre-game), matching feature-engineering.md §5's "minutes-weighted team ORAPM/DRAPM": a snapshot's
possession count is the leakage-safe proxy for how much a player plays.
"""

import numpy as np
import pandas as pd

from nbaforecast.models.rapm.snapshots import DEFAULT_WINDOW_SEASONS

_SNAPSHOT_VALUE_COLUMNS = ["orapm", "drapm", "rapm", "possessions"]


def _window_snapshots(snapshots: pd.DataFrame, window: int) -> pd.DataFrame:
    """The snapshot rows for one rolling ``window``, sorted by ``as_of_date`` for ``merge_asof``."""
    columns = ["player_id", "as_of_date", *_SNAPSHOT_VALUE_COLUMNS]
    if snapshots.empty:
        return pd.DataFrame(columns=columns)
    snap = snapshots.loc[snapshots["window"] == window, columns].copy()
    snap["as_of_date"] = pd.to_datetime(snap["as_of_date"])
    return snap.sort_values("as_of_date", kind="mergesort").reset_index(drop=True)


def _asof_join(keys: pd.DataFrame, snapshots: pd.DataFrame, window: int) -> pd.DataFrame:
    """Attach each ``(player_id, game_date)`` key's latest pre-game snapshot values.

    ``keys`` must have ``player_id`` and ``game_date``. Returns ``keys`` (original order/index
    preserved) with ``orapm``/``drapm``/``rapm``/``possessions`` from the most recent snapshot
    whose ``as_of_date <= game_date`` (NaN where the player has no prior snapshot).
    """
    result = keys.copy()
    if result.empty:
        for column in _SNAPSHOT_VALUE_COLUMNS:
            result[column] = pd.Series(dtype="float64")
        return result

    snap = _window_snapshots(snapshots, window)
    if snap.empty:
        for column in _SNAPSHOT_VALUE_COLUMNS:
            result[column] = np.nan
        return result

    # merge_asof requires the left frame globally sorted by the "on" key; keep the original row
    # order via a positional marker so the caller's index/ordering is undisturbed.
    left = result.reset_index(drop=True)
    left["_row"] = np.arange(len(left))
    left["_game_date"] = pd.to_datetime(left["game_date"])
    left = left.sort_values("_game_date", kind="mergesort")

    merged = pd.merge_asof(
        left,
        snap,
        left_on="_game_date",
        right_on="as_of_date",
        by="player_id",
        direction="backward",
        allow_exact_matches=True,
    )
    merged = merged.sort_values("_row", kind="mergesort")
    for column in _SNAPSHOT_VALUE_COLUMNS:
        result[column] = merged[column].to_numpy()
    return result


def attach_player_rapm(
    player_keys: pd.DataFrame,
    snapshots: pd.DataFrame,
    *,
    window: int = DEFAULT_WINDOW_SEASONS,
) -> pd.Series:
    """Leakage-safe ``player_rapm`` for each player-game row.

    Args:
        player_keys: One row per player-game with at least ``player_id`` and ``game_date``.
        snapshots: ``player_rapm`` snapshot rows (``storage.models.serving.PlayerRapm`` shape:
            ``player_id, as_of_date, window, orapm, drapm, rapm, possessions``).
        window: Which rolling window's snapshots to read (rapm.md §9 default: 3 seasons).

    Returns:
        A ``player_rapm`` Series aligned to ``player_keys.index`` — the player's RAPM from the
        latest snapshot dated on or before their game, NaN when no such snapshot exists.
    """
    joined = _asof_join(player_keys, snapshots, window)
    return pd.Series(joined["rapm"].to_numpy(), index=player_keys.index, name="player_rapm")


def prior_rosters(player_game_stats: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Each ``(game_id, team_id)``'s *prior* roster: players who appeared for the team earlier
    in the same season, strictly before that game.

    Uses only completed prior-game box scores, so it never peeks at who actually suited up for
    the game being featurized (which is post-tip information). A team's very first game of a
    season yields no roster rows (nothing prior to draw on) — the aggregated team RAPM is then
    NaN, exactly like every other season-to-date feature's cold start.

    Returns:
        One row per ``(game_id, team_id, game_date, player_id)`` prior-roster membership.
    """
    columns = ["game_id", "team_id", "game_date", "player_id"]
    if player_game_stats.empty or games.empty:
        return pd.DataFrame(columns=columns)

    meta = games[["game_id", "season_start_year", "game_date"]].copy()
    meta["game_date"] = pd.to_datetime(meta["game_date"])
    pgs = player_game_stats[["game_id", "team_id", "player_id"]].merge(meta, on="game_id")

    rows: list[tuple[str, int, pd.Timestamp, int]] = []
    for _group_key, group in pgs.groupby(["team_id", "season_start_year"], sort=False):
        team_id = int(group["team_id"].iloc[0])
        players_by_game = group.groupby("game_id")["player_id"].apply(set)
        game_dates = group[["game_id", "game_date"]].drop_duplicates().sort_values("game_date")
        seen: set[int] = set()
        for game_id, game_date in game_dates.itertuples(index=False):
            for player_id in seen:
                rows.append((game_id, team_id, game_date, player_id))
            seen |= {int(p) for p in players_by_game.loc[game_id]}
    return pd.DataFrame(rows, columns=columns)


def _weighted_team_means(enriched: pd.DataFrame) -> pd.DataFrame:
    """Possession-weighted ORAPM/DRAPM per ``(game_id, team_id)`` over its roster's snapshots.

    Only roster players who *have* a snapshot (non-NaN ``orapm``) contribute; a team with no such
    player produces no row (→ NaN after the caller's left join). Weights are snapshot possessions;
    when a team's contributing weights all sum to zero it falls back to an unweighted mean, and
    when they sum positive it is the true weighted mean — done groupwise with plain sums (no
    per-group Python ``apply``) so it stays vectorized and cleanly typed.
    """
    contributing = enriched.loc[enriched["orapm"].notna()].copy()
    if contributing.empty:
        return pd.DataFrame(columns=["game_id", "team_id", "team_orapm", "team_drapm"])

    weight = contributing["possessions"].fillna(0.0).clip(lower=0.0)
    contributing["_w"] = weight
    contributing["_wo"] = weight * contributing["orapm"]
    contributing["_wd"] = weight * contributing["drapm"]

    grouped = contributing.groupby(["game_id", "team_id"], sort=False)
    sums = grouped[["_w", "_wo", "_wd"]].sum()
    unweighted = grouped[["orapm", "drapm"]].mean()

    positive = sums["_w"] > 0
    team_orapm = np.where(positive, sums["_wo"] / sums["_w"], unweighted["orapm"])
    team_drapm = np.where(positive, sums["_wd"] / sums["_w"], unweighted["drapm"])
    return pd.DataFrame(
        {"team_orapm": team_orapm, "team_drapm": team_drapm}, index=sums.index
    ).reset_index()


def attach_team_rapm(
    team_keys: pd.DataFrame,
    player_game_stats: pd.DataFrame,
    games: pd.DataFrame,
    snapshots: pd.DataFrame,
    *,
    window: int = DEFAULT_WINDOW_SEASONS,
) -> pd.DataFrame:
    """Leakage-safe possession-weighted ``team_orapm``/``team_drapm`` for each team-game row.

    Args:
        team_keys: One row per team-game with at least ``game_id`` and ``team_id``.
        player_game_stats: Silver player box lines (to reconstruct prior rosters).
        games: Silver games (for each game's ``season_start_year``/``game_date``).
        snapshots: ``player_rapm`` snapshot rows.
        window: Which rolling window's snapshots to read (default 3 seasons).

    Returns:
        A DataFrame indexed like ``team_keys`` with ``team_orapm`` and ``team_drapm`` columns
        (NaN where a team has no prior-roster player with a snapshot).
    """
    empty = pd.DataFrame(
        {"team_orapm": np.nan, "team_drapm": np.nan}, index=team_keys.index, dtype="float64"
    )
    rosters = prior_rosters(player_game_stats, games)
    if rosters.empty:
        return empty

    enriched = _asof_join(rosters, snapshots, window)
    aggregated = _weighted_team_means(enriched)

    merged = team_keys[["game_id", "team_id"]].merge(
        aggregated, on=["game_id", "team_id"], how="left"
    )
    return pd.DataFrame(
        {
            "team_orapm": merged["team_orapm"].to_numpy(),
            "team_drapm": merged["team_drapm"].to_numpy(),
        },
        index=team_keys.index,
    )
