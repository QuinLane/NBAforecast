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

### M3.5 — Stack verification on real data *(added 2026-07-01)*
The M2 and M3 gates both deferred the real end-to-end run. Before building the live lane on top:
docker stack up → full-era backfill verified → real training runs → MLflow champion promoted for
**every** head → browser walkthrough of every page; fix wiring bugs found. Produces the real
champions that M4.5 and M5's Monte Carlo consume.
**DoD:** every page renders real predictions + explanations from the dockerized stack; zero 503s.

### M3.75 — Stats browser *(added 2026-07-07)*
The stats-hub core, pulled forward from M5. The site should be a place people visit to look up
*any* stat easily ("how did the Wolves play last time against the Knicks?") — predictions are the
differentiator, but stats are the product surface they hang on. Everything here is plain queries
over already-ingested data: zero ML risk, high visitor-facing value, and M4/M4.5 get better when
team/player pages exist to hang injuries and odds on. Player pages become stats-first: projected
props on top (next-game relevance), then a **stat trajectory chart** (tabs: PTS/REB/AST/3PM/MIN/
RAPM; per-game + rolling average for loaded seasons, season-by-season career mode once the full-era
backfill lands — RAPM uses the monthly snapshot cadence), then season/career tables and game logs.
Plus: full box scores on game pages, team pages (roster/record/recent games), head-to-head history,
stat leaderboards, and header quick-search. Trajectory lives on player pages, **not** the RAPM
leaderboard — the leaderboard compares players at one snapshot; a trajectory compares a player
against himself.
**DoD:** player pages read like a stat site (props → trajectory → stats → log); any finished game
shows its full box score; team pages show roster/record/head-to-head; leaderboards + search work.

### M4 — Live system (replay-first)
Live poller (NBA cdn + ESPN fallback), game-state features, **both** live win-prob models
(LightGBM + NN, compared), Redis fan-out, **SSE** endpoint, live dashboard + persisted timeline
([live-system.md](live-system.md)). **Replay is a first-class design constraint:** an archived-PBP
source sits behind the same interface as the live feed, so any past game replays through the
identical pipeline — capped by a curated **famous-games replay library** (5–10 iconic games,
one-click, timeline scrubber, per-moment win prob + SHAP drivers). Keeps the hero feature demoable
through the July–October off-season and doubles as the simulation-test harness.
**DoD:** live dashboard updates during games; tip-off ≈ pre-game prediction; a curated famous game
replays end-to-end with scrubber + explanations even with no live NBA games on.

### M4.5 — Market benchmark, report card & availability *(added 2026-07-01)*
Historical closing-odds ingest (free archives ~2007→present) + nightly closing-line capture (The
Odds API free tier); market backtest job grading persisted predictions vs. closing lines; a
**public report card** page — nightly-updated honest self-grading (rolling Brier/log-loss vs.
market, calibration curves, ATS record, props hit rates — losses shown, not hidden). Plus
**injury/availability ingestion** (official NBA injury report) and availability features with
leakage tests — the biggest predictive gap, and what closing lines already encode.
**Framing rule:** "how close does a transparent model get to the most efficient benchmark" —
calibration and honesty, never implied betting edge.
**DoD:** report card live on real backtest vs. closing lines; nightly capture running; availability
features in champions, no-leakage green.

### M5 — Shot charts, Monte Carlo & polish
Shot charts (D3), **how-it-works** (global SHAP), SEO + a11y ([frontend.md](frontend.md)) —
player/team profiles and leaderboards moved forward to M3.75. Plus the **Monte Carlo season
simulator** (simulate the remaining season ~10k× off the game head → playoff/seed/title odds,
nightly, fan-chart page), **props uncertainty bands** rendered underneath the point estimate
(quantile heads already exist), and **prediction provenance** in the UI (model version ·
trained-through date · features as-of).
**DoD:** shot charts live; SEO metadata + how-it-works page in place; Monte Carlo page live;
props show bands + provenance.

