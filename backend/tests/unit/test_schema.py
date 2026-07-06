"""Assert the SQLAlchemy schema matches data-model.md §§2, 3, 4, 5 exactly.

This is the canonical guard for the data model: if a column, key, index, or constraint drifts
from the doc, this fails.
"""

from nbaforecast.storage import models  # noqa: F401  (registers tables)
from nbaforecast.storage.database import Base
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

# Box-score counting columns shared by team_game_stats and player_game_stats.
_COUNTING = {
    "pts",
    "reb",
    "oreb",
    "dreb",
    "ast",
    "stl",
    "blk",
    "tov",
    "pf",
    "fgm",
    "fga",
    "fg3m",
    "fg3a",
    "ftm",
    "fta",
}

# Business columns per table (timestamps appended below per the row-mutability rule).
_BUSINESS_COLUMNS: dict[str, set[str]] = {
    "teams": {
        "team_id",
        "abbreviation",
        "full_name",
        "city",
        "nickname",
        "conference",
        "division",
        "arena_name",
        "arena_lat",
        "arena_lon",
    },
    "players": {
        "player_id",
        "full_name",
        "first_name",
        "last_name",
        "position",
        "height_inches",
        "weight_lbs",
        "birthdate",
        "is_active",
    },
    "games": {
        "game_id",
        "season",
        "season_start_year",
        "season_type",
        "game_date",
        "game_datetime",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "status",
        "num_periods",
    },
    "team_game_stats": {
        "game_id",
        "team_id",
        "opponent_team_id",
        "is_home",
        "off_rating",
        "def_rating",
        "net_rating",
        "pace",
        "possessions",
    }
    | _COUNTING,
    "player_game_stats": {
        "game_id",
        "player_id",
        "team_id",
        "opponent_team_id",
        "is_home",
        "started",
        "min",
        "plus_minus",
        "usage_rate",
    }
    | _COUNTING,
    "play_by_play": {
        "game_id",
        "event_num",
        "period",
        "pc_time",
        "seconds_remaining_period",
        "action_type",
        "sub_type",
        "description",
        "home_score",
        "away_score",
        "player1_id",
        "player2_id",
        "player3_id",
        "team_id",
    },
    "shots": {
        "shot_id",
        "game_id",
        "event_num",
        "player_id",
        "team_id",
        "period",
        "seconds_remaining_period",
        "loc_x",
        "loc_y",
        "shot_distance",
        "shot_zone",
        "shot_zone_area",
        "shot_zone_range",
        "shot_type",
        "action_type",
        "made",
        "location_reliable",
    },
    "possessions": {
        "possession_id",
        "game_id",
        "period",
        "start_seconds",
        "end_seconds",
        "offense_team_id",
        "defense_team_id",
        "points",
        "off_player_ids",
        "def_player_ids",
    },
    "player_rapm": {
        "player_id",
        "as_of_date",
        "window",
        "orapm",
        "drapm",
        "rapm",
        "possessions",
    },
    "predictions": {
        "prediction_id",
        "game_id",
        "player_id",
        "head",
        "value",
        "interval_low",
        "interval_high",
        "market",
        "mlflow_run_id",
        "feature_version",
        "explanation",
    },
    "live_win_prob_timeline": {
        "game_id",
        "event_num",
        "period",
        "seconds_remaining_game",
        "score_diff",
        "win_prob",
    },
    "ingested_games": {"game_id", "entities_done", "ingested_at"},
    "features_team_game": {
        "game_id",
        "team_id",
        "opponent_team_id",
        "season",
        "season_start_year",
        "game_date",
        "is_home",
        "days_rest",
        "is_back_to_back",
        "games_last_7d",
        "games_last_14d",
        "travel_distance_km",
        "tz_shift",
        "roll5_net_rating",
        "roll10_net_rating",
        "roll5_off_rating",
        "roll10_off_rating",
        "roll5_def_rating",
        "roll10_def_rating",
        "roll5_pace",
        "roll10_pace",
        "season_off_rating",
        "season_def_rating",
        "season_net_rating",
        "season_pace",
        "win_pct_to_date",
        "elo",
        "opp_adj_net_rating",
        "h2h_record",
        "h2h_avg_margin",
        "rest_advantage",
        "rating_diff",
        "elo_diff",
        "team_orapm",
        "team_drapm",
        "feature_version",
    },
    "features_player_game": {
        "game_id",
        "player_id",
        "team_id",
        "opponent_team_id",
        "season",
        "season_start_year",
        "game_date",
        "is_home",
        "days_rest",
        "is_back_to_back",
        "roll5_pts",
        "roll10_pts",
        "roll15_pts",
        "roll10_std_pts",
        "roll5_reb",
        "roll10_reb",
        "roll15_reb",
        "roll10_std_reb",
        "roll5_ast",
        "roll10_ast",
        "roll15_ast",
        "roll10_std_ast",
        "roll5_fg3m",
        "roll10_fg3m",
        "roll15_fg3m",
        "season_avg_pts",
        "season_avg_reb",
        "season_avg_ast",
        "season_avg_fg3m",
        "roll_minutes",
        "usage_rate",
        "minutes_trend",
        "opp_def_rating",
        "opp_pace",
        "opp_pos_def",
        "player_rapm",
        "feature_version",
    },
    "features_game_state": {
        "game_id",
        "event_num",
        "score_diff",
        "seconds_remaining_game",
        "period",
        "is_clutch",
        "offense_has_ball",
        "possession_arrow",
        "pre_game_win_prob",
        "timeouts_remaining_home",
        "timeouts_remaining_away",
        "in_bonus",
        "home_fouls",
        "away_fouls",
        "home_win",
        "feature_version",
    },
}

