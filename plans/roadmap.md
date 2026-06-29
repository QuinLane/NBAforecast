# Roadmap

> **Goal:** Sequence every plan into a concrete build order with milestone definitions-of-done.
> The guiding principle is **vertical slice first** — wire one model head end-to-end (data →
> features → model → explanation → API → UI) before adding breadth, so integration risk is killed
> early rather than discovered at the end.
> Parent: [master-plan.md](master-plan.md). Sequences all other plans.

---

## 1. Build principle: vertical slice, then broaden

Rather than build all of the data layer, then all models, then all UI (you'd see nothing working
for months and hit integration surprises late), we get **one thin path fully working first**, then
add models/pages onto the proven shared infrastructure. The §M2 slice is the de-risking moment.

**Extensibility is a first-class M2 requirement.** The vertical slice must establish a common
**`ModelHead` interface** — a uniform contract (`train()`, `predict()`, `explain()`, feature
dependencies, MLflow registration) that every head implements — so adding props, RAPM, live, or a
future v2 head (shot quality, etc.) is "implement the interface + register," not "rewire the
system." Combined with the shared feature pipeline ([feature-engineering.md](feature-engineering.md))
and the `ModelProvider`/registry ([backend-api.md §2](backend-api.md)), new heads slide in without
touching ingestion, serving, or the frontend's explanation rendering. M2's review checkpoint
explicitly validates that a second head *could* be added cleanly before we proceed to M3.

## 2. Milestones

### M0 — Scaffolding & local stack
Repo scaffold ([architecture.md §6](architecture.md)), `docker-compose`, CI skeleton, `/health`,
Next.js placeholder.
**DoD:** `docker-compose up` runs all services; `/health` 200; CI green.

### M1 — Data pipeline (bronze → silver)
Ingestion clients, bronze landing, silver parse/validate/load with Pandera, Prefect backfill +
daily ([data-pipeline.md](data-pipeline.md)). Backfill the **full PBP era (1996-97 → present)** from
the start (§5 decision) — one upfront ingestion cost, realistic data throughout dev.
**DoD:** the full PBP era backfills idempotently and validated; `possessions` populated; corrupted
payload quarantines + fails loudly.

### M2 — Feature pipeline + first vertical slice ⭐ (de-risking milestone)
Leakage-safe feature primitives + team-game features + materialization
([feature-engineering.md](feature-engineering.md)); the **game-prediction win-prob** model
(logistic + LightGBM) with the backtest harness, MLflow, calibration, baseline-floor
([modeling.md](modeling.md)); its **SHAP** explanation ([explainability.md](explainability.md));
API `/games` + `/games/{id}/prediction` ([backend-api.md](backend-api.md)); frontend game-detail
page + **PredictionExplainer** ([frontend.md](frontend.md)).
**DoD:** pick a game in the UI → see a **calibrated win prob with explained top-5 drivers**, served
end-to-end. No-leakage + SHAP-additivity tests green. *The entire spine is now proven.*

### M3 — Broaden the models (on shared infra)
> ⚠️ **REMIND ABOUT AGENTS HERE.** This is the parallel fan-out point — see
> [agent-orchestration.md](agent-orchestration.md). Build RAPM / props / margin+total / frontend
> pages as concurrent subagents in isolated worktrees.

Add the game **margin + total** regressors; **props** (PTS/REB/AST/3PM) + player features + props
API + props board UI; **RAPM** (stints → sparse ridge → snapshots, [rapm.md](rapm.md)) + leaderboard
API/UI + RAPM-as-feature wiring.
**DoD:** all batch heads live with explanations; RAPM leaderboard + props board functional.

### M4 — Live system
Live poller (NBA cdn + ESPN fallback), game-state features, **both** live win-prob models
(LightGBM + NN, compared), Redis fan-out, **SSE** endpoint, live dashboard + persisted timeline +
replay ([live-system.md](live-system.md)).
**DoD:** live dashboard updates during games; tip-off ≈ pre-game prediction; post-game replay works.

### M5 — Stats hub & polish
Shot charts (D3), player/team profiles, stat leaderboards, **how-it-works** (global SHAP),
SEO + a11y ([frontend.md](frontend.md)).
**DoD:** full stats hub navigable; SEO metadata + how-it-works page in place.

### M6 — Hardening & deploy
Testing completeness (coverage gate + Playwright flow, [testing.md](testing.md)); observability
(Sentry + logs); scheduled retraining flow; deploy to PaaS + domain
([infrastructure.md](infrastructure.md)).
**DoD:** live public URL, CI gates green, monitored, nightly ingestion + retraining running on the
full PBP-era history.

## 3. Dependency flow

```
M0 ─► M1 ─► M2 ⭐ ─► M3 ─► M4 ─► M5 ─► M6
                └► (M3/M4/M5 each build on the M2 spine; orderable but M2 must come first)
```

## 4. v1 "done" definition
All v1 scope from [master-plan.md §3](master-plan.md) shipped: game prediction (win/margin/total),
props (4 stats), live win prob, RAPM — all with calibrated, SHAP-explained outputs — plus the stats
hub, deployed publicly, tested, and monitored, retraining nightly on the full PBP-era history.

## 5. Decisions (resolved 2026-06-28)
- **Build order: vertical slice first** — M2 wires one head end-to-end before broadening. M2 also
  establishes the drop-in **`ModelHead` interface** (§1) so future heads slide in cleanly; a review
  checkpoint validates extensibility before M3.
- **Early backfill: full PBP era from M1** — one upfront ingestion cost, realistic data throughout
  development (not a small subset).
