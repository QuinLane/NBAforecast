# Backend API

> **Goal:** Expose stats-hub data, predictions, explanations, props, RAPM, and live win
> probability over a clean, typed HTTP API. The API **never trains** — it loads the current
> champion models from MLflow and serves them, caching hot results in Redis.
> Parent: [master-plan.md](master-plan.md). Consumes: [modeling.md](modeling.md),
> [rapm.md](rapm.md), [explainability.md](explainability.md). Serves: [frontend.md](frontend.md),
> [live-system.md](live-system.md).

---

## 1. Framework & shape

**FastAPI** (async, Pydantic-typed, auto-generated OpenAPI docs). Structure:
- `api/main.py` — app factory: `/api/v1` prefix, CORS, error handlers, health, OpenAPI.
- `api/routers/` — one module per resource (games, teams, players, props, rapm, stats, live, models).
- `api/schemas/` — Pydantic response models (the public contract).
- `api/deps.py` — dependency injection: DB session, Redis client, `ModelProvider`.
- `api/services/` — business logic between routers and storage/models (keeps routers thin).

## 2. Model serving (champion loading)

A **`ModelProvider`** loads the current champion for each head from the **MLflow registry** at
startup, holds them in memory, and **hot-reloads** when the promotion gate
([modeling.md §7](modeling.md)) promotes a new champion (poll registry version or react to a
Prefect signal). The API only ever calls `provider.get(head).predict(...)`. This is the concrete
realization of the training/serving split from [architecture.md §7](architecture.md).

## 3. Endpoint surface (v1)

All under `/api/v1`. Read-only (see §7 decision).

**Health & models**
- `GET /health` — liveness.
- `GET /models` — current champions per head + their headline metrics (powers "How it works").

**Games & predictions**
- `GET /games?date=|season=|team=` — schedule + results (paginated).
- `GET /games/{game_id}` — game detail (teams, status, box score).
- `GET /games/{game_id}/prediction` — pre-game `{win_prob, margin, total, market?, explanation}`
  (top-5 drivers; `market` reserved for v2 — [modeling.md §10](modeling.md)).
- `GET /games/{game_id}/prediction/full-explanation` — full SHAP breakdown (on-demand).
- `GET /games/{game_id}/live` — current live win prob + headline drivers (read from Redis).

**Teams & players**
- `GET /teams`, `GET /teams/{team_id}` — profile + as-of ratings.
- `GET /players`, `GET /players/{player_id}` — profile, season stats, recent game logs.
- `GET /players/{player_id}/shots?season=` — shot-chart data (respects `location_reliable`).
- `GET /players/{player_id}/props?game_id=` — PTS/REB/AST/3PM projections + prediction intervals
  + explanation.

**RAPM**
- `GET /rapm?season=|window=` — leaderboard (ORAPM/DRAPM/RAPM, paginated, sortable).
- `GET /players/{player_id}/rapm` — that player's RAPM history.

**Stats hub**
- `GET /stats/leaderboards?stat=&season=` — generic leaderboards.
- `GET /live/games` — today's games with current live win prob.
- `GET /live/games/{game_id}/stream` — live updates (transport per §7 decision).

## 4. Response schemas (key ones)

Reuse the [explainability.md §5](explainability.md) `Explanation` contract everywhere a prediction
appears. Examples:
```
GamePrediction { game_id, win_prob, margin, total, market: Market|null, explanation: Explanation }
PropsProjection { player_id, game_id, stat, point, interval_low, interval_high, explanation }
RapmEntry { player_id, name, season, window, orapm, drapm, rapm, possessions }
LiveWinProb { game_id, win_prob, score, period, clock, headline_drivers: Contribution[] }
```
All list endpoints share a `Page<T> { items, total, page, page_size }` envelope.

## 5. Caching (Redis)

- **Predictions & explanations:** cached on first request with a TTL (pre-game predictions are
  stable until lineups/injuries change); keyed by `game_id` + `feature_version`.
