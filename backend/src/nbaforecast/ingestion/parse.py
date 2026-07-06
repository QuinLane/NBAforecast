"""Parse raw nba_api / pbpstats payloads into silver DataFrames (data-pipeline.md Prompt 3).

Each ``parse_*`` returns a DataFrame whose columns match the silver table in
[data-model.md §3](../../../plans/data-model.md). Values are mapped from the (stable) NBA stats
column names but otherwise untransformed; ``created_at``/``updated_at`` are DB-defaulted.

Note: the exact NBA result-set headers are confirmed against live data at T1.7; the mappings here
follow the long-documented stats.nba.com schemas.
"""

import logging
import math
import re
from datetime import date
from typing import Any

import pandas as pd

from nbaforecast.ingestion.result_sets import result_set_records

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]

# First char of an NBA SEASON_ID → season type.
_SEASON_TYPE_BY_PREFIX = {
    "1": "Pre Season",
    "2": "Regular Season",
    "3": "All Star",
    "4": "Playoffs",
    "5": "Play In",
}


def _opt_int(value: Any) -> int | None:
    """Coerce to int, mapping ``None``/``""``/NaN/0-sentinels handled by caller to ``None``."""
    if value is None or value == "":
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return int(value)


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return float(value)


def _id_or_none(value: Any) -> int | None:
    """NBA uses 0 as a 'no player/team' sentinel in pbp; map it to NULL."""
    v = _opt_int(value)
    return None if v == 0 else v


def clock_to_seconds(clock: Any) -> int | None:
    """``"MM:SS"`` game clock → seconds remaining in the period."""
    if not clock or ":" not in str(clock):
        return None
    minutes, seconds = str(clock).split(":")
    return int(minutes) * 60 + int(float(seconds))


def minutes_to_float(value: Any) -> float | None:
    """NBA box-score ``MIN`` (``"MM:SS"`` or blank for DNP) → fractional minutes."""
    if value is None or value == "":
        return None
    text = str(value)
    if ":" in text:
        minutes, seconds = text.split(":")
        return int(minutes) + int(float(seconds)) / 60.0
    return float(text)


def season_from_id(season_id: str) -> tuple[str, int, str]:
    """``"22023"`` → (``"2023-24"``, ``2023``, ``"Regular Season"``)."""
    season_type = _SEASON_TYPE_BY_PREFIX.get(season_id[0], "Regular Season")
    start_year = int(season_id[1:])
    season = f"{start_year}-{(start_year + 1) % 100:02d}"
    return season, start_year, season_type


def parse_games(schedule_raw: JsonDict) -> pd.DataFrame:
    """Build the ``games`` table from a ``LeagueGameLog`` payload (two rows per game)."""
    records = result_set_records(schedule_raw, "LeagueGameLog")
    by_game: dict[str, dict[str, dict[str, Any]]] = {}
    for row in records:
        game_id = row["GAME_ID"]
        side = "home" if " vs. " in row["MATCHUP"] else "away"
        by_game.setdefault(game_id, {})[side] = row

    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for game_id, sides in by_game.items():
        if "home" not in sides or "away" not in sides:
            # NBA source-data bug (seen live at M3.5: 0022500147 carries "DET @ DAL" AND
            # "DAL @ DET" — both rows away-shaped). The payload is self-contradictory, so
            # home/away is underivable; drop the game loudly rather than fail the season.
            skipped.append(game_id)
            continue
        home, away = sides["home"], sides["away"]
        season, start_year, season_type = season_from_id(home["SEASON_ID"])
        rows.append(
            {
                "game_id": game_id,
                "season": season,
                "season_start_year": start_year,
                "season_type": season_type,
                "game_date": pd.to_datetime(home["GAME_DATE"]).date(),
                "game_datetime": None,
                "home_team_id": int(home["TEAM_ID"]),
                "away_team_id": int(away["TEAM_ID"]),
                "home_score": _opt_int(home.get("PTS")),
                "away_score": _opt_int(away.get("PTS")),
                "status": "final",
                "num_periods": 4,
            }
        )
    if skipped:
        logger.warning(
            "skipping %d game(s) with contradictory home/away MATCHUP rows "
            "(NBA source-data bug): %s",
            len(skipped),
            skipped,
        )
    return pd.DataFrame(rows)


def _v3_sides(boxscore_raw: JsonDict, root_key: str) -> dict[str, JsonDict]:
    """``{"home": <team obj>, "away": <team obj>}`` from a v3 boxscore payload."""
    root = boxscore_raw[root_key]
    return {"home": root["homeTeam"], "away": root["awayTeam"]}


