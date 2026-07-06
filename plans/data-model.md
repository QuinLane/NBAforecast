# Data Model — Canonical Schema

> **Goal:** The single source of truth for every table — columns, types, keys, indexes — that the
> build prompts in [data-pipeline.md](data-pipeline.md), [feature-engineering.md](feature-engineering.md),
> [rapm.md](rapm.md), and [live-system.md](live-system.md) implement.
> Parent: [master-plan.md](master-plan.md).

---

## 1. Conventions

- **Naming:** snake_case, plural table names; `*_id` for keys.
- **Timestamps:** `created_at`/`updated_at` `TIMESTAMPTZ DEFAULT now()` on mutable tables.
- **IDs:** `team_id`/`player_id` are NBA integers → `BIGINT`. `game_id` is the NBA string with
  leading zeros (e.g., `"0022300001"`) → `VARCHAR(20)` (§7 — preserved, not cast to int).
- **Seasons:** stored two ways — `season VARCHAR(7)` (`"2023-24"`) for display + `season_start_year
  INT` (`2023`) for filtering/sorting and `lookback_seasons` windows.
- **Idempotency:** every silver/gold table has a natural composite key; loads are upserts on it.
- **Storage split:** silver + gold live in **Postgres** (serving) and **Parquet** (training,
  partitioned by `season_start_year`). Large tables (`play_by_play`, `shots`, `possessions`) are
  Parquet-primary but also kept in Postgres for serving (shot charts, etc.).
- **Money column note:** none — no financial data.

## 2. Reference / dimension tables

### `teams`
| Column | Type | Notes |
|--------|------|-------|
| team_id | BIGINT PK | NBA team id |
| abbreviation | VARCHAR(5) | e.g. LAL |
| full_name | VARCHAR | |
| city, nickname | VARCHAR | |
| conference, division | VARCHAR | |
| arena_name | VARCHAR | current arena |
| arena_lat, arena_lon | NUMERIC | for travel features (current arena; historical relocation ignored in v1) |
| created_at, updated_at | TIMESTAMPTZ | |

### `players`
| Column | Type | Notes |
|--------|------|-------|
| player_id | BIGINT PK | |
| full_name, first_name, last_name | VARCHAR | |
| position | VARCHAR | |
| height_inches, weight_lbs | INT NULL | optional |
| birthdate | DATE NULL | optional |
| is_active | BOOLEAN | |
| created_at, updated_at | TIMESTAMPTZ | |

## 3. Core silver tables

### `games`
| Column | Type | Notes |
|--------|------|-------|
| game_id | VARCHAR(20) PK | NBA string id |
| season | VARCHAR(7) | "2023-24" |
| season_start_year | INT | 2023; **indexed** |
| season_type | VARCHAR | Regular Season / Playoffs / Play-In / Preseason |
| game_date | DATE | **indexed** |
| game_datetime | TIMESTAMPTZ | tip-off — the point-in-time boundary |
| home_team_id, away_team_id | BIGINT FK→teams | **indexed**; CHECK home ≠ away |
| home_score, away_score | INT NULL | null until final |
| status | VARCHAR | scheduled / live / final |
| num_periods | INT | 4, >4 = OT |
| created_at, updated_at | TIMESTAMPTZ | |

### `team_game_stats` — PK (game_id, team_id)
| Column | Type | Notes |
|--------|------|-------|
| game_id | VARCHAR(20) FK→games | |
| team_id | BIGINT FK→teams | **indexed** |
| opponent_team_id | BIGINT | |
| is_home | BOOLEAN | |
| pts, reb, oreb, dreb, ast, stl, blk, tov, pf | INT | |
| fgm, fga, fg3m, fg3a, ftm, fta | INT | |
| off_rating, def_rating, net_rating, pace | NUMERIC | |
| possessions | NUMERIC | |
| created_at, updated_at | TIMESTAMPTZ | |

### `player_game_stats` — PK (game_id, player_id)
| Column | Type | Notes |
|--------|------|-------|
| game_id | VARCHAR(20) FK→games | |
| player_id | BIGINT FK→players | **indexed** |
| team_id, opponent_team_id | BIGINT | **indexed** (team_id) |
| is_home, started | BOOLEAN | |
| min | NUMERIC | minutes (fractional) |
| pts, reb, oreb, dreb, ast, stl, blk, tov, pf | INT | |
| fgm, fga, fg3m, fg3a, ftm, fta | INT | |
| plus_minus | INT | |
| usage_rate | NUMERIC NULL | computed if available |
| created_at, updated_at | TIMESTAMPTZ | |

