"""Feature humanizer — explainability.md Prompt 3 + §6.

A registry mapping every feature the game-win explanations can reference to a
``{display_label, description, value_formatter, unit}`` entry, plus a function that decorates
raw ``Contribution``/``Explanation`` objects into the human-readable form the frontend renders
("**+6%** from a **2-day rest advantage**" instead of ``days_rest=2``).

Covers the team-game features the game-win/margin/total heads read
(``models/game_prediction/win_prob.py::MODEL_FEATURE_COLUMNS``) and, since T3.10, the
player-game features the props heads read (``models/props/regressor.py::MODEL_FEATURE_COLUMNS``).
The coverage test asserts this registry is exactly the union of those two sets.
``features_game_state`` entries land alongside the live head in T4.1.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nbaforecast.explain.schema import Contribution, Explanation


@dataclass(slots=True, frozen=True)
class FeatureMeta:
    """One feature's entry in the humanizer registry."""

    display_label: str
    description: str
    unit: str
    value_formatter: Callable[[Any], str]


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _na_guarded(fn: Callable[[Any], str]) -> Callable[[Any], str]:
    def wrapped(value: Any) -> str:
        return "N/A" if _is_missing(value) else fn(value)

    return wrapped


@_na_guarded
def _format_days(value: Any) -> str:
    days = round(float(value))
    return f"{days} day" if days == 1 else f"{days} days"


@_na_guarded
def _format_count(value: Any) -> str:
    return str(round(float(value)))


@_na_guarded
def _format_km(value: Any) -> str:
    return f"{float(value):.0f} km"


@_na_guarded
def _format_hours_shift(value: Any) -> str:
    hours = float(value)
    sign = "+" if hours >= 0 else ""
    return f"{sign}{hours:.0f}h"


@_na_guarded
def _format_signed_rating(value: Any) -> str:
    rating = float(value)
    sign = "+" if rating >= 0 else ""
    return f"{sign}{rating:.1f}"


@_na_guarded
def _format_pace(value: Any) -> str:
    return f"{float(value):.1f} poss/48"


@_na_guarded
def _format_percent(value: Any) -> str:
    return f"{float(value) * 100:.0f}%"


@_na_guarded
def _format_elo(value: Any) -> str:
    return f"{float(value):.0f}"


@_na_guarded
def _format_signed_elo(value: Any) -> str:
    elo = float(value)
    sign = "+" if elo >= 0 else ""
    return f"{sign}{elo:.0f}"


@_na_guarded
def _format_signed_days(value: Any) -> str:
    days = float(value)
    sign = "+" if days >= 0 else ""
    return f"{sign}{days:.0f}d"


@_na_guarded
def _format_bool(value: Any) -> str:
    return "yes" if bool(value) else "no"


@_na_guarded
def _format_stat(value: Any) -> str:
    """Per-game counting stat / average to one decimal (e.g. ``24.3``)."""
    return f"{float(value):.1f}"


@_na_guarded
def _format_minutes(value: Any) -> str:
    return f"{float(value):.1f} min"


@_na_guarded
def _format_signed_minutes(value: Any) -> str:
    minutes = float(value)
    sign = "+" if minutes >= 0 else ""
    return f"{sign}{minutes:.1f} min"


@_na_guarded
def _format_rating_plain(value: Any) -> str:
    """An unsigned rating (e.g. an opponent's defensive rating around 110)."""
    return f"{float(value):.1f}"