def _counting_stats(stats: JsonDict) -> dict[str, int | None]:
    """The shared v3 counting-stat mapping (identical for team and player rows)."""
    return {
        "pts": _opt_int(stats.get("points")),
        "reb": _opt_int(stats.get("reboundsTotal")),
        "oreb": _opt_int(stats.get("reboundsOffensive")),
        "dreb": _opt_int(stats.get("reboundsDefensive")),
        "ast": _opt_int(stats.get("assists")),
        "stl": _opt_int(stats.get("steals")),
        "blk": _opt_int(stats.get("blocks")),
        "tov": _opt_int(stats.get("turnovers")),
        "pf": _opt_int(stats.get("foulsPersonal")),
        "fgm": _opt_int(stats.get("fieldGoalsMade")),
        "fga": _opt_int(stats.get("fieldGoalsAttempted")),
        "fg3m": _opt_int(stats.get("threePointersMade")),
        "fg3a": _opt_int(stats.get("threePointersAttempted")),
        "ftm": _opt_int(stats.get("freeThrowsMade")),
        "fta": _opt_int(stats.get("freeThrowsAttempted")),
    }


def parse_team_game_stats(boxscore_raw: JsonDict, home_team_id: int) -> pd.DataFrame:
    """Build ``team_game_stats`` from v3 traditional + advanced box scores for one game.

    ``home_team_id`` is retained for signature compatibility with the pipeline; home/away
    truth comes from the payload's own ``homeTeam``/``awayTeam`` grouping.
    """
    trad = boxscore_raw["traditional"]["boxScoreTraditional"]
    sides = _v3_sides(boxscore_raw["traditional"], "boxScoreTraditional")
    adv_sides = _v3_sides(boxscore_raw["advanced"], "boxScoreAdvanced")
    adv_by_team = {int(team["teamId"]): team["statistics"] for team in adv_sides.values()}
    game_id = str(trad["gameId"])

    rows: list[dict[str, Any]] = []
    for side, team in sides.items():
        team_id = int(team["teamId"])
        opponent = int(sides["away" if side == "home" else "home"]["teamId"])
        adv = adv_by_team.get(team_id, {})
        rows.append(
            {
                "game_id": game_id,
                "team_id": team_id,
                "opponent_team_id": opponent,
                "is_home": side == "home",
                **_counting_stats(team["statistics"]),
                "off_rating": _opt_float(adv.get("offensiveRating")),
                "def_rating": _opt_float(adv.get("defensiveRating")),
                "net_rating": _opt_float(adv.get("netRating")),
                "pace": _opt_float(adv.get("pace")),
                "possessions": _opt_float(adv.get("possessions")),
            }
        )
    return pd.DataFrame(rows)


def parse_player_game_stats(boxscore_raw: JsonDict, home_team_id: int) -> pd.DataFrame:
    """Build ``player_game_stats`` for players who appeared (non-empty v3 minutes)."""
    trad = boxscore_raw["traditional"]["boxScoreTraditional"]
    sides = _v3_sides(boxscore_raw["traditional"], "boxScoreTraditional")
    adv_sides = _v3_sides(boxscore_raw["advanced"], "boxScoreAdvanced")
    adv_by_player = {
        int(player["personId"]): player["statistics"]
        for team in adv_sides.values()
        for player in team.get("players", [])
    }
    game_id = str(trad["gameId"])

    rows: list[dict[str, Any]] = []
    for side, team in sides.items():
        team_id = int(team["teamId"])
        opponent = int(sides["away" if side == "home" else "home"]["teamId"])
        for player in team.get("players", []):
            stats = player["statistics"]
            minutes = minutes_to_float(stats.get("minutes"))
            if minutes is None:
                continue  # DNP — counting stats are null; excluded from silver
            player_id = int(player["personId"])
            adv = adv_by_player.get(player_id, {})
            rows.append(
                {
                    "game_id": game_id,
                    "player_id": player_id,
                    "team_id": team_id,
                    "opponent_team_id": opponent,
                    "is_home": side == "home",
                    # v3 fills `position` only for the five starters.
                    "started": bool(player.get("position")),
                    "min": minutes,
                    **_counting_stats(stats),
                    "plus_minus": _opt_int(stats.get("plusMinusPoints")),
                    "usage_rate": _opt_float(adv.get("usagePercentage")),
                }
            )
    return pd.DataFrame(rows)


_ISO_CLOCK_RE = re.compile(r"PT(\d+)M(\d+(?:\.\d+)?)S")


def _v3_clock(clock: Any) -> tuple[str | None, int | None]:
    """v3 ISO clock (``"PT11M22.00S"``) → (``"11:22"`` pc_time, seconds remaining)."""
    match = _ISO_CLOCK_RE.fullmatch(str(clock or ""))
    if match is None:
        return None, None
    minutes, seconds = int(match.group(1)), int(float(match.group(2)))
    return f"{minutes}:{seconds:02d}", minutes * 60 + seconds


