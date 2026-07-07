"""RAPM leaderboard + history service — backend-api.md §3 (RAPM) + Prompt 5.

Pure DB reads over the ``player_rapm`` snapshots (models/rapm/snapshots.py) joined to player
names. The leaderboard is a *single snapshot* (one ``as_of_date``) so every row is comparable;
by default it's the most recent snapshot for the requested window.
"""

from datetime import date as date_type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.rapm import RapmEntry, RapmHistoryEntry
from nbaforecast.storage.models import Player, PlayerRapm

DEFAULT_WINDOW = 3
# A low-possession rating is mostly noise even after ridge shrinkage — the leaderboard
# filters to a minimum sample by default (walkthrough finding, T3.15).
DEFAULT_MIN_POSS = 1000
SORTABLE_COLUMNS = {
    "rapm": PlayerRapm.rapm,
    "orapm": PlayerRapm.orapm,
    "drapm": PlayerRapm.drapm,
    "possessions": PlayerRapm.possessions,
}


def _as_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


async def _latest_as_of(session: AsyncSession, window: int) -> date_type | None:
    query = select(func.max(PlayerRapm.as_of_date)).where(PlayerRapm.window == window)
    return (await session.execute(query)).scalar_one_or_none()


async def rapm_leaderboard(
    session: AsyncSession,
    *,
    window: int = DEFAULT_WINDOW,
    as_of: date_type | None = None,
    sort: str = "rapm",
    min_poss: int = DEFAULT_MIN_POSS,
    page: int = 1,
    page_size: int = 25,
) -> Page[RapmEntry]:
    """``GET /rapm`` — one snapshot's players ranked by the chosen metric (descending).

    ``as_of`` defaults to the latest snapshot date for ``window``; ``sort`` is one of
    ``rapm``/``orapm``/``drapm``/``possessions``. ``min_poss`` drops small-sample ratings
    (0 shows everyone). Raises ``KeyError`` for an unknown ``sort`` (router → 400).
    """
    if sort not in SORTABLE_COLUMNS:
        raise KeyError(sort)

    effective_as_of = as_of if as_of is not None else await _latest_as_of(session, window)
    if effective_as_of is None:
        return Page(items=[], total=0, page=page, page_size=page_size)

    base = (
        select(PlayerRapm, Player.full_name)
        .join(Player, Player.player_id == PlayerRapm.player_id, isouter=True)
        .where(PlayerRapm.window == window, PlayerRapm.as_of_date == effective_as_of)
    )
    if min_poss > 0:
        base = base.where(PlayerRapm.possessions >= min_poss)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    sort_column = SORTABLE_COLUMNS[sort]
    paged = (
        base.order_by(sort_column.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(paged)).all()

    items = [
        RapmEntry(
            player_id=snapshot.player_id,
            full_name=full_name,
            as_of_date=snapshot.as_of_date,
            window=snapshot.window,
            orapm=_as_float(snapshot.orapm),
            drapm=_as_float(snapshot.drapm),
            rapm=_as_float(snapshot.rapm),
            possessions=snapshot.possessions,
        )
        for snapshot, full_name in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


async def player_rapm_history(
    session: AsyncSession, player_id: int, *, window: int = DEFAULT_WINDOW
) -> list[RapmHistoryEntry]:
    """``GET /players/{player_id}/rapm`` — that player's snapshots over time (chronological)."""
    query = (
        select(PlayerRapm)
        .where(PlayerRapm.player_id == player_id, PlayerRapm.window == window)
        .order_by(PlayerRapm.as_of_date)
    )
    snapshots = (await session.execute(query)).scalars().all()
    return [
        RapmHistoryEntry(
            as_of_date=snapshot.as_of_date,
            window=snapshot.window,
            orapm=_as_float(snapshot.orapm),
            drapm=_as_float(snapshot.drapm),
            rapm=_as_float(snapshot.rapm),
            possessions=snapshot.possessions,
        )
        for snapshot in snapshots
    ]
