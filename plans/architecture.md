# Architecture

> **Goal:** Define the full tech stack, system architecture, data flow, and repository file
> structure for NBAforecast in enough detail that the scaffolding can be prompted directly.
> Parent: [master-plan.md](master-plan.md).

---

## 1. Tech stack (with rationale)

### Data layer
| Tool | Role | Why |
|------|------|-----|
| `nba_api` | Primary ingestion | Box scores, shot charts, play-by-play, tracking dashboards |
| `pbpstats` | Possession/lineup ingestion | Stint-level data RAPM needs |
| `httpx` | Async HTTP | Concurrent pulls, live polling |
| **Prefect** | Orchestration | Schedules nightly ingestion + retraining as DAGs; lighter/more Pythonic than Airflow |
| **Postgres** | App database | Serving store for stats, predictions, features |
| SQLAlchemy 2.0 + Alembic | ORM + migrations | Typed models + versioned schema |
| **S3** (MinIO locally) | Object store | Raw JSON dumps + Parquet + model artifacts |
| **Parquet** (pyarrow) | Columnar history | Cheap analytical store; data-lake pattern |
| **Pandera** | Data validation | Schema/range checks; early warning when upstream API changes |

### Modeling layer
| Tool | Role | Why |
|------|------|-----|
| pandas, numpy | Data wrangling | Standard |
| scikit-learn | Baselines, pipelines, calibration | Logistic baseline, `Ridge` for RAPM |
| XGBoost / LightGBM | Gradient boosting | Game prediction, props (and later shot quality) |
| scipy.sparse | Sparse matrices | RAPM design matrix (lineup stints) |
| **SHAP** | Explainability | Per-prediction feature attribution → "show the why" visuals |
| **MLflow** | Experiment tracking + model registry | Reproducibility; serves the "how we predict" theme |
| PyTorch | *Optional, later* | NN win-prob variant if desired |

### Backend / serving
| Tool | Role | Why |
|------|------|-----|
| **FastAPI** + Pydantic + Uvicorn | API | Async, typed, auto OpenAPI docs |
| pydantic-settings | Config | 12-factor env config |
| **Redis** | Cache | Live dashboards, leaderboards, expensive queries |
| APScheduler / Prefect | Live polling | Timer-driven live game updates (event-driven upgrade deferred) |

### Frontend
| Tool | Role | Why |
|------|------|-----|
| **Next.js + TypeScript** | App framework | SSR/SSG for SEO on a public site; industry default |
| **D3.js** | Custom viz | Shot charts, court heatmaps |
| Recharts / visx | Standard charts | Win-prob line, trends |
| TanStack Query | Data fetching | Caching, revalidation |
| Tailwind CSS | Styling | Fast, consistent UI |

### Infra / DevOps
| Tool | Role | Why |
|------|------|-----|
| **Docker** + docker-compose | Local + prod images | One-command local stack; reproducible |
| **GitHub Actions** | CI/CD | Lint, type-check, test, build on every PR |
| **AWS** (ECS Fargate + RDS + S3 + EventBridge) | Prod | Cloud target; start on cheap PaaS, migrate |
| Terraform | IaC *(optional)* | Infrastructure-as-code signal |
| ruff, mypy, pytest | Quality gates | Lint/format, types, tests |

---

## 2. System architecture

Seven logical components. The Python pieces live in **one installable package**
(`nbaforecast`) with **multiple entrypoints** (API server, Prefect worker, live poller) —
pragmatic for a solo project while keeping clean module boundaries.

1. **Ingestion** — Prefect flows call `nba_api`/`pbpstats`, land raw JSON in object storage.
2. **Storage** — raw (S3/MinIO) + structured serving DB (Postgres) + columnar history (Parquet).
3. **Feature engineering** — one shared pipeline transforms raw → feature tables consumed by
   every model head (so new models = new heads, not new pipelines).
4. **Modeling** — per-head training pipelines; experiments + artifacts tracked in MLflow;
   best models promoted in the MLflow registry.
5. **Serving** — FastAPI loads registered models, returns predictions + SHAP explanations.
6. **Live system** — poller pulls live play-by-play, computes win prob, caches in Redis,
   pushes to the dashboard.
7. **Frontend** — Next.js consumes the API; SSR for stats pages, live polling for dashboards.

### Data flow

