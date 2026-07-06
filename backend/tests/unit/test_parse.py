"""Unit tests for silver parse functions using synthetic nba_api-shaped payloads."""

from typing import Any

import pandas as pd
from nbaforecast.ingestion.parse import (
    minutes_to_float,
    parse_games,
    parse_play_by_play,
    parse_player_game_stats,
    parse_possessions,
    parse_shots,
    parse_team_game_stats,
    season_from_id,
)

LAL = 1610612747
BOS = 1610612738


def _result_set(name: str, headers: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"resultSets": [{"name": name, "headers": headers, "rowSet": rows}]}


def test_season_from_id() -> None:
    assert season_from_id("22023") == ("2023-24", 2023, "Regular Season")
    assert season_from_id("42015") == ("2015-16", 2015, "Playoffs")


def test_minutes_to_float() -> None:
    assert minutes_to_float("34:30") == 34.5
    assert minutes_to_float("") is None
    assert minutes_to_float(None) is None


def test_parse_games_pairs_home_and_away() -> None:
    raw = _result_set(
        "LeagueGameLog",
        ["SEASON_ID", "TEAM_ID", "GAME_ID", "GAME_DATE", "MATCHUP", "PTS"],
        [
            ["22023", LAL, "0022300001", "2023-10-24", "LAL vs. BOS", 110],
            ["22023", BOS, "0022300001", "2023-10-24", "BOS @ LAL", 105],
        ],
    )
    df = parse_games(raw)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["home_team_id"] == LAL
    assert row["away_team_id"] == BOS
    assert row["home_score"] == 110
    assert row["away_score"] == 105
    assert row["season"] == "2023-24"
    assert row["season_start_year"] == 2023
    assert row["status"] == "final"


# v3 counting stats: 1..15 in silver column order (pts..fta) via the v3 field names.
_V3_COUNTS = {
    "points": 1,
    "reboundsTotal": 2,
    "reboundsOffensive": 3,
    "reboundsDefensive": 4,
    "assists": 5,
    "steals": 6,
    "blocks": 7,
    "turnovers": 8,
    "foulsPersonal": 9,
    "fieldGoalsMade": 10,
    "fieldGoalsAttempted": 11,
    "threePointersMade": 12,
    "threePointersAttempted": 13,
    "freeThrowsMade": 14,
    "freeThrowsAttempted": 15,
}


def _v3_player(person_id: int, minutes: str, *, position: str = "", **stats: Any) -> dict[str, Any]:
    return {
        "personId": person_id,
        "position": position,
        "statistics": {"minutes": minutes, **stats},
    }


def _v3_boxscore(
    home: dict[str, Any],
    away: dict[str, Any],
    adv_home: dict[str, Any],
    adv_away: dict[str, Any],
) -> dict[str, Any]:
    def wrap(key: str, home_team: dict[str, Any], away_team: dict[str, Any]) -> dict[str, Any]:
        return {
            "meta": {},
            key: {
                "gameId": "0022300001",
                "homeTeamId": home_team["teamId"],
                "awayTeamId": away_team["teamId"],
                "homeTeam": home_team,
                "awayTeam": away_team,
            },
        }

    return {
        "traditional": wrap("boxScoreTraditional", home, away),
        "advanced": wrap("boxScoreAdvanced", adv_home, adv_away),
    }


def test_parse_team_game_stats() -> None:
    raw = _v3_boxscore(
        {"teamId": LAL, "players": [], "statistics": dict(_V3_COUNTS)},
        {"teamId": BOS, "players": [], "statistics": dict(_V3_COUNTS)},
        {
            "teamId": LAL,
            "players": [],
            "statistics": {
                "offensiveRating": 112.5,
                "defensiveRating": 108.0,
                "netRating": 4.5,
                "pace": 99.0,
                "possessions": 98.0,
            },
        },
        {"teamId": BOS, "players": [], "statistics": {}},
    )
    df = parse_team_game_stats(raw, home_team_id=LAL)
    assert set(df["team_id"]) == {LAL, BOS}
    lal = df[df["team_id"] == LAL].iloc[0]
    assert lal["is_home"]
    assert lal["opponent_team_id"] == BOS
    assert lal["tov"] == 8  # turnovers in the v3 stat mapping
    assert lal["off_rating"] == 112.5
    assert lal["possessions"] == 98.0
    bos = df[df["team_id"] == BOS].iloc[0]
    assert not bos["is_home"]


