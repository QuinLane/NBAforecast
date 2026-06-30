"""Parse raw nba_api / pbpstats payloads into silver DataFrames (data-pipeline.md Prompt 3).

Each ``parse_*`` returns a DataFrame whose columns match the silver table in
[data-model.md §3](../../../plans/data-model.md). Values are mapped from the (stable) NBA stats
column names but otherwise untransformed; ``created_at``/``updated_at`` are DB-defaulted.

Note: the exact NBA result-set headers are confirmed against live data at T1.7; the mappings here
follow the long-documented stats.nba.com schemas.
"""

import math
from datetime import date
from typing import Any

import pandas as pd

from nbaforecast.errors import IngestionError
from nbaforecast.ingestion.result_sets import result_set_records

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
    for game_id, sides in by_game.items():
        if "home" not in sides or "away" not in sides:
            raise IngestionError(f"game {game_id} missing home or away row in schedule")
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
    return pd.DataFrame(rows)


def _team_rows(boxscore_raw: JsonDict) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    traditional = result_set_records(boxscore_raw["traditional"], "TeamStats")
    advanced_by_team = {
        int(r["TEAM_ID"]): r for r in result_set_records(boxscore_raw["advanced"], "TeamStats")
    }
    return traditional, advanced_by_team


def parse_team_game_stats(boxscore_raw: JsonDict, home_team_id: int) -> pd.DataFrame:
    """Build ``team_game_stats`` from traditional + advanced box scores for one game."""
    traditional, advanced_by_team = _team_rows(boxscore_raw)
    team_ids = [int(r["TEAM_ID"]) for r in traditional]
    rows: list[dict[str, Any]] = []
    for tr in traditional:
        team_id = int(tr["TEAM_ID"])
        adv = advanced_by_team.get(team_id, {})
        opponent = next(t for t in team_ids if t != team_id)
        rows.append(
            {
                "game_id": tr["GAME_ID"],
                "team_id": team_id,
                "opponent_team_id": opponent,
                "is_home": team_id == home_team_id,
                "pts": _opt_int(tr["PTS"]),
                "reb": _opt_int(tr["REB"]),
                "oreb": _opt_int(tr["OREB"]),
                "dreb": _opt_int(tr["DREB"]),
                "ast": _opt_int(tr["AST"]),
                "stl": _opt_int(tr["STL"]),
                "blk": _opt_int(tr["BLK"]),
                "tov": _opt_int(tr["TO"]),
                "pf": _opt_int(tr["PF"]),
                "fgm": _opt_int(tr["FGM"]),
                "fga": _opt_int(tr["FGA"]),
                "fg3m": _opt_int(tr["FG3M"]),
                "fg3a": _opt_int(tr["FG3A"]),
                "ftm": _opt_int(tr["FTM"]),
                "fta": _opt_int(tr["FTA"]),
                "off_rating": _opt_float(adv.get("OFF_RATING")),
                "def_rating": _opt_float(adv.get("DEF_RATING")),
                "net_rating": _opt_float(adv.get("NET_RATING")),
                "pace": _opt_float(adv.get("PACE")),
                "possessions": _opt_float(adv.get("POSS")),
            }
        )
    return pd.DataFrame(rows)


def parse_player_game_stats(boxscore_raw: JsonDict, home_team_id: int) -> pd.DataFrame:
    """Build ``player_game_stats`` for players who appeared (non-null minutes)."""
    traditional = result_set_records(boxscore_raw["traditional"], "PlayerStats")
    advanced_by_player = {
        int(r["PLAYER_ID"]): r for r in result_set_records(boxscore_raw["advanced"], "PlayerStats")
    }
    team_ids = {int(r["TEAM_ID"]) for r in traditional}
    rows: list[dict[str, Any]] = []
    for tr in traditional:
        minutes = minutes_to_float(tr.get("MIN"))
        if minutes is None:
            continue  # DNP — counting stats are null; excluded from silver
        player_id = int(tr["PLAYER_ID"])
        team_id = int(tr["TEAM_ID"])
        adv = advanced_by_player.get(player_id, {})
        opponent = next(t for t in team_ids if t != team_id)
        rows.append(
            {
                "game_id": tr["GAME_ID"],
                "player_id": player_id,
                "team_id": team_id,
                "opponent_team_id": opponent,
                "is_home": team_id == home_team_id,
                "started": bool(tr.get("START_POSITION")),
                "min": minutes,
                "pts": _opt_int(tr["PTS"]),
                "reb": _opt_int(tr["REB"]),
                "oreb": _opt_int(tr["OREB"]),
                "dreb": _opt_int(tr["DREB"]),
                "ast": _opt_int(tr["AST"]),
                "stl": _opt_int(tr["STL"]),
                "blk": _opt_int(tr["BLK"]),
                "tov": _opt_int(tr["TO"]),
                "pf": _opt_int(tr["PF"]),
                "fgm": _opt_int(tr["FGM"]),
                "fga": _opt_int(tr["FGA"]),
                "fg3m": _opt_int(tr["FG3M"]),
                "fg3a": _opt_int(tr["FG3A"]),
                "ftm": _opt_int(tr["FTM"]),
                "fta": _opt_int(tr["FTA"]),
                "plus_minus": _opt_int(tr.get("PLUS_MINUS")),
                "usage_rate": _opt_float(adv.get("USG_PCT")),
            }
        )
    return pd.DataFrame(rows)


def _pbp_description(row: dict[str, Any]) -> str | None:
    for key in ("HOMEDESCRIPTION", "VISITORDESCRIPTION", "NEUTRALDESCRIPTION"):
        text = row.get(key)
        if text:
            return str(text)
    return None


def _pbp_scores(score: Any) -> tuple[int | None, int | None]:
    """NBA pbp ``SCORE`` is ``"away - home"``; absent except on scoring plays."""
    if not score or "-" not in str(score):
        return None, None
    away, home = str(score).split("-")
    return int(away.strip()), int(home.strip())


def parse_play_by_play(pbp_raw: JsonDict) -> pd.DataFrame:
    """Build ``play_by_play`` from a ``PlayByPlayV2`` payload."""
    records = result_set_records(pbp_raw, "PlayByPlay")
    rows: list[dict[str, Any]] = []
    for row in records:
        away_score, home_score = _pbp_scores(row.get("SCORE"))
        rows.append(
            {
                "game_id": row["GAME_ID"],
                "event_num": int(row["EVENTNUM"]),
                "period": int(row["PERIOD"]),
                "pc_time": row.get("PCTIMESTRING"),
                "seconds_remaining_period": clock_to_seconds(row.get("PCTIMESTRING")),
                "event_msg_type": _opt_int(row.get("EVENTMSGTYPE")),
                "event_action_type": _opt_int(row.get("EVENTMSGACTIONTYPE")),
                "description": _pbp_description(row),
                "home_score": home_score,
                "away_score": away_score,
                "player1_id": _id_or_none(row.get("PLAYER1_ID")),
                "player2_id": _id_or_none(row.get("PLAYER2_ID")),
                "player3_id": _id_or_none(row.get("PLAYER3_ID")),
                "team_id": _id_or_none(row.get("PLAYER1_TEAM_ID")),
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