- **Leaderboards & expensive stat queries:** cached with TTL, invalidated after nightly feature
  refresh.
- **Live win prob:** *written* to Redis by the [live-system.md](live-system.md) poller; the API
  just reads it (never computes live inference on the request path).
- A small cache decorator handles get-or-compute + TTL + invalidation keys.

## 6. Cross-cutting

- **Validation/serialization:** Pydantic models everywhere; consistent typed error envelope
  `{ error, detail }` with proper status codes.
- **Pagination/filtering/sorting:** uniform query-param conventions across list endpoints.
- **Docs:** OpenAPI/Swagger auto-served at `/api/v1/docs`.
- **Versioning:** `/api/v1` prefix from day one so v2 (odds/market) can add without breaking.
- **Observability:** structured request logging; basic timing metrics.

---

## 7. Decisions (resolved 2026-06-28)
- **DB access: async SQLAlchemy** — non-blocking calls matching FastAPI's async model; better
  concurrency and a stronger signal. `deps.py` provides an async session.
- **v1 auth: public read-only + basic rate limiting** — it's public stats data; no user accounts
  in v1. Rate-limit to prevent abuse.
- **Live transport: SSE, behind a thin transport abstraction.** SSE fits the one-directional live
  win-prob feed; the abstraction makes a later swap to WebSocket cheap.
  WebSocket is **earmarked for a future interactive feature** (e.g., live community
  predictions/polls) where bidirectional comms is genuinely needed — see
  [master-plan.md](master-plan.md) v2 list. Rationale: SSE is the correct tool for one-way
  pushes; reaching for WebSocket here would be resume-driven, not engineering-driven.

## 8. Build prompts (executable)

> **Prompt 1 — API skeleton.** In `backend/src/nbaforecast/api/`, create the FastAPI app factory
> with `/api/v1` prefix, CORS, a typed error-envelope exception handler, OpenAPI docs, and
> `GET /health`. Wire empty routers for games, teams, players, props, rapm, stats, live, models.

> **Prompt 2 — Dependencies.** In `api/deps.py`, provide DB-session, Redis-client, and
> `ModelProvider` dependencies. Implement `ModelProvider` to load each head's champion from the
> MLflow registry at startup and hot-reload on a new promotion (registry-version poll).

> **Prompt 3 — Schemas.** In `api/schemas/`, define all §4 Pydantic response models, importing the
> `Explanation`/`Contribution` types from `explain/schema.py`, including the reserved `market`
> field and the `Page<T>` envelope.

> **Prompt 4 — Games & predictions routers.** Implement the §3 games endpoints, pulling stored
> data + calling `ModelProvider` for predictions, attaching `Explanation` (top-5; full on the
> dedicated endpoint), with Redis caching per §5.

> **Prompt 5 — Players, props, RAPM, stats routers.** Implement the remaining §3 read endpoints,
> including shot-chart data and the RAPM leaderboard with sorting/pagination.

> **Prompt 6 — Live router + stream.** Implement `GET /live/games`, `GET /games/{id}/live` (Redis
> read), and the live `stream` endpoint using the §7 transport decision.

> **Prompt 7 — Caching layer.** Implement the get-or-compute Redis decorator with TTL and
> invalidation hooks tied to `feature_version` / nightly refresh.

> **Prompt 8 — API tests.** In `backend/tests/api/`, use FastAPI `TestClient` to contract-test each
> endpoint (status, schema shape, pagination, error envelope) against seeded fixtures. Wire into CI.

## 9. Definition of done
- All §3 endpoints serve typed responses validated by `TestClient` tests in CI.
- `ModelProvider` loads champions from MLflow and hot-reloads on promotion.
- Predictions carry the `Explanation`; live endpoints read from Redis.
- OpenAPI docs available; `/api/v1` versioning in place.
