"""Team roster is 'current roster', not 'everyone who ever played for the team'.

A mid-season trade (Luke Kennard, live finding) used to list a player on both teams because the
roster was every player with a game for the team. It's now anchored on each player's most recent
game in the team's current season, so a traded player shows on his latest team only.
"""

from collections.abc import AsyncIterator
from datetime import date

import pytest_asyncio
from nbaforecast.api.services import teams as teams_service
from nbaforecast.storage.database import Base
from nbaforecast.storage.models import Game, Player, PlayerGameStats, Team
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

_PLAYER_STAT_ZEROS = dict.fromkeys(
    ("oreb", "dreb", "stl", "blk", "tov", "pf", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta"), 0
)

TEAM_A, TEAM_B = 1, 2
TRADED, STAYER = 100, 101


def _game(gid: str, day: date, home: int, away: int) -> Game:
    return Game(
        game_id=gid,
        season="2025-26",
        season_start_year=2025,
        season_type="Regular Season",
        game_date=day,
        home_team_id=home,
        away_team_id=away,
        home_score=110,
        away_score=100,
        status="final",
    )


def _line(gid: str, player_id: int, team_id: int, opp: int) -> PlayerGameStats:
    return PlayerGameStats(
        game_id=gid,
        player_id=player_id,
        team_id=team_id,
        opponent_team_id=opp,
        is_home=True,
        started=True,
        min=30.0,
        pts=10,
        reb=5,
        ast=5,
        **_PLAYER_STAT_ZEROS,
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = (Team.__table__, Player.__table__, Game.__table__, PlayerGameStats.__table__)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        for tid in (TEAM_A, TEAM_B):
            s.add(Team(team_id=tid, abbreviation=f"T{tid}", full_name=f"Team {tid}"))
        s.add(Player(player_id=TRADED, full_name="Traded Player", position="G", is_active=True))
        s.add(Player(player_id=STAYER, full_name="Stayer", position="F", is_active=True))
        # Traded plays for A early, then B late; Stayer stays on A the whole time.
        s.add(_game("g1", date(2025, 11, 1), TEAM_A, TEAM_B))
        s.add(_game("g2", date(2025, 12, 1), TEAM_B, TEAM_A))
        s.add(_line("g1", TRADED, TEAM_A, TEAM_B))
        s.add(_line("g1", STAYER, TEAM_A, TEAM_B))
        s.add(_line("g2", TRADED, TEAM_B, TEAM_A))
        s.add(_line("g2", STAYER, TEAM_A, TEAM_B))
        await s.commit()
        yield s
    await engine.dispose()


async def test_traded_player_only_on_latest_team(session: AsyncSession) -> None:
    a_profile = await teams_service.team_profile(session, TEAM_A)
    b_profile = await teams_service.team_profile(session, TEAM_B)
    assert a_profile is not None
    assert b_profile is not None
    a_roster = {p.player_id for p in a_profile.roster}
    b_roster = {p.player_id for p in b_profile.roster}
    # Traded player's last game was for B → on B's roster only.
    assert TRADED in b_roster
    assert TRADED not in a_roster
    # The stayer remains on A.
    assert STAYER in a_roster
    assert STAYER not in b_roster