def _v3_score(value: Any) -> int | None:
    """v3 ``scoreHome``/``scoreAway`` are strings, empty on non-scoring events."""
    if value is None or value == "":
        return None
    return int(value)


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def parse_play_by_play(pbp_raw: JsonDict) -> pd.DataFrame:
    """Build ``play_by_play`` from a ``PlayByPlayV3`` payload.

    v3 exposes one actor per event (``personId``) — ``player2_id``/``player3_id`` stay NULL
    (kept for rows ingested under v2).
    """
    game = pbp_raw["game"]
    game_id = str(game["gameId"])
    rows: list[dict[str, Any]] = []
    for action in game["actions"]:
        pc_time, seconds_remaining = _v3_clock(action.get("clock"))
        rows.append(
            {
                "game_id": game_id,
                # actionId, not actionNumber: v3 repeats actionNumber for paired events
                # (e.g. a turnover and its steal), which would collide on the PK; actionId
                # is unique and monotonic. NOTE: not the same numbering as shots.event_num
                # (shotchartdetail's GAME_EVENT_ID).
                "event_num": int(action["actionId"]),
                "period": int(action["period"]),
                "pc_time": pc_time,
                "seconds_remaining_period": seconds_remaining,
                "action_type": _opt_str(action.get("actionType")),
                "sub_type": _opt_str(action.get("subType")),
                "description": _opt_str(action.get("description")),
                "home_score": _v3_score(action.get("scoreHome")),
                "away_score": _v3_score(action.get("scoreAway")),
                "player1_id": _id_or_none(action.get("personId")),
                "player2_id": None,
                "player3_id": None,
                "team_id": _id_or_none(action.get("teamId")),
            }
        )
    return pd.DataFrame(rows)


def _shot_type(raw_type: Any) -> str | None:
    """``"2PT Field Goal"`` → ``"2PT"`` (data-model stores 2PT/3PT)."""
    if not raw_type:
        return None
    return str(raw_type).split(" ", 1)[0]


def parse_shots(shots_raw: JsonDict, season_start_year: int) -> pd.DataFrame:
    """Build ``shots`` from a ``ShotChartDetail`` payload.

    ``location_reliable`` is False for 1996-97..1999-00 (≈25% missing coords; data-pipeline §1).
    """
    records = result_set_records(shots_raw, "Shot_Chart_Detail")
    location_reliable = season_start_year >= 2000
    rows: list[dict[str, Any]] = []
    for row in records:
        minutes = _opt_int(row.get("MINUTES_REMAINING")) or 0
        seconds = _opt_int(row.get("SECONDS_REMAINING")) or 0
        rows.append(
            {
                "game_id": row["GAME_ID"],
                "event_num": int(row["GAME_EVENT_ID"]),
                "player_id": int(row["PLAYER_ID"]),
                "team_id": int(row["TEAM_ID"]),
                "period": int(row["PERIOD"]),
                "seconds_remaining_period": minutes * 60 + seconds,
                "loc_x": _opt_int(row.get("LOC_X")),
                "loc_y": _opt_int(row.get("LOC_Y")),
                "shot_distance": _opt_int(row.get("SHOT_DISTANCE")),
                "shot_zone": row.get("SHOT_ZONE_BASIC"),
                "shot_zone_area": row.get("SHOT_ZONE_AREA"),
                "shot_zone_range": row.get("SHOT_ZONE_RANGE"),
                "shot_type": _shot_type(row.get("SHOT_TYPE")),
                "action_type": row.get("ACTION_TYPE"),
                "made": bool(_opt_int(row.get("SHOT_MADE_FLAG"))),
                "location_reliable": location_reliable,
            }
        )
    return pd.DataFrame(rows)


def parse_possessions(possessions: list[JsonDict], game_id: str) -> pd.DataFrame:
    """Build ``possessions`` from the clean possession dicts emitted by ``fetch_possessions``.

    Expected keys per possession: ``period, start_seconds, end_seconds, offense_team_id,
    defense_team_id, points, off_player_ids, def_player_ids``.
    """
    rows: list[dict[str, Any]] = []
    for p in possessions:
        rows.append(
            {
                "game_id": game_id,
                "period": int(p["period"]),
                "start_seconds": _opt_int(p.get("start_seconds")),
                "end_seconds": _opt_int(p.get("end_seconds")),
                "offense_team_id": int(p["offense_team_id"]),
                "defense_team_id": int(p["defense_team_id"]),
                "points": int(p["points"]),
                "off_player_ids": [int(x) for x in p["off_player_ids"]],
                "def_player_ids": [int(x) for x in p["def_player_ids"]],
            }
        )
    return pd.DataFrame(rows)


def parse_game_date(value: str) -> date:
    """Parse an NBA ``GAME_DATE`` string to a ``date`` (exposed for the daily flow)."""
    return pd.to_datetime(value).date()