**Batch (nightly, Prefect-scheduled):**
```
nba_api/pbpstats ─► land raw JSON (S3/MinIO)
  ─► parse + validate (Pandera) ─► load Postgres + write Parquet
  ─► feature engineering ─► feature tables
  ─► (scheduled) retrain heads ─► log to MLflow ─► promote in registry
```

**Request-time:**
```
Next.js ─► FastAPI ─► load cached prediction OR compute from registered model
  ─► attach SHAP explanation ─► JSON response ─► render (D3 / charts)
```

**Live game:**
```
live poller (every N s) ─► ESPN/NBA live PBP ─► win-prob model
  ─► write Redis ─► frontend polls/SSE ─► live dashboard updates
```

---

## 3. Repository file structure

```
NBAforecast/
├── claudeInfo.md
├── plans/                          # all planning docs
├── README.md
├── docker-compose.yml              # postgres, redis, minio, mlflow, api, worker, frontend
├── .env.example
├── .github/
│   └── workflows/ci.yml            # lint, type-check, test, build
│
├── backend/
│   ├── pyproject.toml              # one installable package: nbaforecast
│   ├── alembic/                    # DB migrations
│   ├── src/nbaforecast/
│   │   ├── config/                 # pydantic-settings, env handling
│   │   ├── ingestion/              # nba_api/pbpstats clients + Prefect flows
│   │   │   ├── clients/
│   │   │   └── flows/
│   │   ├── storage/                # SQLAlchemy models, repositories, s3/parquet IO
│   │   ├── features/               # shared feature engineering
│   │   ├── models/                 # one subpackage per model head
│   │   │   ├── game_prediction/
│   │   │   ├── win_probability/
│   │   │   ├── props/
│   │   │   └── rapm/
│   │   ├── training/               # training pipelines + MLflow integration
│   │   ├── explain/                # SHAP wrappers + explanation formatting
│   │   ├── live/                   # live game poller + win-prob updater
│   │   ├── api/                    # FastAPI app
│   │   │   ├── main.py
│   │   │   ├── routers/            # games, predictions, players, rapm, live, stats
│   │   │   ├── schemas/            # Pydantic request/response models
│   │   │   └── deps.py             # DI: db session, cache, model registry
│   │   └── entrypoints/            # api_server, prefect_worker, live_poller
│   └── tests/
│       ├── unit/
│       ├── data_validation/        # Pandera-based
│       ├── ml/                     # no-leakage, calibration, baseline-floor
│       └── api/
│
├── frontend/                       # Next.js + TS (App Router)
│   ├── package.json
│   ├── app/                        # routes: /, /games, /games/[id], /players/[id], /rapm, /live
│   ├── components/                 # charts, shot-chart, win-prob, prediction-explainer
│   ├── lib/                        # api client, hooks (TanStack Query)
│   └── styles/
│
├── infra/
│   ├── terraform/                  # optional IaC
│   └── docker/                     # Dockerfiles (api, worker, frontend)
│
└── data/                           # local dev data + Parquet (gitignored)
```

---

## 4. Environments

- **Local (default):** `docker-compose up` brings up Postgres, Redis, MinIO, MLflow, the API,
  a Prefect worker, and the Next.js dev server. $0 cost, fully offline-capable after data pull.
- **CI:** GitHub Actions runs lint/type/test against ephemeral Postgres.
- **Prod (later):** start on a cheap PaaS (Render/Fly + Vercel hobby), migrate to AWS
  (ECS Fargate + RDS + S3 + EventBridge) when justified. Secrets via env / AWS SSM.

## 5. Cross-cutting conventions

- **Config:** all settings via `pydantic-settings`, never hardcoded; `.env.example` documents keys.
- **Storage abstraction:** a `storage` module hides S3-vs-MinIO behind one interface (boto3/s3fs).
- **Model access:** API never trains; it loads the current registered model from MLflow.
- **Shared features:** every model head reads from the same feature tables — enforced by design.

---

## 6. Build prompt — scaffolding (executable)

