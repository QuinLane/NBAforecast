# NBAforecast — Master Plan

> **Status:** Planning. This is the index for the whole project. It describes goals, scope,
> and the high-level architecture, then points to focused sub-plans. Keep this file in sync
> whenever a sub-plan is added or scope changes. See [`../claudeInfo.md`](../claudeInfo.md)
> for *how* we work on this project.

---

## 1. What NBAforecast is

A full web app that is a **central hub for NBA stats and interesting data**, with a
**prediction engine that shows its reasoning** — not "AI says X," but data-grounded
predictions with visible feature attributions (the "glass box" theme).

- **Hero:** explainable prediction (game outcome, live win probability, player props).
- **Substrate:** a clean stats hub powered by the same data pipeline that feeds the models.
- **Differentiator:** *show the why.* Every prediction comes with a visual breakdown of the
  factors driving it (powered by SHAP).

## 2. Goals

- **Portfolio:** demonstrate end-to-end CS depth — real-time data pipeline, ML modeling,
  model serving, backtesting, explainability, cloud-ready deployment.
- **Real product:** something Quin can actually maintain and host publicly.
- **Skill growth:** hands-on with industry-standard tools (FastAPI, Prefect, MLflow,
  Postgres, Docker, AWS, Next.js).

## 3. Scope

### v1 (build now)
- **Game prediction** — pre-game win probability + spread, gradient boosting + logistic baseline.
- **Live win probability** — in-game model updating off live play-by-play, on a dashboard.
- **Player props** — projected PTS/REB/AST per player per game.
- **RAPM** — regularized adjusted plus-minus player value (ridge on sparse lineup matrix).
- **Stats hub** — clean display of stats/shot charts powered by the pipeline.
- **SHAP explainability** — cross-cutting; every model exposes feature attributions.
- **Market benchmark + public report card** *(promoted from v2, 2026-07-01)* — historical closing
  odds (~2007→) + nightly line capture; a nightly-updated public self-grading page (Brier/log-loss
  vs. market, calibration, ATS, props hit rates). Framed as calibration honesty, never betting edge.
- **Famous-games replay** — archived play-by-play through the identical live pipeline; curated
  iconic games with a scrubber + per-moment explained win prob. Live lane demoable off-season.
- **Injury/availability features** — official injury report ingested; availability as model input.
- **Monte Carlo season simulator** — playoff/seed/title odds off the game head, nightly.
- **Props uncertainty bands + prediction provenance** — quantile intervals under the point
  estimate; model version/training date on every prediction.

### v2+ (deferred)
- **Shot-quality model** — expected FG% (all-seasons location/context; defender-aware only on
  the 2013–16 SportVU archive — see [data-pipeline.md](data-pipeline.md) for the data caveat).
- **Computer-vision shot tracker** — ball-trajectory make/miss from video. Architecturally
  separate (CV, not tabular). Treat as a standalone Phase 3 moonshot.
- **Intraday line movement** — v1 captures closing lines only ($0); finer-grained odds history is
  a paid tier. See [modeling.md §10](modeling.md).
- **Live community predictions/polls** — a genuinely interactive, bidirectional feature; the
  intended home for **WebSockets** (v1 live win-prob uses one-way SSE — see
  [backend-api.md §7](backend-api.md)).
- Streaming (Redpanda/Kinesis) upgrade for live ingestion if load ever justifies it.

## 4. Architecture (summary)

Monorepo. Python backend (ingestion + ML + API as one installable package with multiple
entrypoints) + Next.js frontend. Local-first: the entire stack runs via `docker-compose` at
$0 cost until public launch. Full detail in **[architecture.md](architecture.md)**.

```
nba_api / pbpstats ──► Prefect ingestion ──► raw (S3/MinIO) ──► validate (Pandera)
   ──► Postgres + Parquet ──► shared feature pipeline ──► model heads (train, MLflow)
   ──► FastAPI serving (+ SHAP) ──► Next.js frontend
                       live games ──► poller ──► win-prob ──► Redis ──► dashboard
```

## 5. Tech stack (one-liner; full rationale in architecture.md)

Python · FastAPI · Postgres · Prefect · MLflow · scikit-learn / XGBoost / LightGBM · SHAP ·
S3/MinIO + Parquet · Redis · Docker · GitHub Actions · Next.js + TypeScript + D3 · AWS (prod).

## 6. Sub-plans (index)