# created_at + updated_at on mutable rows; created_at only on append-only rows.
_MUTABLE = {"teams", "players", "games", "team_game_stats", "player_game_stats"}
_CREATED_ONLY = {
    "play_by_play",
    "shots",
    "possessions",
    "player_rapm",
    "predictions",
    "live_win_prob_timeline",
    "features_team_game",
    "features_player_game",
    "features_game_state",
}

_EXPECTED_PK: dict[str, tuple[str, ...]] = {
    "teams": ("team_id",),
    "players": ("player_id",),
    "games": ("game_id",),
    "team_game_stats": ("game_id", "team_id"),
    "player_game_stats": ("game_id", "player_id"),
    "play_by_play": ("game_id", "event_num"),
    "shots": ("shot_id",),
    "possessions": ("possession_id",),
    "player_rapm": ("player_id", "as_of_date", "window"),
    "predictions": ("prediction_id",),
    "live_win_prob_timeline": ("game_id", "event_num"),
    "ingested_games": ("game_id",),
    "features_team_game": ("game_id", "team_id"),
    "features_player_game": ("game_id", "player_id"),
    "features_game_state": ("game_id", "event_num"),
}

# Index definitions expected (frozenset of columns per table), single + composite.
_EXPECTED_INDEX_COLS: dict[str, set[frozenset[str]]] = {
    "games": {
        frozenset({"season_start_year"}),
        frozenset({"game_date"}),
        frozenset({"home_team_id"}),
        frozenset({"away_team_id"}),
    },
    "team_game_stats": {frozenset({"team_id"})},
    "player_game_stats": {frozenset({"player_id"}), frozenset({"team_id"})},
    "play_by_play": {frozenset({"game_id", "period"})},
    "shots": {frozenset({"game_id"}), frozenset({"player_id"}), frozenset({"shot_zone"})},
    "possessions": {frozenset({"game_id"})},
    "player_rapm": {frozenset({"player_id"}), frozenset({"as_of_date"})},
    "predictions": {frozenset({"game_id"})},
    "live_win_prob_timeline": {frozenset({"game_id"})},
    "features_team_game": {
        frozenset({"game_id"}),
        frozenset({"team_id"}),
        frozenset({"season_start_year"}),
    },
    "features_player_game": {
        frozenset({"game_id"}),
        frozenset({"player_id"}),
        frozenset({"season_start_year"}),
    },
    "features_game_state": {frozenset({"game_id"})},
}


def _expected_columns(table: str) -> set[str]:
    cols = set(_BUSINESS_COLUMNS[table])
    if table in _MUTABLE:
        cols |= {"created_at", "updated_at"}
    elif table in _CREATED_ONLY:
        cols |= {"created_at"}
    return cols


def test_all_tables_present_and_no_extras() -> None:
    assert set(Base.metadata.tables) == set(_BUSINESS_COLUMNS)


def test_columns_match_doc() -> None:
    for name, table in Base.metadata.tables.items():
        assert {c.name for c in table.columns} == _expected_columns(name), name


def test_primary_keys_match_doc() -> None:
    for name, table in Base.metadata.tables.items():
        pk = tuple(c.name for c in table.primary_key.columns)
        assert pk == _EXPECTED_PK[name], name


def test_indexes_match_doc() -> None:
    for name, table in Base.metadata.tables.items():
        actual = {frozenset(c.name for c in idx.columns) for idx in table.indexes}
        assert actual == _EXPECTED_INDEX_COLS.get(name, set()), name


def test_foreign_keys() -> None:
    def fk_targets(table_name: str) -> set[tuple[str, str]]:
        table = Base.metadata.tables[table_name]
        targets: set[tuple[str, str]] = set()
        for c in table.constraints:
            if isinstance(c, ForeignKeyConstraint):
                for fk in c.elements:
                    targets.add((fk.parent.name, fk.column.table.name))
        return targets

    assert fk_targets("games") == {("home_team_id", "teams"), ("away_team_id", "teams")}
    assert ("game_id", "games") in fk_targets("team_game_stats")
    assert ("team_id", "teams") in fk_targets("team_game_stats")
    assert ("player_id", "players") in fk_targets("player_game_stats")
    assert ("player_id", "players") in fk_targets("shots")
    assert fk_targets("possessions") == {("game_id", "games")}
    assert fk_targets("player_rapm") == {("player_id", "players")}
    assert fk_targets("features_team_game") == {("game_id", "games"), ("team_id", "teams")}
    assert fk_targets("features_player_game") == {("game_id", "games"), ("player_id", "players")}
    assert fk_targets("features_game_state") == {("game_id", "games")}


def test_games_check_and_shots_unique() -> None:
    games = Base.metadata.tables["games"]
    checks = [c for c in games.constraints if isinstance(c, CheckConstraint)]
    assert any("home_team_id" in str(c.sqltext) for c in checks)

    shots = Base.metadata.tables["shots"]
    uniques = [c for c in shots.constraints if isinstance(c, UniqueConstraint)]
    assert any({col.name for col in c.columns} == {"game_id", "event_num"} for c in uniques)


def test_id_type_conventions() -> None:
    """game_id is VARCHAR(20); team/player ids are BIGINT (data-model §1)."""
    games = Base.metadata.tables["games"]
    assert games.c.game_id.type.length == 20  # type: ignore[attr-defined]
    teams = Base.metadata.tables["teams"]
    assert teams.c.team_id.type.python_type is int
