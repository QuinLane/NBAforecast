"""Stint aggregation — rapm.md Prompt 1.

A **stint** is a maximal run of consecutive possessions (within one game, one period) that share
the same 10-player lineup (5 offense + 5 defense). Aggregating possessions into stints shrinks the
design matrix built in ``models/rapm/design.py`` — the ridge fit doesn't need possession-level
granularity, only per-lineup point totals and possession counts.

Consecutive possessions are compared by their *unordered* on-court lineup: two possessions belong
to the same stint only if both the offense five and the defense five are identical sets (order in
the ``off_player_ids``/``def_player_ids`` arrays is not meaningful — see
``storage/models/silver.py::Possession``). A change of offense/defense team, a substitution, a new
period, or a new game always starts a new stint.
"""

from dataclasses import dataclass

import pandas as pd

_LINEUP_SIZE = 5


@dataclass(slots=True)
class Stint:
    """One stint: a fixed 10-player lineup over one or more consecutive possessions.

    ``off_player_ids``/``def_player_ids`` are sorted tuples (order-independent identity) so two
    stints with the same players compare equal regardless of array ordering upstream.
    """

    game_id: str
    period: int
    offense_team_id: int
    defense_team_id: int
    off_player_ids: tuple[int, ...]
    def_player_ids: tuple[int, ...]
    points: int
    possessions: int


def _lineup_key(player_ids: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    if len(player_ids) != _LINEUP_SIZE:
        raise ValueError(f"expected {_LINEUP_SIZE} players on court, got {len(player_ids)}")
    return tuple(sorted(int(p) for p in player_ids))


def build_stints(possessions: pd.DataFrame) -> list[Stint]:
    """Group consecutive same-lineup possessions into stints.

    Args:
        possessions: Rows shaped like ``storage.models.silver.Possession`` — must contain
            ``game_id, period, offense_team_id, defense_team_id, points, off_player_ids,
            def_player_ids``, and (when present) be sorted within a game/period by
            possession order (``start_seconds`` ascending, or insertion order if ``start_seconds``
            is absent). Possessions for different games/periods need not be pre-sorted relative to
            each other.

    Returns:
        One ``Stint`` per maximal consecutive run sharing the same offense/defense lineup, in
        the order the runs occur in the input. Possession count and points are summed within
        a run.
    """
    if possessions.empty:
        return []

    sort_columns = [c for c in ("game_id", "period", "start_seconds") if c in possessions.columns]
    ordered = possessions.sort_values(sort_columns, kind="stable") if sort_columns else possessions

    stints: list[Stint] = []
    current: Stint | None = None

    for record in ordered.to_dict("records"):
        game_id = str(record["game_id"])
        period = int(record["period"])
        offense_team_id = int(record["offense_team_id"])
        defense_team_id = int(record["defense_team_id"])
        off_key = _lineup_key(record["off_player_ids"])
        def_key = _lineup_key(record["def_player_ids"])
        points = int(record["points"])

        same_stint = current is not None and (
            current.game_id == game_id
            and current.period == period
            and current.offense_team_id == offense_team_id
            and current.defense_team_id == defense_team_id
            and current.off_player_ids == off_key
            and current.def_player_ids == def_key
        )
        if current is not None and same_stint:
            current.points += points
            current.possessions += 1
        else:
            current = Stint(
                game_id=game_id,
                period=period,
                offense_team_id=offense_team_id,
                defense_team_id=defense_team_id,
                off_player_ids=off_key,
                def_player_ids=def_key,
                points=points,
                possessions=1,
            )
            stints.append(current)

    return stints


def stints_to_dataframe(stints: list[Stint]) -> pd.DataFrame:
    """Convenience: ``Stint`` list -> flat DataFrame (one row per stint)."""
    return pd.DataFrame(
        [
            {
                "game_id": s.game_id,
                "period": s.period,
                "offense_team_id": s.offense_team_id,
                "defense_team_id": s.defense_team_id,
                "off_player_ids": list(s.off_player_ids),
                "def_player_ids": list(s.def_player_ids),
                "points": s.points,
                "possessions": s.possessions,
            }
            for s in stints
        ]
    )