def test_parse_player_game_stats_filters_dnp() -> None:
    raw = _v3_boxscore(
        {
            "teamId": LAL,
            "statistics": {},
            "players": [_v3_player(201939, "34:30", position="G", **_V3_COUNTS)],
        },
        {
            "teamId": BOS,
            "statistics": {},
            # DNP — empty v3 minutes; excluded from silver
            "players": [_v3_player(202681, "", **_V3_COUNTS)],
        },
        {
            "teamId": LAL,
            "statistics": {},
            "players": [_v3_player(201939, "34:30", usagePercentage=0.28)],
        },
        {"teamId": BOS, "statistics": {}, "players": []},
    )
    df = parse_player_game_stats(raw, home_team_id=LAL)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["player_id"] == 201939
    assert row["started"]  # v3 fills `position` only for starters
    assert row["min"] == 34.5
    assert row["usage_rate"] == 0.28
    assert row["opponent_team_id"] == BOS


def test_parse_play_by_play() -> None:
    raw = {
        "meta": {},
        "game": {
            "gameId": "0022300001",
            "actions": [
                {
                    "actionNumber": 2,
                    "actionId": 2,
                    "clock": "PT11M34.00S",
                    "period": 1,
                    "actionType": "Made Shot",
                    "subType": "Jump Shot",
                    "description": "Made shot",
                    "scoreHome": "0",
                    "scoreAway": "2",
                    "personId": 201939,
                    "teamId": LAL,
                },
                # v3 repeats actionNumber for paired events — actionId must win the PK.
                {
                    "actionNumber": 2,
                    "actionId": 3,
                    "clock": "PT11M20.00S",
                    "period": 1,
                    "actionType": "Rebound",
                    "subType": "",
                    "description": "",
                    "scoreHome": "",
                    "scoreAway": "",
                    "personId": 0,
                    "teamId": 0,
                },
            ],
        },
    }
    df = parse_play_by_play(raw)
    row = df.iloc[0]
    assert row["event_num"] == 2
    assert row["seconds_remaining_period"] == 11 * 60 + 34
    assert row["action_type"] == "Made Shot"
    assert row["sub_type"] == "Jump Shot"
    assert row["description"] == "Made shot"
    assert row["away_score"] == 2
    assert row["home_score"] == 0
    assert row["player1_id"] == 201939
    assert row["player2_id"] is None  # v3 has a single actor
    second = df.iloc[1]
    assert second["event_num"] == 3  # actionId, not the (repeated) actionNumber
    assert pd.isna(second["player1_id"])  # 0 sentinel → None
    assert pd.isna(second["home_score"])  # empty score strings → None
    assert second["sub_type"] is None


def test_parse_shots_location_reliable_flag() -> None:
    headers = [
        "GAME_ID",
        "GAME_EVENT_ID",
        "PLAYER_ID",
        "TEAM_ID",
        "PERIOD",
        "MINUTES_REMAINING",
        "SECONDS_REMAINING",
        "LOC_X",
        "LOC_Y",
        "SHOT_DISTANCE",
        "SHOT_ZONE_BASIC",
        "SHOT_ZONE_AREA",
        "SHOT_ZONE_RANGE",
        "SHOT_TYPE",
        "ACTION_TYPE",
        "SHOT_MADE_FLAG",
    ]
    row = [
        "0022300001",
        4,
        201939,
        LAL,
        1,
        11,
        20,
        -120,
        80,
        14,
        "Mid-Range",
        "Center(C)",
        "8-16 ft.",
        "2PT Field Goal",
        "Jump Shot",
        1,
    ]
    modern = parse_shots(_result_set("Shot_Chart_Detail", headers, [row]), 2023)
    assert modern.iloc[0]["location_reliable"]
    assert modern.iloc[0]["shot_type"] == "2PT"
    assert modern.iloc[0]["made"]
    assert modern.iloc[0]["seconds_remaining_period"] == 11 * 60 + 20

    early = parse_shots(_result_set("Shot_Chart_Detail", headers, [row]), 1998)
    assert not early.iloc[0]["location_reliable"]


def test_parse_possessions() -> None:
    clean = [
        {
            "period": 1,
            "start_seconds": 700,
            "end_seconds": 690,
            "offense_team_id": LAL,
            "defense_team_id": BOS,
            "points": 2,
            "off_player_ids": [1, 2, 3, 4, 5],
            "def_player_ids": [6, 7, 8, 9, 10],
        }
    ]
    df = parse_possessions(clean, "0022300001")
    row = df.iloc[0]
    assert row["game_id"] == "0022300001"
    assert row["offense_team_id"] == LAL
    assert row["points"] == 2
    assert row["off_player_ids"] == [1, 2, 3, 4, 5]
