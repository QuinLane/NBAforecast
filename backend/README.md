# nbaforecast (backend)

Explainable NBA prediction engine — ingestion, features, models, and the FastAPI service. One
installable package (`nbaforecast`) with multiple entrypoints (API, Prefect worker, live poller,
backfill). See [`../plans/`](../plans) for the full design.

## Setup

```bash
uv sync --group dev          # install deps into .venv (lockfile is committed)
```

Quality gates (also enforced in CI):

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest tests
```

## Local stack

From the repo root, bring up Postgres, Redis, MinIO, and MLflow, then apply migrations:

```bash
docker compose up -d
cd backend && uv run alembic upgrade head
```

Copy `../.env.example` to `../.env` and adjust as needed (all config is `NBAF_`-prefixed).

## Data ingestion (M1)

Bronze → silver pipeline: raw nba_api / pbpstats JSON is landed immutably to MinIO, then parsed,
Pandera-validated, and upserted to Postgres + written to partitioned Parquet. Bad payloads are
quarantined and the flow fails loudly. See [`../plans/data-pipeline.md`](../plans/data-pipeline.md).

### Run the full-era backfill (T1.7)

With the stack up and migrations applied:

```bash
uv run nbaforecast-backfill                       # full PBP era, 1996-97 → present
uv run nbaforecast-backfill --start-year 2023     # only 2023-24 → present
uv run nbaforecast-backfill --start-year 2023 --end-year 2023 --season-type "Regular Season"
```

The run is **resumable** — the `ingested_games` checkpoint lets a re-run skip games already fully
ingested, so an interrupted backfill continues where it left off. Calls to stats.nba.com are
throttled and retried (`NBAF_INGEST_*` settings); a full-era backfill is a long operation best run
overnight. Start with a single recent season to validate the stack end-to-end before the full era.

### Nightly incremental ingest

```bash
uv run nbaforecast-worker     # serves the ingest-daily deployment (cron, default 6am ET)
```

## Training + champion promotion (T3.14)

With data backfilled, train heads and run the champion/challenger gate — walk-forward backtest →
final fit on the trailing window → MLflow run (params, backtest metrics, model artifact, global
SHAP) → promotion gate:

```bash
uv run nbaforecast-train                              # all heads
uv run nbaforecast-train --heads game_win props_pts   # a subset
uv run nbaforecast-train --lookback-seasons 5         # smaller training window
uv run nbaforecast-train --rapm-snapshots             # also build historical player_rapm
```

The API hot-reloads a newly promoted champion within its registry-poll interval — no restart
needed.

## Entrypoints

| Command | Purpose |
|---------|---------|
| `nbaforecast-api` | FastAPI service (`GET /health`) |
| `nbaforecast-worker` | Prefect worker serving the nightly ingest deployment |
| `nbaforecast-backfill` | Historical season backfill (full PBP era by default) |
| `nbaforecast-train` | Train heads + champion promotion gate (and RAPM snapshots) |
| `nbaforecast-poller` | Live game poller (M4) |