> **Prompt:** Scaffold the NBAforecast monorepo exactly per the file structure in §3. Create:
> (1) `backend/pyproject.toml` defining an installable package `nbaforecast` with deps:
> `nba_api`, `pbpstats`, `httpx`, `prefect`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`,
> `pyarrow`, `pandera`, `pandas`, `numpy`, `scikit-learn`, `xgboost`, `lightgbm`, `shap`,
> `mlflow`, `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `redis`, plus dev deps
> `pytest`, `ruff`, `mypy`. (2) The full `src/nbaforecast/` package tree with empty
> `__init__.py` files and a one-line docstring in each subpackage stating its responsibility.
> (3) `backend/src/nbaforecast/config/settings.py` with a `pydantic-settings` `Settings` class
> covering Postgres, Redis, S3/MinIO, and MLflow connection params, reading from env. (4) A
> `docker-compose.yml` wiring Postgres, Redis, MinIO, an MLflow server (Postgres-backed,
> MinIO artifacts), the FastAPI app, and a Prefect worker. (5) `.env.example` documenting all
> keys. (6) `frontend/` as a Next.js + TypeScript + Tailwind App-Router project with a
> placeholder home page and a configured TanStack Query provider. (7) `.github/workflows/ci.yml`
> running ruff, mypy, and pytest on the backend. Do **not** implement business logic yet —
> only the skeleton, configs, and one health-check endpoint (`GET /health`) in the API.
> Definition of done: `docker-compose up` starts all services and `GET /health` returns 200.

## 7. Rationale — why this architecture

**The central idea: separate the training path from the serving path.** The app has two
workloads that must never share a code path: heavy/slow/occasional (pull data, build features,
train models — minutes to hours, nightly) and light/fast/constant (a user wants a prediction
now — milliseconds). Models are trained offline and saved; the web server only *loads* the
finished artifact and answers. Same reason you don't recompile on every HTTP request. The
vertical spine in §2 encodes exactly this split; every tool below is plumbing that keeps it
clean.

**What each tool buys us (what breaks without it):**
- **Prefect** — "cron with a brain": models the pipeline as a DAG with retries, run history,
  and a dashboard. *Without it: brittle scripts, no visibility, manual 3am recovery.*
- **Postgres** — operational store for fast indexed row lookups the app hits. *Bad at
  ML-scale scans, which is why we also have ↓.*
- **S3/MinIO + Parquet** — cheap file storage for raw API dumps + columnar analytical data.
  Parquet stores column-by-column compressed, so training reads only needed columns ~10–100×
  faster than Postgres. The "data lake" pattern, kept separate from the operational DB.
  *Without it: cram everything into Postgres → slow, costly scans, raw data destroyed on
  reshape.*
- **Pandera** — declares required columns/types/ranges and fails loudly at ingestion. Type
  checks for *data*. *Without it: silent corruption when the NBA API changes a field.*
- **Shared feature pipeline** — features computed once, read by all heads. Prevents
  *train/serve skew* (computing a feature differently at train vs predict time) and makes new
  models cheap. *This is the mechanism behind "broad now, deep later."*
- **MLflow** — logs every training run (params/metrics/artifact) for reproducibility, and a
  registry tells the API which model is *current*. *This is what decouples training from
  serving.* *Without it: scattered pickle files, no idea what's in prod.*
- **SHAP** — attributes each prediction to its input features; the engine behind the
  "show the why" visuals. *Without it: black-box predictions, killing the differentiator.*
- **FastAPI / Redis / Docker** — async typed API boundary / in-memory cache so live numbers
  are computed once and read many times / reproducible one-command local stack.

**Two structural decisions:**
- **Monorepo** (backend + frontend, one repo): atomic cross-stack commits, simplest for a solo
  dev. Split repos would mean two PRs for any change spanning the API and its UI — pure friction
  here.
- **Modular monolith** (one Python package, multiple entrypoints) over microservices: trivially
  share models/config/helpers, one deploy, refactor by moving functions; scale by running more
  copies of an entrypoint. Microservices' network calls / serialization / distributed debugging
  are the classic over-engineering trap at this scale. A piece can be extracted into its own
  service later *if* it genuinely needs independent scaling.

**Tool principle:** every tool is a liability (learn + maintain) as well as an asset; adopt one
only when the pain it removes exceeds the pain it adds. Prefect/MLflow/S3+Parquet are accepted
slightly early because the *skill* is part of a portfolio deliverable; Kafka, Kubernetes, and
microservices are excluded because their cost is real and the payoff isn't at this scale.

## 8. Open questions
- Live in-game feed: ESPN unofficial endpoint vs NBA live endpoint — decide in
  [live-system.md](live-system.md) (real-time reliability + rate limits).
- Whether to add **dbt** for SQL transformations (analytics-engineering signal) or keep
  transforms in Python — decide in [data-pipeline.md](data-pipeline.md).
- Whether to commit to **Terraform** in v1 or defer until first AWS deploy.
