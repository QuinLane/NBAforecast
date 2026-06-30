"""Shared synthetic-league generator for tests that need a realistic, multi-team, multi-season
silver dataset (not pytest-collected — no ``test_`` prefix).

A deterministic round-robin league: every team plays every other team home + away, each season.
Skill is correlated with ``team_id`` and a +2.5 home-court boost is baked in
(``home_net ~ Normal(home_id - away_id + 2.5, 5)``) so Elo, home-court, and other
skill/venue-sensitive features carry genuine, checkable signal rather than pure noise.
"""

import numpy as np
import pandas as pd

DEFAULT_N_TEAMS = 6
DEFAULT_SEASONS = (("2022-23", 2022), ("2023-24", 2023))


def build_synthetic_league(
    n_teams: int = DEFAULT_N_TEAMS,
    seasons: tuple[tuple[str, int], ...] = DEFAULT_SEASONS,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns ``(games, team_game_stats, teams)`` silver-shaped DataFrames."""
    rng = np.random.default_rng(seed)
    team_ids = list(range(1, n_teams + 1))
    teams = pd.DataFrame(
        {
            "team_id": team_ids,
            "arena_lat": rng.uniform(25, 47, n_teams),
            "arena_lon": rng.uniform(-122, -71, n_teams),
        }
    )

    games_rows: list[dict[str, object]] = []
    stats_rows: list[dict[str, object]] = []
    game_counter = 0
    for season, season_start_year in seasons:
        game_date = pd.Timestamp(f"{season_start_year}-10-20")
        for home in team_ids:
            for away in team_ids:
                if home == away:
                    continue
                game_counter += 1
                game_id = f"G{game_counter}"
                game_date = game_date + pd.Timedelta(2, unit="D")
                # +2.5 home-court boost (modeling.md §3's own baseline figure) on top of the
                # team_id-correlated skill gap, so a real home-court effect exists to detect.
                home_net = float(rng.normal((home - away) + 2.5, 5))
                pace = float(rng.normal(98, 3))
                games_rows.append(
                    {
                        "game_id": game_id,
                        "season": season,
                        "season_start_year": season_start_year,
                        "game_date": game_date,
                        "home_team_id": home,
                        "away_team_id": away,
                        "home_score": round(100 + home_net),
                        "away_score": round(100 - home_net),
                        "status": "final",
                    }
                )
                stats_rows.append(
                    {
                        "game_id": game_id,
                        "team_id": home,
                        "opponent_team_id": away,
                        "is_home": True,
                        "off_rating": 110 + home_net / 2,
                        "def_rating": 110 - home_net / 2,
                        "net_rating": home_net,
                        "pace": pace,
                    }
                )
                stats_rows.append(
                    {
                        "game_id": game_id,
                        "team_id": away,
                        "opponent_team_id": home,
                        "is_home": False,
                        "off_rating": 110 - home_net / 2,
                        "def_rating": 110 + home_net / 2,
                        "net_rating": -home_net,
                        "pace": pace,
                    }
                )
    return pd.DataFrame(games_rows), pd.DataFrame(stats_rows), teams