| Plan | Status | Covers |
|------|--------|--------|
| [architecture.md](architecture.md) | ✅ drafted | Tech stack, system design, file structure, environments |
| [engineering-standards.md](engineering-standards.md) | ✅ drafted | Code structure, naming, git, commits, PR/review protocol |
| [concepts-and-terminology.md](concepts-and-terminology.md) | ✅ drafted | Plain-language ML + project glossary (learning reference) |
| [agent-orchestration.md](agent-orchestration.md) | ✅ drafted | Parallel subagent build strategy (M3 fan-out) |
| [data-pipeline.md](data-pipeline.md) | ✅ drafted | Sources, ingestion, storage, validation, scheduling |
| [data-model.md](data-model.md) | ✅ drafted | Canonical schema — all tables, columns, keys, indexes |
| [feature-engineering.md](feature-engineering.md) | ✅ drafted | Shared feature pipeline feeding all model heads |
| [modeling.md](modeling.md) | ✅ drafted | Game prediction, win prob, props — training & eval |
| [rapm.md](rapm.md) | ✅ drafted | Ridge-on-sparse-lineup-matrix RAPM, from v1 |
| [explainability.md](explainability.md) | ✅ drafted | SHAP integration + how the "why" is surfaced |
| [backend-api.md](backend-api.md) | ✅ drafted | FastAPI services, endpoints, schemas |
| [live-system.md](live-system.md) | ✅ drafted | Live game polling + win-prob updates + caching |
| [frontend.md](frontend.md) | ✅ drafted | Next.js app, stats hub, prediction visuals |
| [infrastructure.md](infrastructure.md) | ✅ drafted | Docker, CI/CD, AWS deployment, secrets |
| [testing.md](testing.md) | ✅ drafted | Unit, data validation, ML tests (no-leakage, calibration) |
| [roadmap.md](roadmap.md) | ✅ drafted | Milestones, build order, definition of done per phase |
| [implementation-plan.md](implementation-plan.md) | ✅ drafted | Dependency-ordered task checklist (T0.1…T6.6) with gates |

## 7. Build order (high level)

1. Scaffolding + local Docker stack (architecture.md).
2. Data pipeline → first data landed and validated.
3. Feature pipeline → feature tables.
4. First model head end-to-end (game prediction) + MLflow + SHAP + API + a frontend page.
5. Add RAPM, props, live win-prob heads on the shared pipeline.
6. Stats hub pages.
7. Deploy.

## 8. Change log
- 2026-06-28 — Master plan created. v1 scope set (game prediction, live win prob, props, RAPM,
  stats hub, SHAP). Stack locked (SSR/Next.js, FastAPI, Prefect, MLflow, AWS). Architecture
  drafted in architecture.md.
- 2026-06-28 — **All 12 sub-plans drafted** with embedded build prompts and resolved decisions:
  - Game output = win prob + margin + total; props = PTS/REB/AST/3PM; live = LightGBM **and** NN
    (compared); market/odds benchmark deferred to v2.
  - RAPM = ORAPM/DRAPM split, 3-season rolling default, plain ridge (box-prior v2).
  - Explanations = top-5 waterfall + expandable, probability-points (log-odds toggle), live
    headline-drivers + full-on-demand.
  - API = async SQLAlchemy, public read-only + rate limit, **SSE** for live (WebSocket earmarked
    for a future interactive feature).
  - Live source = NBA cdn + ESPN fallback, ~10s cadence, persisted win-prob timeline.
  - Frontend = shadcn/ui + Tailwind, OpenAPI-generated client, Recharts (+ D3 courts).
  - Infra = PaaS-first, Terraform deferred, Sentry + structured logs. Data transforms = Python
    (not dbt).
  - Ingest full PBP era (1996-97→present) from M1; train on configurable `lookback_seasons`
    (default ~15). Build order = vertical slice first with a drop-in `ModelHead` interface.
  - **data-model.md** added as the canonical schema (all tables/columns/keys/indexes): `game_id`
    as string, possession lineups as `BIGINT[5]` arrays, predictions persisted to Postgres, large
    tables in both Postgres + Parquet.
  - **engineering-standards.md** + **implementation-plan.md** added. Standards: uv + pnpm,
    ruff/mypy-strict, trunk-based + squash-merge, Conventional Commits, snake_case JSON, layering
    rules, PR Definition-of-Done. Implementation plan: dependency-ordered task checklist
    (T0.1→T6.6) mapped to milestones with gates; one task = one branch = one PR.
- 2026-07-01 — **Portfolio restructure** (M0–M3 complete at this point). v1 scope expanded:
  market benchmark + public report card promoted from v2, famous-games replay, injury/availability
  features, Monte Carlo season simulator, props uncertainty bands + provenance. Roadmap gains
  **M3.5** (stack verification on real data — pays down the deferred M2/M3 live-stack debt) and
  **M4.5** (market benchmark + report card + availability); M4 is now replay-first. See
  [roadmap.md §6](roadmap.md) for the decision log and
  [implementation-plan.md](implementation-plan.md) for tasks T3.13–T3.15, T4.11–T4.17, T5.5–T5.6.
  New: [`docs/project-explainer.md`](../docs/project-explainer.md) — plain-language technical
  breakdown of the whole project (interview prep; lives outside `plans/` so it survives cleanup).
- 2026-07-07 — **Stats-browser pull-forward** (M3.5 complete). Inserted **M3.75** (stats-hub core
  pulled forward from M5): player/team pages, box scores, a stat-trajectory chart (tabs incl. RAPM,
  on a monthly snapshot cadence), head-to-head lookup, leaderboards, quick-search — all queries
  over already-ingested data. Player pages become stats-first (props → trajectory → tables → log).
  Player headshots + team logos hotlinked from the NBA CDN. RAPM trajectory lives on player pages,
  never the leaderboard (snapshot ≠ self-over-time; career = per-season path, not an era-blended
  average). M5 keeps shot charts, how-it-works, Monte Carlo. See [roadmap.md §7](roadmap.md) and
  [implementation-plan.md](implementation-plan.md) tasks T3.16–T3.24.
