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

### M3.9 — v1 feature finish *(added 2026-07-08)*
The last push before deploy. Everything here works on already-ingested data (plus the full-era
backfill running in parallel). Built in this order:

0. **Full-era backfill** *(in progress)* — 1996→present, unblocked by making possessions optional
   pre-2019 (`ingest_game` skips them <2019; era-aware checkpoint completeness). Concurrency
   (`ingest_concurrency`, default 4) overlaps network latency behind the request throttle;
   structured progress logs make a detached run watchable. Runs while the features below are built.
   Also here: the **team-roster fix** (current-season, latest-team-only — no more Kennard-on-two-teams).
1. **Shot chart** — half-court make/miss plot on the **player page** (scatter first, hexbin-vs-league
   heatmap second); per-game and team-aggregate versions later. Data + `ShotChartEntry` already exist.
2. **In-game win-probability timeline** — the replay/"thinking" view, on the **game page under the
   score** for finished games (live later). Requires **game-state features + an in-game win-prob
   head** (pulled forward from M4); replays stored play-by-play through it to draw a win-prob curve
   with a scrubber and a per-moment SHAP "thinking" panel. **No live poller/SSE/Redis** — that infra
   stays in the backlog. This is the single highest-impact feature and reuses the ModelHead/SHAP spine.
3. **Monte Carlo season simulator** — simulate the remaining season ~10k× off the game-win head →
   a league-wide **`/projections`** page (standings, playoff/seed/title odds) plus a per-team snippet
   on each **team page**.
4. **Landing page** — a real home page (hook, live title-odds teaser from Monte Carlo, entry points).
5. **T5.6 — props uncertainty bands + prediction provenance** *(built last)* — quantile intervals
   under each props point estimate; model-version/trained-through/features-as-of provenance in the UI.

**DoD:** shot charts on player pages; a finished game shows its win-prob timeline + thinking panel;
`/projections` + team snippets live; a real landing page; props show bands + provenance. Then
reevaluate: deploy (M6) or pull an item back from the backlog.

### M4 — Live real-time system *(DEFERRED to Future Additions, 2026-07-08)*
> Deferred for engineering cost (Redis, SSE, live poller, a second NN model), **not** any video
> issue — replay uses play-by-play data, never footage. The post-game win-prob timeline (M3.9 #2)
> delivers the explainable-replay payoff now; this milestone is the real-time delivery layer on top.

Live poller (NBA cdn + ESPN fallback), game-state features, **both** live win-prob models
(LightGBM + NN, compared), Redis fan-out, **SSE** endpoint, live dashboard + persisted timeline
([live-system.md](live-system.md)). **Replay is a first-class design constraint:** an archived-PBP
source sits behind the same interface as the live feed, so any past game replays through the
identical pipeline — capped by a curated **famous-games replay library** (5–10 iconic games,
one-click, timeline scrubber, per-moment win prob + SHAP drivers). Keeps the hero feature demoable
through the July–October off-season and doubles as the simulation-test harness.
**DoD:** live dashboard updates during games; tip-off ≈ pre-game prediction; a curated famous game
replays end-to-end with scrubber + explanations even with no live NBA games on.

### M4.5 — Market benchmark, report card & availability *(DEFERRED to Future Additions, 2026-07-08; added 2026-07-01)*
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

### M5 — How-it-works & polish *(mostly absorbed into M3.9, 2026-07-08)*
Shot charts, the Monte Carlo simulator, props uncertainty bands, and provenance were pulled forward
into **M3.9**; player/team profiles + leaderboards were pulled into M3.75. What's left of M5 is the
**how-it-works** page (global SHAP) and **SEO + a11y** ([frontend.md](frontend.md)) — small enough
to fold into the M3.9→M6 transition.
**DoD:** how-it-works page in place; SEO metadata + a11y pass done.

### M6 — Hardening & deploy
Testing completeness (coverage gate + Playwright flow, [testing.md](testing.md)); observability
(Sentry + logs); scheduled retraining flow; deploy to PaaS + domain
([infrastructure.md](infrastructure.md)).
**DoD:** live public URL, CI gates green, monitored, nightly ingestion + retraining running on the
full PBP-era history.

## 3. Dependency flow

```
M0 ─► M1 ─► M2 ⭐ ─► M3 ─► M3.5 ─► M3.75 ─► M3.9 ─► (M5 leftovers) ─► M6 ─► deploy
                                              └► v1 finish: backfill, shot chart, in-game
                                                 timeline, Monte Carlo, landing, props bands

  Future Additions (post-v1 backlog, deferred 2026-07-08):
    • M4  — live real-time system (poller/SSE/Redis) + famous-games replay library
    • M4.5 — market benchmark + public report card + injury/availability features
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

## 8. Decisions (resolved 2026-07-08 — v1 refocus)
- **M3.9 inserted; M4 (live) + M4.5 (market) deferred to a post-v1 backlog.** Finish a rich,
  deployable v1 first; the real-time delivery layer and market/report-card work come after.
- **Replay uses play-by-play data, never video.** The timeline replays the stored event stream
  through the model and renders our own win-prob curve + SHAP — no video API, storage, cost, or
  licensing. (Real NBA game video is league/broadcaster-licensed and enterprise-priced; embedding
  official clips is the only legal route and isn't needed.) So the deferral of M4 is purely about
  live-infra cost, not any footage problem.
- **In-game win-prob timeline pulled forward into M3.9** — the explainable-replay payoff (win-prob
  curve + per-moment "thinking" panel on the game page, finished games first) needs only game-state
  features + a new in-game win-prob head, not the live poller/SSE/Redis stack. Highest-impact
  feature; reuses the ModelHead/SHAP spine.
- **Full-era backfill unblocked by making possessions optional pre-2019** — cdn.nba.com only serves
  possessions from 2019-20, so pre-2019 games land box/pbp/shots without them and are checkpoint-
  complete (era-aware `required_entities`). **RAPM is offered from 2019-20 onward only** (its 3-season
  window never needs older possessions); pre-2019 RAPM would require deriving possessions from raw
  v3 play-by-play — a separate backlog research task. Backfill also gained modest concurrency and
  progress logging (watchable via `backfill.log`).
- **Team roster = current season, latest team only** — fixes traded players appearing on two teams
  and stops a full-era backfill from listing decades of alumni.
- **Monte Carlo lives on a league-wide `/projections` page + per-team snippets**; shot charts live
  on player pages first. Props uncertainty bands + provenance (old T5.6) are built **last** in M3.9.

## 9. Future Additions (post-v1 backlog)
Deferred but specced — pull back after v1 ships and is deployed:
- **Live real-time system (M4)** — live poller (NBA cdn + ESPN fallback), Redis fan-out, SSE, live
  dashboard, and the curated famous-games replay library. The M3.9 in-game timeline is the batch/
  post-game half; this is the real-time delivery layer.
- **Market benchmark + public report card + injury/availability (M4.5)** — closing-odds ingest,
  nightly line capture, market backtest, the public self-grading report card, and availability
  features.
- **Historical RAPM (pre-2019)** — derive possessions from raw v3 play-by-play to extend RAPM before
  2019-20.
- **Computer-vision shot tracker** (master-plan v2 idea) — make/miss from video; out of v1 scope.