### `play_by_play` — PK (game_id, event_num)
| Column | Type | Notes |
|--------|------|-------|
| game_id | VARCHAR(20) FK→games | **indexed (game_id, period)** |
| event_num | INT | order within game |
| period | INT | |
| pc_time | VARCHAR | raw game clock "MM:SS" |
| seconds_remaining_period | INT | parsed |
| action_type, sub_type | TEXT | v3 action strings (replaced v2 int event codes when the NBA retired v2 endpoints; migration 0003) |
| description | TEXT | |
| home_score, away_score | INT | running score |
| player1_id, player2_id, player3_id | BIGINT NULL | |
| team_id | BIGINT NULL | primary player's team |
| created_at | TIMESTAMPTZ | |

### `shots` — surrogate PK + UNIQUE(game_id, event_num)
| Column | Type | Notes |
|--------|------|-------|
| shot_id | BIGSERIAL PK | |
| game_id | VARCHAR(20) FK→games | **indexed** |
| event_num | INT | links to pbp |
| player_id | BIGINT FK→players | **indexed** |
| team_id | BIGINT | |
| period | INT | |
| seconds_remaining_period | INT | |
| loc_x, loc_y | INT | court coords (tenths of feet) |
| shot_distance | INT | feet |
| shot_zone, shot_zone_area, shot_zone_range | VARCHAR | **indexed (shot_zone)** |
| shot_type | VARCHAR | 2PT / 3PT |
| action_type | VARCHAR | Jump Shot / Layup / … |
| made | BOOLEAN | |
| location_reliable | BOOLEAN | **false for 1996-00** (data caveat, [data-pipeline.md §1](data-pipeline.md)) |
| created_at | TIMESTAMPTZ | |

### `possessions` — surrogate PK
| Column | Type | Notes |
|--------|------|-------|
| possession_id | BIGSERIAL PK | |
| game_id | VARCHAR(20) FK→games | **indexed** |
| period | INT | |
| start_seconds, end_seconds | INT | game clock |
| offense_team_id, defense_team_id | BIGINT | |
| points | INT | scored on this possession |
| off_player_ids, def_player_ids | BIGINT[] (5 each) | on-court lineups (§7 — array vs join-table decision) |
| created_at | TIMESTAMPTZ | |

Source of the RAPM stint matrix ([rapm.md](rapm.md)).

## 4. Gold / feature tables

> **Built in T2.3, not T1.1.** These tables' columns are finalized in
> [feature-engineering.md §4](feature-engineering.md) and their SQLAlchemy models + Alembic
> migration are owned by feature-engineering Prompt 5 (T2.3). T1.1 implements only §§2, 3, 5
> (the fully-specified reference, silver, and serving/model tables). Their Parquet schemas
> likewise ship with T2.3.

Columns follow the catalog in [feature-engineering.md §4](feature-engineering.md). Rolling features
use the naming convention **`roll{N}_{metric}`** (e.g., `roll10_net_rating`). All carry
`feature_version VARCHAR` and `created_at`.

### `features_team_game` — PK (game_id, team_id)
`opponent_team_id, season, season_start_year, game_date, is_home, days_rest, is_back_to_back,
games_last_7d, games_last_14d, travel_distance_km, tz_shift, roll5_net_rating, roll10_net_rating,
roll5_off_rating, roll10_off_rating, roll5_def_rating, roll10_def_rating, roll5_pace, roll10_pace,
season_off_rating, season_def_rating, season_net_rating, season_pace, win_pct_to_date, elo,
opp_adj_net_rating, h2h_record, h2h_avg_margin, rest_advantage, rating_diff, elo_diff, team_orapm,
team_drapm` (last two from RAPM snapshots — **NULL until T3.9** wires RAPM into features). Index
(team_id), (game_id), (season_start_year). Finalized in T2.3 against the implementation in
`features/team_game.py` (T2.2) — this list supersedes feature-engineering.md §4's prose summary
where the two differ (`opp_adj_net_rating`, `season_pace` were missing there).

### `features_player_game` — PK (game_id, player_id)
`is_home, days_rest, is_back_to_back, roll5_pts, roll10_pts, roll15_pts, roll5_reb, roll10_reb,
roll15_reb, roll5_ast, …, roll5_fg3m, …, std10_pts, …, season_avg_pts, season_avg_reb,
season_avg_ast, season_avg_fg3m, roll_minutes, usage_rate, minutes_trend, opp_def_rating, opp_pace,
opp_pos_def, player_rapm`. Index (player_id), (game_id).

