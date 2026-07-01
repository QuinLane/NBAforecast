"""Shared synthetic player-game generator for tests needing a realistic, multi-player,
multi-season silver dataset (not pytest-collected — no ``test_`` prefix).

Builds on top of ``_synthetic_league.py``'s team/game generator: each team fields a fixed
5-player rotation (one player per position: G/G/F/F/C) whose per-game stat lines are drawn from a
player-level skill anchor (drifting per season, same rationale as the team-skill drift in
``_synthetic_league.py``) plus the team's own game-level scoring context, so recent-form features
carry genuine, checkable signal.
"""

import numpy as np
import pandas as pd

from tests.ml._synthetic_league import DEFAULT_SEASONS, build_synthetic_league

POSITIONS = ("G", "G", "F", "F", "C")
PLAYERS_PER_TEAM = len(POSITIONS)


def build_synthetic_player_league(
    n_teams: int = 8,
    seasons: tuple[tuple[str, int], ...] = DEFAULT_SEASONS,
    seed: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns ``(games, team_game_stats, teams, player_game_stats, players)``."""
    games, team_game_stats, teams = build_synthetic_league(n_teams=n_teams, seasons=seasons)
    rng = np.random.default_rng(seed)

    team_ids = teams["team_id"].tolist()
    player_ids = {
        team_id: [team_id * 100 + slot for slot in range(PLAYERS_PER_TEAM)] for team_id in team_ids
    }
    player_rows = []
    for team_id in team_ids:
        for player_id, position in zip(player_ids[team_id], POSITIONS, strict=True):
            player_rows.append(
                {
                    "player_id": player_id,
                    "position": position,
                    "full_name": f"Player {player_id}",
                }
            )
    players = pd.DataFrame(player_rows)

    # Per-player base skill (points-per-36 anchor), drifting each season like team skill.
    skill = {
        pid: 10.0 + 4.0 * slot
        for team_id in team_ids
        for slot, pid in enumerate(player_ids[team_id])
    }

    player_stat_rows = []
    for season, _season_start_year in seasons:
        skill = {pid: max(2.0, val + rng.normal(0, 1.0)) for pid, val in skill.items()}
        season_games = team_game_stats.merge(
            games[["game_id", "season"]], on="game_id", how="inner"
        )
        season_games = season_games.loc[season_games["season"] == season]

        for _, team_row in season_games.iterrows():
            game_id = team_row["game_id"]
            team_id = team_row["team_id"]
            opponent_team_id = team_row["opponent_team_id"]
            is_home = team_row["is_home"]
            pace_factor = float(team_row["pace"]) / 98.0

            for player_id in player_ids[team_id]:
                base = skill[player_id] * pace_factor
                minutes = float(np.clip(rng.normal(28, 4), 8, 40))
                pts = max(0, round(rng.normal(base, 3)))
                reb = max(0, round(rng.normal(base * 0.35, 2)))
                ast = max(0, round(rng.normal(base * 0.25, 1.5)))
                fg3m = max(0, round(rng.normal(base * 0.15, 1.2)))
                player_stat_rows.append(
                    {
                        "game_id": game_id,
                        "player_id": player_id,
                        "team_id": team_id,
                        "opponent_team_id": opponent_team_id,
                        "is_home": bool(is_home),
                        "min": minutes,
                        "pts": pts,
                        "reb": reb,
                        "ast": ast,
                        "fg3m": fg3m,
                        "usage_rate": float(np.clip(rng.normal(0.20, 0.05), 0.05, 0.4)),
                    }
                )

    player_game_stats = pd.DataFrame(player_stat_rows)
    return games, team_game_stats, teams, player_game_stats, players