### M6 — Hardening & deploy
Testing completeness (coverage gate + Playwright flow, [testing.md](testing.md)); observability
(Sentry + logs); scheduled retraining flow; deploy to PaaS + domain
([infrastructure.md](infrastructure.md)).
**DoD:** live public URL, CI gates green, monitored, nightly ingestion + retraining running on the
full PBP-era history.

## 3. Dependency flow

```
M0 ─► M1 ─► M2 ⭐ ─► M3 ─► M3.5 ─► M3.75 ─► M4 ─► M4.5 ─► M5 ─► M6
                └► (M3+ each build on the M2 spine; M3.5 proves it on real data; M3.75 makes the
                    stats surface a product before the live lane lands on top)
```

## 4. v1 "done" definition
All v1 scope from [master-plan.md §3](master-plan.md) shipped: game prediction (win/margin/total),
props (4 stats), live win prob, RAPM — all with calibrated, SHAP-explained outputs — plus the
market benchmark + public report card, famous-games replay, Monte Carlo season odds, and the stats
hub, deployed publicly, tested, and monitored, retraining nightly on the full PBP-era history.

## 5. Decisions (resolved 2026-06-28)
- **Build order: vertical slice first** — M2 wires one head end-to-end before broadening. M2 also
  establishes the drop-in **`ModelHead` interface** (§1) so future heads slide in cleanly; a review
  checkpoint validates extensibility before M3.
- **Early backfill: full PBP era from M1** — one upfront ingestion cost, realistic data throughout
  development (not a small subset).

## 6. Decisions (resolved 2026-07-01 — portfolio restructure)
- **M3.5 inserted** — the deferred live-stack verification + first real champion promotions become
  their own gate before M4 (both M2 and M3 called green without them; the debt stops here).
- **Betting-market benchmark pulled from v2 into v1 (M4.5)** — historical archives are free; go-
  forward capture fits The Odds API free tier ($0/mo). Framed strictly as calibration vs. the most
  efficient public benchmark, never betting edge.
- **Public report card (M4.5)** — nightly honest self-grading; the glass-box thesis extended from
  "explain each prediction" to "grade the whole model in public."
- **Injury/availability features (M4.5)** — biggest predictive gap; required for the market
  comparison to be meaningful (closing lines already price availability).
- **Replay-first M4** — archived-PBP source behind the live-feed interface + curated famous-games
  library, so the live system demos year-round (off-season = July–October).
- **Monte Carlo season simulator + props uncertainty bands (under the point estimate) +
  prediction provenance (M5)** — cheap rides on existing heads/MLflow metadata.

## 7. Decisions (resolved 2026-07-07 — stats-browser pull-forward)
- **M3.75 inserted (stats-hub core pulled forward from M5)** — the site is a stats browser first,
  a predictor on top: all data is already ingested, the work is queries + UI, and M4/M4.5 features
  need team/player pages to land on. M5 keeps shot charts, Monte Carlo, and polish.
- **Player pages are stats-first** — props (next-game relevance) on top, then a trajectory chart
  with stat tabs, then season/career tables and game logs.
- **RAPM trajectory lives on player pages, not the leaderboard** — the leaderboard is a
  single-snapshot cross-player comparison; trajectories compare a player against himself (shorter
  careers just mean shorter lines). Career RAPM is shown as the per-season path, **never** a
  possession-weighted average across eras (reintroduces sample-size skew and cross-era
  incomparability).
- **Monthly RAPM snapshot cadence** — `player_rapm` now stores month-start + season-end snapshots
  (the trainer's `--rapm-monthly`), so within-season progression is chartable from one backfilled
  season; the same chart becomes a career path after the full-era backfill.
- **Player headshots + team logos hotlinked from the NBA public CDN** — keyed by the same ids we
  store; initials/spacer fallbacks. Fine for a non-commercial portfolio; a licensed image API
  (SportsDataIO/Sportradar) would be needed if this ever became commercial.