### `features_game_state` — PK (game_id, event_num)
`feature_version, score_diff, seconds_remaining_game, period, is_clutch, offense_has_ball,
possession_arrow, pre_game_win_prob, timeouts_remaining_home, timeouts_remaining_away, in_bonus,
home_fouls, away_fouls, home_win (label)`. Index (game_id).

## 5. Model / serving tables

### `player_rapm` — PK (player_id, as_of_date, window)
| Column | Type | Notes |
|--------|------|-------|
| player_id | BIGINT FK→players | **indexed** |
| as_of_date | DATE | snapshot date; **indexed** |
| window | INT | seasons (default 3) |
| orapm, drapm, rapm | NUMERIC | per 100 possessions |
| possessions | INT | sample behind the estimate |
| created_at | TIMESTAMPTZ | |

### `predictions` — persisted served predictions (§7 decision)
| Column | Type | Notes |
|--------|------|-------|
| prediction_id | BIGSERIAL PK | |
| game_id | VARCHAR(20) FK→games | **indexed** |
| player_id | BIGINT NULL | for props |
| head | VARCHAR | game_win / game_margin / game_total / prop_pts / prop_reb / prop_ast / prop_fg3m / live_win |
| value | NUMERIC | |
| interval_low, interval_high | NUMERIC NULL | props intervals |
| market | NUMERIC NULL | reserved for v2 odds comparison |
| mlflow_run_id | VARCHAR | which model produced it |
| feature_version | VARCHAR | |
| explanation | JSONB | cached `Explanation` ([explainability.md §5](explainability.md)) |
| created_at | TIMESTAMPTZ | |

Enables accuracy-over-time tracking and the v2 market benchmark.

### `live_win_prob_timeline` — PK (game_id, event_num)
| Column | Type | Notes |
|--------|------|-------|
| game_id | VARCHAR(20) FK→games | **indexed** |
| event_num | INT | |
| period, seconds_remaining_game, score_diff | INT | |
| win_prob | NUMERIC | |
| created_at | TIMESTAMPTZ | |

Powers the post-game replay chart ([live-system.md §6](live-system.md)).

### `ingested_games` — ingestion checkpoint
| Column | Type | Notes |
|--------|------|-------|
| game_id | VARCHAR(20) PK | |
| entities_done | JSONB | which parts loaded (box/pbp/shots/possessions) |
| ingested_at | TIMESTAMPTZ | |

Lets backfill resume after a crash ([data-pipeline.md §5](data-pipeline.md)).

## 6. Relationships (summary)

```
teams 1───* games (home_team_id, away_team_id)
teams 1───* team_game_stats / player_game_stats / shots / possessions
players 1──* player_game_stats / shots / player_rapm
games 1────* team_game_stats, player_game_stats, play_by_play, shots, possessions,
              features_*, predictions, live_win_prob_timeline
play_by_play 1──1 shots / features_game_state (via game_id, event_num)
possessions ──► (RAPM stint matrix) ──► player_rapm ──► features_*  (team_orapm/drapm, player_rapm)
```

## 7. Decisions (resolved 2026-06-28)
- **Lineups: player-ID arrays** on `possessions` (`off_player_ids`/`def_player_ids` `BIGINT[5]`) —
  compact and fast for reading whole lineups when building RAPM stints.
- **Predictions: persist to the `predictions` table** (not Redis-only) — enables accuracy-over-time
  tracking, post-hoc analysis, and the v2 market benchmark.
- Decided inline: `game_id` stored as the NBA string (preserves leading zeros); large tables kept
  in both Postgres (serving) and Parquet (training).

## 8. Build prompt (executable)

> **Prompt — Implement the schema.** Create SQLAlchemy 2.0 models for the **fully-specified**
> tables in §§2, 3, 5 exactly as specified (types, PKs, FKs, CHECK constraints, indexes), an
> Alembic migration creating them, and matching pyarrow Parquet schemas for the silver tables
> partitioned by `season_start_year`. The §4 gold/feature tables are deferred to T2.3 (see the §4
> note) since their columns are finalized there. This is the canonical realization that
> [data-pipeline.md](data-pipeline.md)/[feature-engineering.md](feature-engineering.md)/[rapm.md](rapm.md)/[live-system.md](live-system.md)
> build prompts depend on. Add a test asserting every model's columns/keys match this doc.

## 9. Definition of done
- All tables exist via Alembic with the specified keys/indexes/constraints.
- Parquet schemas mirror silver + gold, partitioned by season.
- FK integrity holds; idempotent upserts verified against the natural keys.