FEATURE_REGISTRY: dict[str, FeatureMeta] = {
    "days_rest": FeatureMeta(
        "Days of rest", "Days since the team's last game.", "days", _format_days
    ),
    "is_back_to_back": FeatureMeta(
        "Back-to-back",
        "Playing with zero days of rest since the last game.",
        "boolean",
        _format_bool,
    ),
    "games_last_7d": FeatureMeta(
        "Games in last 7 days",
        "Schedule density: games played in the trailing week.",
        "count",
        _format_count,
    ),
    "games_last_14d": FeatureMeta(
        "Games in last 14 days",
        "Schedule density: games played in the trailing two weeks.",
        "count",
        _format_count,
    ),
    "travel_distance_km": FeatureMeta(
        "Travel distance",
        "Great-circle distance from the team's previous game to this one.",
        "km",
        _format_km,
    ),
    "tz_shift": FeatureMeta(
        "Time zone shift",
        "Time zone change since the team's last game.",
        "hours",
        _format_hours_shift,
    ),
    "roll5_net_rating": FeatureMeta(
        "Net rating, last 5 games",
        "Point differential per 100 possessions, last 5 games.",
        "rating",
        _format_signed_rating,
    ),
    "roll10_net_rating": FeatureMeta(
        "Net rating, last 10 games",
        "Point differential per 100 possessions, last 10 games.",
        "rating",
        _format_signed_rating,
    ),
    "roll5_off_rating": FeatureMeta(
        "Offensive rating, last 5 games",
        "Points scored per 100 possessions, last 5 games.",
        "rating",
        _format_signed_rating,
    ),
    "roll10_off_rating": FeatureMeta(
        "Offensive rating, last 10 games",
        "Points scored per 100 possessions, last 10 games.",
        "rating",
        _format_signed_rating,
    ),
    "roll5_def_rating": FeatureMeta(
        "Defensive rating, last 5 games",
        "Points allowed per 100 possessions, last 5 games.",
        "rating",
        _format_signed_rating,
    ),
    "roll10_def_rating": FeatureMeta(
        "Defensive rating, last 10 games",
        "Points allowed per 100 possessions, last 10 games.",
        "rating",
        _format_signed_rating,
    ),
    "roll5_pace": FeatureMeta(
        "Pace, last 5 games", "Possessions per 48 minutes, last 5 games.", "pace", _format_pace
    ),
    "roll10_pace": FeatureMeta(
        "Pace, last 10 games", "Possessions per 48 minutes, last 10 games.", "pace", _format_pace
    ),
    "season_off_rating": FeatureMeta(
        "Offensive rating, season to date",
        "Points scored per 100 possessions so far this season.",
        "rating",
        _format_signed_rating,
    ),
    "season_def_rating": FeatureMeta(
        "Defensive rating, season to date",
        "Points allowed per 100 possessions so far this season.",
        "rating",
        _format_signed_rating,
    ),
    "season_net_rating": FeatureMeta(
        "Net rating, season to date",
        "Point differential per 100 possessions so far this season.",
        "rating",
        _format_signed_rating,
    ),
    "season_pace": FeatureMeta(
        "Pace, season to date",
        "Possessions per 48 minutes so far this season.",
        "pace",
        _format_pace,
    ),
    "win_pct_to_date": FeatureMeta(
        "Win percentage, season to date",
        "Fraction of games won so far this season.",
        "percent",
        _format_percent,
    ),
    "elo": FeatureMeta(
        "Elo rating", "The team's own power rating heading into tonight.", "elo points", _format_elo
    ),
    "opp_adj_net_rating": FeatureMeta(
        "Opponent-adjusted net rating",
        "Season net rating adjusted for the strength of opponents faced so far.",
        "rating",
        _format_signed_rating,
    ),
    "h2h_record": FeatureMeta(
        "Head-to-head record",
        "Win percentage in prior meetings against tonight's opponent.",
        "percent",
        _format_percent,
    ),
    "h2h_avg_margin": FeatureMeta(
        "Head-to-head average margin",
        "Average scoring margin in prior meetings against tonight's opponent.",
        "rating",
        _format_signed_rating,
    ),
    "rest_advantage": FeatureMeta(
        "Rest advantage",
        "Days of rest minus the opponent's days of rest.",
        "days",
        _format_signed_days,
    ),
    "rating_diff": FeatureMeta(
        "Net rating advantage",
        "Season net rating minus the opponent's season net rating.",
        "rating",
        _format_signed_rating,
    ),
    "elo_diff": FeatureMeta(
        "Elo advantage",
        "Elo rating minus the opponent's Elo rating.",
        "elo points",
        _format_signed_elo,
    ),
    "is_home": FeatureMeta(
        "Home court", "Whether the team is playing at home tonight.", "boolean", _format_bool
    ),
}


