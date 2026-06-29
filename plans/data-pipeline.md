# Data Pipeline

> **Goal:** Reliably pull NBA data from external sources, land it immutably, validate it, and
> load it into the operational DB + analytical store — on a schedule, idempotently — so every
> downstream layer (features, models, stats hub) reads clean, trustworthy data.
> Parent: [master-plan.md](master-plan.md). Feeds: [feature-engineering.md](feature-engineering.md).

---

## 1. Sources

| Source | Library | Gives us | Notes |
|--------|---------|----------|-------|
| stats.nba.com | `nba_api` | Schedule, box scores, play-by-play, shot charts, aggregate dashboards | Rate-limited, header-sensitive, occasionally flaky — must throttle + retry |
| PBP Stats | `pbpstats` | Possessions + **lineup stints** | Required for [rapm.md](rapm.md); parses NBA pbp into possession objects |
| ESPN (unofficial) | `httpx` | Live in-game play-by-play | Used by [live-system.md](live-system.md), not the batch pipeline |
| balldontlie | `httpx` | Simple games/players/box JSON | Fallback / prototyping only |

**Data caveats (carried from research):**
- Per-shot **defender distance** is **not** available for current seasons (NBA stopped
  publishing SportVU tracking ~2016). `shotchartdetail` gives location/distance/zone/type but no
  defender field. A defender-aware shot model is only trainable on the 2013–16 SportVU
  archive — relevant later for [shot quality (v2+)](master-plan.md#3-scope), not v1.
- **Early shot-location data is unreliable:** from 1996-97 through 1999-00, ~25% of field-goal
  attempts are missing location coordinates. Flag a `location_reliable` boolean on `shots` (false
  for those seasons) so location-based features and the future shot model can exclude them.

## 2. Layering (medallion pattern)

Industry-standard bronze → silver → gold separation:

- **Bronze (raw):** exact, unmodified API responses dumped to object storage. Immutable.
  Lets us re-process without re-pulling, and preserves an audit trail.
- **Silver (clean):** parsed, type-cast, **Pandera-validated** tables → Postgres (operational)
  + Parquet (analytical). One row per real-world entity, deduped.
- **Gold (features/aggregates):** computed downstream — see
  [feature-engineering.md](feature-engineering.md). Out of scope for this doc.

```
nba_api / pbpstats ─► BRONZE raw JSON (S3/MinIO, immutable)
   ─► parse + Pandera validate ─► SILVER (Postgres + Parquet)
```

## 3. Core entities (silver schema, first cut)

Full schema lives in DB models; this is the conceptual map. Detailed column lists belong in a
later `data-model.md` if it grows.

| Table | Grain | Key fields |
|-------|-------|-----------|
| `teams` | one row / team | team_id, abbreviation, name, conference |
| `players` | one row / player | player_id, name, position, active |
| `games` | one row / game | game_id, date, season, home_team_id, away_team_id, status, scores |
| `team_game_stats` | team × game | game_id, team_id, pts, reb, ast, off/def rating, pace |
| `player_game_stats` | player × game | game_id, player_id, min, pts, reb, ast, usage, +/- |
| `play_by_play` | event × game | game_id, event_num, period, clock, description, score |
| `shots` | shot × game | game_id, player_id, loc_x, loc_y, shot_distance, zone, made |
| `possessions` | possession × game | game_id, period, start/end time, offense_team_id, points, lineup ids |

`possessions` (with on-court lineup ids) comes from `pbpstats` and is the substrate RAPM needs.

## 4. Storage layout

- **Bronze (S3/MinIO):** `raw/{source}/{endpoint}/{season}/{game_id|date}.json` — write-once.
- **Silver Parquet:** `silver/{table}/season={YYYY}/part-*.parquet` — partitioned by season.
- **Silver Postgres:** normalized tables above, with indexes on (game_id), (player_id),
  (team_id), (date). Migrations via Alembic.

## 5. Ingestion design

**Two flows, one set of reusable tasks.**

- **Backfill** `backfill_season(season)` — pull a whole season once (schedule → per-game
  box/pbp/shots → possessions). Run for the N seasons we want history on.
- **Daily** `ingest_daily(date)` — nightly: pull finished games for `date`, their box/pbp/shots,
  update possessions. Idempotent so re-runs are safe.

**Reliability requirements (stats.nba.com is finicky):**
- Throttle: ≥0.6s between calls, configurable; one concurrency limit so we don't hammer it.
- Retries: exponential backoff on timeouts/429s (Prefect task retries).
- Correct headers (nba_api handles most; set a realistic User-Agent + Referer) and generous
  timeouts.
- **Idempotency:** all silver loads are upserts keyed on natural keys (game_id, event_num,
  etc.). Re-running any flow never duplicates rows. Bronze writes are keyed by game_id/date so
  re-pull overwrites the same object.
- **Checkpointing:** record which game_ids are fully ingested so backfill can resume after a
  crash instead of restarting.

**Scheduling:** Prefect deployment runs `ingest_daily` nightly (after games finish, e.g. 6am
ET). Model retraining is a *separate* scheduled flow (see [modeling.md](modeling.md)) triggered
after ingestion succeeds.

## 6. Validation (Pandera)

A Pandera schema per silver table, checked **before** any load. Examples of checks:
- `games`: `home_team_id != away_team_id`; `season` matches regex; scores ≥ 0 or null if not
  final; status ∈ {scheduled, live, final}.
- `shots`: `loc_x`/`loc_y` within court bounds; `made` ∈ {0,1}; `shot_distance` ≥ 0.
- `player_game_stats`: `min` ≥ 0; counting stats ≥ 0; usage ∈ [0,1].
A failed validation **fails the flow loudly** and quarantines the batch (writes the offending
raw payload + error to a `quarantine/` prefix) rather than loading bad data.

---

## 7. Build prompts (executable)

> **Prompt 1 — Ingestion clients.** In `backend/src/nbaforecast/ingestion/clients/`, create
> thin wrappers around `nba_api` and `pbpstats`. Requirements: a shared `throttle` (configurable
> min-interval between calls, default 0.6s, read from settings), realistic default headers, and
> a `@retry` decorator (exponential backoff, max 5 attempts) for timeouts/429s. Expose typed
> functions: `fetch_schedule(season)`, `fetch_boxscore(game_id)`, `fetch_pbp(game_id)`,
> `fetch_shots(game_id)`, `fetch_possessions(game_id)`. Each returns the raw parsed JSON/dict —
> no transformation. Unit-test the throttle and retry logic with a mocked transport.

> **Prompt 2 — Bronze landing.** In `backend/src/nbaforecast/storage/`, implement an
> `ObjectStore` abstraction over S3/MinIO (boto3 or s3fs), configured from settings, with
> `put_raw(source, endpoint, key, payload)` writing to
> `raw/{source}/{endpoint}/{season}/{key}.json` and `get_raw(...)`. Writes are idempotent
> (overwrite same key). Add a `quarantine(payload, error)` helper writing to `quarantine/`.

> **Prompt 3 — Silver parse + validate + load.** In `backend/src/nbaforecast/ingestion/`, for
> each entity in §3 write a `parse_{entity}(raw) -> DataFrame` function and a Pandera schema in
> `ingestion/schemas.py` enforcing the §6 checks. Create SQLAlchemy 2.0 models +
> repositories in `storage/` with **upsert** methods keyed on the natural keys, plus an Alembic
> migration creating all tables and indexes. Add `write_parquet(table, df, season)` partitioning
> by season. The load step must: validate → on failure quarantine and raise; on success upsert
> to Postgres and write Parquet.

> **Prompt 4 — Prefect flows.** In `backend/src/nbaforecast/ingestion/flows/`, implement
> `backfill_season(season)` and `ingest_daily(date)` Prefect flows composing the client → bronze
> → parse → validate → silver tasks per entity, with task-level retries and a global concurrency
> limit. Maintain an `ingested_games` checkpoint table so backfill resumes. Add a Prefect
> deployment that schedules `ingest_daily` nightly (cron, configurable, default 6am ET).

> **Prompt 5 — Data-validation tests.** In `backend/tests/data_validation/`, add pytest tests
> that run each Pandera schema against a saved sample raw payload fixture (one per entity, stored
> under `tests/fixtures/`), asserting valid payloads pass and deliberately corrupted ones are
> rejected and quarantined. Wire these into the CI workflow.

## 8. Definition of done
- `backfill_season(2023)` lands bronze JSON, validated silver Parquet, and populated Postgres
  for a full season, idempotently (re-run produces no duplicates).
- `ingest_daily(yesterday)` runs nightly via the Prefect deployment.
- A corrupted payload is quarantined and fails the flow loudly — never loaded.
- `possessions` table is populated with lineup ids, ready for [rapm.md](rapm.md).
- All Pandera schemas covered by tests in CI.

## 9. Decisions & open questions

**Decided — ingestion depth vs. training window (these are separate knobs):**
- **Ingestion depth = the full play-by-play era, 1996-97 → present** (~29 seasons). The PBP era
  is the earliest digitized comprehensive play-by-play/shot data on stats.nba.com. Storage is
  cheap (~16M pbp rows / ~7M shots total), so we store the complete record and decide what to
  *train on* separately.
- **Training window = configurable per model** via a `lookback_seasons` parameter (the
  "limit to last X seasons" feature). Default **~15 seasons**, with presets *Modern ≈ 10 /
  Extended ≈ 15 / Full ≈ 29*. Rationale: the game changed (hand-check ban 2004-05, three-point
  boom ~2014-15, rising pace), so recency-vs-sample-size is an empirical tradeoff to backtest,
  not hardcode. This parameter is owned by [modeling.md](modeling.md); the pipeline just makes
  all seasons available.

**Open:**
- **dbt or Python for silver→gold transforms?** Deferred to [feature-engineering.md](feature-engineering.md);
  pipeline here only owns bronze→silver.
- Exact nightly run time vs. when box scores/pbp finalize on stats.nba.com.
- Confirm earliest reliably-available season **per endpoint** at build time (`pbpstats`
  possessions and some dashboards may not reach all the way to 1996-97).
