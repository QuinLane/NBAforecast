"""Unit tests for silver parse functions using synthetic nba_api-shaped payloads."""

from typing import Any

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


def _boxscore(
    team_headers: list[str],
    team_rows: list[list[Any]],
    adv_headers: list[str],
    adv_rows: list[list[Any]],
    player_headers: list[str],
    player_rows: list[list[Any]],
    adv_player_headers: list[str],
    adv_player_rows: list[list[Any]],
) -> dict[str, Any]:
    return {
        "traditional": {
            "resultSets": [
                {"name": "TeamStats", "headers": team_headers, "rowSet": team_rows},
                {"name": "PlayerStats", "headers": player_headers, "rowSet": player_rows},
            ]
        },
        "advanced": {
            "resultSets": [
                {"name": "TeamStats", "headers": adv_headers, "rowSet": adv_rows},
                {"name": "PlayerStats", "headers": adv_player_headers, "rowSet": adv_player_rows},
            ]
        },
    }


_COUNTING = [
    "PTS",
    "REB",
    "OREB",
    "DREB",
    "AST",
    "STL",
    "BLK",
    "TO",
    "PF",
    "FGM",
    "FGA",
    "FG3M",
    "FG3A",
    "FTM",
    "FTA",
]


def test_parse_team_game_stats() -> None:
    team_headers = ["GAME_ID", "TEAM_ID", *_COUNTING]
    counts = list(range(1, 16))
    raw = _boxscore(
        team_headers,
        [["0022300001", LAL, *counts], ["0022300001", BOS, *counts]],
        ["GAME_ID", "TEAM_ID", "OFF_RATING", "DEF_RATING", "NET_RATING", "PACE", "POSS"],
        [
            ["0022300001", LAL, 112.5, 108.0, 4.5, 99.0, 98.0],
            ["0022300001", BOS, 108.0, 112.5, -4.5, 99.0, 98.0],
        ],
        ["GAME_ID", "TEAM_ID", "PLAYER_ID", "MIN", "START_POSITION", *_COUNTING, "PLUS_MINUS"],
        [],
        ["GAME_ID", "PLAYER_ID", "USG_PCT"],
        [],
    )
    df = parse_team_game_stats(raw, home_team_id=LAL)
    assert set(df["team_id"]) == {LAL, BOS}
    lal = df[df["team_id"] == LAL].iloc[0]
    assert lal["is_home"]
    assert lal["opponent_team_id"] == BOS
    assert lal["tov"] == 8  # 8th counting column (TO)
    assert lal["off_rating"] == 112.5
    assert lal["possessions"] == 98.0


def test_parse_player_game_stats_filters_dnp() -> None:
    player_headers = [
        "GAME_ID",
        "TEAM_ID",
        "PLAYER_ID",
        "MIN",
        "START_POSITION",
        *_COUNTING,
        "PLUS_MINUS",
    ]
    counts = list(range(1, 16))
    raw = _boxscore(
        ["GAME_ID", "TEAM_ID", *_COUNTING],
        [["0022300001", LAL, *counts], ["0022300001", BOS, *counts]],
        ["GAME_ID", "TEAM_ID", "OFF_RATING", "DEF_RATING", "NET_RATING", "PACE", "POSS"],
        [],
        player_headers,
        [
            ["0022300001", LAL, 201939, "34:30", "G", *counts, 12],
            ["0022300001", BOS, 202681, "", "", *counts, 0],  # DNP — excluded
        ],
        ["GAME_ID", "PLAYER_ID", "USG_PCT"],
        [["0022300001", 201939, 0.28]],
    )
    df = parse_player_game_stats(raw, home_team_id=LAL)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["player_id"] == 201939
    assert row["started"]
    assert row["min"] == 34.5
    assert row["usage_rate"] == 0.28
    assert row["opponent_team_id"] == BOS


def test_parse_play_by_play() -> None:
    raw = _result_set(
        "PlayByPlay",
        [
            "GAME_ID",
            "EVENTNUM",
            "PERIOD",
            "PCTIMESTRING",
            "EVENTMSGTYPE",
            "EVENTMSGACTIONTYPE",
            "HOMEDESCRIPTION",
            "VISITORDESCRIPTION",
            "NEUTRALDESCRIPTION",
            "SCORE",
            "PLAYER1_ID",
            "PLAYER1_TEAM_ID",
            "PLAYER2_ID",
            "PLAYER3_ID",
        ],
        [
            [
                "0022300001",
                2,
                1,
                "11:34",
                1,
                5,
                "Made shot",
                None,
                None,
                "2 - 0",
                201939,
                LAL,
                0,
                0,
            ],
        ],
    )
    df = parse_play_by_play(raw)
    row = df.iloc[0]
    assert row["event_num"] == 2
    assert row["seconds_remaining_period"] == 11 * 60 + 34
    assert row["description"] == "Made shot"
    assert row["away_score"] == 2
    assert row["home_score"] == 0
    assert row["player1_id"] == 201939
    assert row["player2_id"] is None  # 0 sentinel → None


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
