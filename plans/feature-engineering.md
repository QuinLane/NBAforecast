# Feature Engineering

> **Goal:** Turn clean silver data into model-ready **features**, computed once in a shared
> pipeline and read identically by every model head — with strict **point-in-time correctness**
> (no data leakage) and **train/serve parity** (same computation at training and prediction).
> Parent: [master-plan.md](master-plan.md). Consumes: [data-pipeline.md](data-pipeline.md).
> Feeds: [modeling.md](modeling.md), [rapm.md](rapm.md).

---

## 1. What this layer is (the "gold" layer)

A **feature** is a model input — e.g., "home team's net rating over its last 10 games as of
tonight." Raw silver tables aren't model-ready; this layer computes features from them and
**materializes** them into feature tables keyed by entity + game.

We build a **lightweight feature store**, not a heavy one:
- Feature tables live in Postgres (serving) + Parquet (training), e.g. `features_team_game`,
  `features_player_game`, `features_game_state`.
- A single **shared computation library** (`nbaforecast.features`) produces them — used by both
  the batch backfill *and* live inference. (A full feature store like Feast is **overkill** at
  this scale — see the tool-liability principle in [architecture.md §7](architecture.md).)

```
SILVER tables ─► nbaforecast.features (shared lib) ─► GOLD feature tables ─► model heads
```

## 2. The cardinal rule: point-in-time correctness (no leakage)

**A feature for game G may only use information available strictly before tip-off of G.**

Data **leakage** is the #1 silent killer of ML projects: a model that peeks at future
information scores beautifully in backtests and then collapses in production. Classic leaks here:
- A "season average" that includes the game being predicted (or later games).
- A rolling average whose window accidentally includes the current game.
- Opponent ratings computed over the *full* season when predicting a mid-season game.

**Enforcement:**
- Every rolling/aggregate feature is computed **"as of" the game date**, using only rows with
  an earlier game datetime — implemented via time-ordered `groupby` + `shift(1)` (exclude the
  current row) and **as-of joins**, never a full-season aggregate.
- A dedicated **no-leakage test** (see build prompts) asserts that recomputing a game's features
  using only games before it yields identical values to the materialized feature row.
- Backtesting replays history in chronological order; no future season's data informs a past
  prediction.

## 3. Train/serve parity

The **same function** computes features for a historical game (training) and for tonight's game
(live prediction), parameterized only by an `as_of` timestamp. One code path → no **train/serve
skew** (the bug where a feature is computed slightly differently at predict time and the model
silently degrades). The live poller and the training job both import `nbaforecast.features`.

## 4. v1 feature catalog

### Team–game features (`features_team_game`, one row per team per game)
Drives [game prediction](modeling.md). Computed for both home and away team.

| Group | Features |
|-------|----------|
| Rest & schedule | days_rest, is_back_to_back, games_last_7d, games_last_14d (fatigue/density) |
| Travel | is_home, travel_distance_km (from arena lat/long ref table), tz_shift since last game |
| Recent form | rolling net_rating / off_rating / def_rating / pace over last 5 & 10 games (shifted) |
| Season-to-date | as-of off/def/net rating, pace, win_pct (only games before G) |
| Strength | own Elo/power rating (as-of), opponent-adjusted net rating |
| Matchup | head-to-head record & avg margin vs tonight's opponent (prior games only) |
| Differentials | rest_advantage, rating_diff, elo_diff (home minus away) |

### Player–game features (`features_player_game`, one row per player per game)
Drives [props](modeling.md).

| Group | Features |
|-------|----------|
| Recent production | rolling mean/std of pts, reb, ast over last 5/10/15 games (shifted) |
| Role/usage | rolling minutes, usage_rate, recent minutes trend (role change detection) |
| Season-to-date | as-of per-game averages, usage |
| Matchup/context | opponent def_rating, opponent pace (more possessions → more counting stats), opp positional defense, is_home, days_rest, is_back_to_back |

### Game-state features (`features_game_state`, one row per play-by-play state)
Drives [live win probability](live-system.md). Built from historical pbp for training.

| Group | Features |
|-------|----------|
| Score/clock | score_diff, seconds_remaining (game), period, is_clutch |
| Possession | offense_has_ball, possession_arrow |
| Prior | pre_game_win_prob (the [game-prediction](modeling.md) output as an input — see §5) |
| Secondary | timeouts_remaining, in_bonus, fouls |

## 5. Composition: model outputs as features