# ── Player-game (props) features ──────────────────────────────────────────────────────────────
# Registered here so props explanations (models/props/regressor.py, over features_player_game)
# humanize the same way game-win explanations do. Built programmatically for the repetitive
# per-stat rolling/season entries; see features/player_game.py's FEATURE_COLUMNS.

_PROPS_STAT_LABELS = {
    "pts": "points",
    "reb": "rebounds",
    "ast": "assists",
    "fg3m": "three-pointers made",
}

for _stat, _label in _PROPS_STAT_LABELS.items():
    for _window in (5, 10, 15):
        FEATURE_REGISTRY[f"roll{_window}_{_stat}"] = FeatureMeta(
            f"{_label.capitalize()}, last {_window} games",
            f"Average {_label} over the player's last {_window} games.",
            _label,
            _format_stat,
        )
    FEATURE_REGISTRY[f"season_avg_{_stat}"] = FeatureMeta(
        f"{_label.capitalize()}, season average",
        f"Average {_label} per game so far this season.",
        _label,
        _format_stat,
    )

for _stat, _label in (("pts", "points"), ("reb", "rebounds"), ("ast", "assists")):
    FEATURE_REGISTRY[f"roll10_std_{_stat}"] = FeatureMeta(
        f"{_label.capitalize()} volatility, last 10 games",
        f"Standard deviation of {_label} over the last 10 games (game-to-game consistency).",
        _label,
        _format_stat,
    )

FEATURE_REGISTRY.update(
    {
        "roll_minutes": FeatureMeta(
            "Minutes, recent average",
            "Average minutes played in the player's recent games.",
            "minutes",
            _format_minutes,
        ),
        "usage_rate": FeatureMeta(
            "Usage rate",
            "Share of the team's possessions the player uses while on the court.",
            "percent",
            _format_percent,
        ),
        "minutes_trend": FeatureMeta(
            "Minutes trend",
            "Recent minutes minus the longer-baseline minutes — a rising or falling role.",
            "minutes",
            _format_signed_minutes,
        ),
        "opp_def_rating": FeatureMeta(
            "Opponent defensive rating",
            "Points the opponent allows per 100 possessions.",
            "rating",
            _format_rating_plain,
        ),
        "opp_pace": FeatureMeta(
            "Opponent pace",
            "Opponent possessions per 48 minutes — more possessions mean more counting stats.",
            "pace",
            _format_pace,
        ),
        "opp_pos_def": FeatureMeta(
            "Opponent positional defense",
            "Points the opponent allows to the player's position.",
            "rating",
            _format_rating_plain,
        ),
    }
)


def humanize_contribution(contribution: Contribution) -> Contribution:
    """Decorate one raw ``Contribution`` with its registry entry's display label/formatted value.

    Raises ``KeyError`` for a feature with no registry entry — that's a real bug (a feature was
    added without a humanizer entry), not something to silently degrade past (engineering-
    standards.md §2: pipelines fail loud). The coverage test ensures this never fires for any
    feature the game-win head actually produces.
    """
    try:
        meta = FEATURE_REGISTRY[contribution.feature]
    except KeyError as exc:
        raise RuntimeError(
            f"humanizer has no registry entry for feature {contribution.feature!r}; "
            "add it to FEATURE_REGISTRY in humanizer.py"
        ) from exc
    return contribution.model_copy(
        update={
            "display_label": meta.display_label,
            "formatted_value": meta.value_formatter(contribution.raw_value),
        }
    )


def humanize(explanation: Explanation) -> Explanation:
    """Decorate every contribution in ``explanation`` with its human-readable form."""
    return explanation.model_copy(
        update={"contributions": [humanize_contribution(c) for c in explanation.contributions]}
    )