Two deliberate compositions that make the system more than the sum of its parts:
- **RAPM → features:** player RAPM values (from [rapm.md](rapm.md)) aggregate into team strength
  features for game prediction and into player-quality features for props. (Use a RAPM computed
  on data *before* G to stay leakage-safe.)
- **Pre-game win prob → live model:** the game-prediction model's output seeds the live model as
  a prior, so at tip-off the live win prob equals the pre-game prediction and updates from there.

Both must respect point-in-time correctness — only use upstream outputs computed from pre-G data.

## 6. Training-set assembly & `lookback_seasons`

When [modeling.md](modeling.md) builds a training set it: (1) selects the target games, (2)
filters them to the configurable **`lookback_seasons`** window (default ~15; see
[data-pipeline.md §9](data-pipeline.md)), (3) joins the materialized feature rows. The features
themselves are game-relative (rolling windows); `lookback_seasons` filters which *games* become
training rows, not the window of each rolling feature.

## 7. Storage, versioning, refresh

- Materialized to `features_*` tables (Postgres) + Parquet partitioned by season.
- **Feature-set version:** a `feature_version` string recorded with each materialization and
  logged to MLflow with every model, so we always know which feature definitions a model was
  trained on.
- **Refresh:** a Prefect task recomputes/upserts affected feature rows after each
  `ingest_daily` silver load (only games touched + dependent rolling windows).
- A static **arena reference table** (team_id → lat/long) seeds travel features.

---

## 8. Build prompts (executable)

> **Prompt 1 — Leakage-safe primitives.** In `backend/src/nbaforecast/features/primitives.py`,
> implement reusable, time-correct helpers: `rolling_as_of(df, group_keys, value, window,
> datetime_col)` (time-ordered, `shift(1)` to exclude the current row), `as_of_join(left, right,
> on, datetime_col)`, `days_rest(...)`, `schedule_density(...)`, and `travel_distance(...)` using
> an arena lat/long reference. Every function takes/respects an `as_of` boundary. Unit-test that
> none of them ever incorporate the current or any future row.

> **Prompt 2 — Team–game features.** In `features/team_game.py`, implement
> `build_team_game_features(as_of=None) -> DataFrame` producing every column in §4 (team–game)
> from silver tables, using only the §8.1 primitives. When `as_of` is None it builds the full
> historical table (training); when set it builds features for upcoming games (serving). Include
> an own-Elo computation updated chronologically.

> **Prompt 3 — Player–game features.** In `features/player_game.py`, implement
> `build_player_game_features(as_of=None)` producing the §4 player–game columns, including
> opponent positional defense and minutes-trend role detection.

> **Prompt 4 — Game-state features.** In `features/game_state.py`, implement
> `build_game_state_features(game_pbp, pre_game_win_prob)` producing the §4 game-state columns
> from a game's play-by-play, accepting the pre-game prior. Reused live by [live-system.md](live-system.md).

> **Prompt 5 — Materialization + refresh.** In `features/materialize.py`, write the gold
> `features_team_game` / `features_player_game` / `features_game_state` SQLAlchemy models +
> Alembic migration, an upsert materializer writing Postgres + Parquet (partitioned by season)
> stamped with a `feature_version`, and a Prefect task that incrementally refreshes affected
> rows after `ingest_daily`.

> **Prompt 6 — Leakage & parity tests.** In `backend/tests/ml/`, add: (a) a **no-leakage test**
> that recomputes a sampled game's features from only pre-game data and asserts equality with the
> materialized row; (b) a **train/serve parity test** asserting `build_*` with `as_of` set to a
> historical game's tip-off reproduces that game's stored training features exactly. Wire into CI.

## 9. Definition of done
- `features_team_game`, `features_player_game`, `features_game_state` materialized for the full
  ingested history, partitioned by season, stamped with a `feature_version`.
- No-leakage and train/serve-parity tests pass in CI.
- Feature refresh runs automatically after nightly ingestion.
- RAPM values and pre-game win prob are wired in as features (§5) once those models exist.

## 10. Decisions & open questions
- **Decided — Python, not dbt** for these transforms. The same shared library serves live
  inference, giving train/serve parity for free; dbt is SQL-only and can't run at live predict
  time (it would force a second Python implementation and reintroduce skew risk).
- Injuries / roster availability as features — reliable free source is uncertain; defer to v2 or
  approximate via recent-minutes availability. Decide in [modeling.md](modeling.md).
- Exact rolling windows (5/10/15) to keep — tune empirically during modeling.
