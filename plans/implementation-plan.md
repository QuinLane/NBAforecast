# Implementation Plan — Execution Sequence

> **Goal:** The ordered, dependency-aware playbook for *building* NBAforecast — which plans get
> implemented first and the build prompts as a concrete task checklist with prerequisites and
> gating tests. Turns the design ([roadmap.md](roadmap.md) milestones) into executable order.
> Parent: [master-plan.md](master-plan.md).

---

## 1. Principles

- **Dependency-ordered:** never build a thing before what it depends on exists.
- **Vertical slice first:** M2 wires one head end-to-end before breadth ([roadmap.md §1](roadmap.md)).
- **One task = one branch = one PR** (small, gated; [engineering-standards.md §6–7](engineering-standards.md)).
- **Each task cites its source build prompt** in the relevant plan — that prompt is the spec; this
  doc is the order.

## 2. Plan implementation order (which plans first)

```
1. engineering-standards + architecture   → conventions + scaffold        (M0)
2. data-model                              → schema must exist first       (M1)
3. data-pipeline                           → land + validate data          (M1)
4. feature-engineering (team scope)        → features for the slice        (M2)
5. modeling (game-win) + explainability + backend-api + frontend (slice)
                                           → ⭐ vertical slice             (M2)
6. modeling (margin/total/props) + rapm    → broaden on shared infra       (M3)
7. stack verification + real champions     → prove the spine on real data  (M3.5)
8. stats browser (player/team pages, box scores, trajectory, leaderboards) → product surface (M3.75)
9. live-system + replay                    → live lane, demoable off-season(M4)
10. market benchmark + report card + injuries → grade the model publicly   (M4.5)
11. frontend (shot charts, how-it-works) + Monte Carlo → charts & polish    (M5)
12. testing (completeness) + infrastructure → harden + deploy              (M6)
```

## 3. Task checklist

Format: **task — source prompt — depends-on**. ✅-gate at each milestone end.

### M0 — Scaffolding
| Task | Source | Depends |
|------|--------|---------|
| T0.1 Repo init, ruff/mypy/pre-commit config, CI skeleton | engineering-standards §1; infra Prompt 3 | — |
| T0.2 Backend package + `pyproject` (uv) + `Settings` | architecture §6 (1–3) | T0.1 |
| T0.3 `docker-compose` full local stack | infra Prompt 1 | T0.2 |
| T0.4 API skeleton + `GET /health` | backend-api Prompt 1 (minimal) | T0.2 |
| T0.5 Next.js + Tailwind + shadcn scaffold | architecture §6 (6) | T0.1 |
| **Gate** | `docker-compose up` → `/health` 200; CI green | |

### M1 — Schema + data pipeline (full PBP era)
| Task | Source | Depends |
|------|--------|---------|
| T1.1 Full schema: SQLAlchemy + Alembic + Parquet schemas | data-model Prompt | T0.2 |
| T1.2 Ingestion clients (throttle/retry) | data-pipeline Prompt 1 | T0.2 |
| T1.3 Bronze `ObjectStore` (MinIO/S3) | data-pipeline Prompt 2 | T0.3 |
| T1.4 Silver parse + Pandera + upsert repos | data-pipeline Prompt 3 | T1.1–T1.3 |
| T1.5 Prefect backfill + daily flows + checkpoint | data-pipeline Prompt 4 | T1.4 |
| T1.6 Data-validation tests | data-pipeline Prompt 5 | T1.4 |
| T1.7 Run full-era backfill (1996-97→present) | roadmap M1 | T1.5 |
| **Gate** | full era backfilled idempotently + validated; `possessions` populated; quarantine works | |

### M2 — Feature pipeline + vertical slice ⭐ + `ModelHead` interface
| Task | Source | Depends |
|------|--------|---------|
| T2.1 Leakage-safe feature primitives | feature-eng Prompt 1 | T1.4 |
| T2.2 Team-game features + Elo | feature-eng Prompt 2 | T2.1 |
| T2.3 Feature materialization + refresh (team) | feature-eng Prompt 5 | T2.2 |
| T2.4 No-leakage + train/serve parity tests | feature-eng Prompt 6 | T2.3 |
| T2.5 **`ModelHead` interface** + backtest harness | modeling Prompt 1 + roadmap §1 | T2.3 |
| T2.6 Baselines + floor test (game-win) | modeling Prompt 2 | T2.5 |
| T2.7 Game win-prob model (logistic + LightGBM + calibration) | modeling Prompt 3a | T2.5 |
| T2.8 MLflow tracking + promotion gate | modeling Prompt 6 | T2.7 |
| T2.9 Metrics module + tests | modeling Prompt 8 | T2.5 |
| T2.10 Explanation schema + TreeSHAP explainer (game) | explainability Prompts 1–2 | T2.7 |
| T2.11 Feature humanizer | explainability Prompt 3 | T2.2 |
| T2.12 SHAP additivity test | explainability Prompt 6 | T2.10 |
| T2.13 API: deps/`ModelProvider` + schemas + games & prediction routers | backend-api Prompts 1–4 | T2.8, T2.10 |
| T2.14 API contract tests (slice) | backend-api Prompt 8 | T2.13 |
| T2.15 Generated API client + Query hooks | frontend Prompt 2 | T2.13 |
| T2.16 PredictionExplainer + game-detail page | frontend Prompts 3, 6 | T2.15 |
| T2.17 E2E smoke path | testing Prompt 4 | T2.16 |
| **⭐ Gate** | UI: game → calibrated win prob + explained top-5; no-leakage + additivity green; **extensibility review: a 2nd head must drop in cleanly** before M3 | |

### M3 — Broaden the heads
> ⚠️ **Agent fan-out point.** Build these as parallel subagents per
> [agent-orchestration.md](agent-orchestration.md) (`agent-rapm` / `agent-props` /
> `agent-game-extras` / `agent-frontend`). The main session must surface that plan and confirm with
> the user **before** starting M3.

| Task | Source | Depends |
|------|--------|---------|
| T3.1 Game margin + total regressors | modeling Prompt 3b/c | T2.5 |
| T3.2 Player-game features + materialize | feature-eng Prompt 3 | T2.1 |
| T3.3 Props models (PTS/REB/AST/3PM) + intervals | modeling Prompt 4 | T3.2 |
| T3.4 RAPM stints | rapm Prompt 1 | T1.4 |
| T3.5 RAPM sparse design matrix | rapm Prompt 2 | T3.4 |
| T3.6 RAPM ridge fit + λ CV | rapm Prompt 3 | T3.5 |
| T3.7 RAPM snapshots + storage + refresh | rapm Prompt 4 | T3.6 |
| T3.8 RAPM evaluation | rapm Prompt 5 | T3.7 |
| T3.9 RAPM→feature wiring + leakage/correctness tests | rapm Prompts 6–7 | T3.7, T2.2 |
| T3.10 API: players/props/rapm/stats routers | backend-api Prompt 5 | T3.3, T3.7 |
| T3.11 Frontend: props board, RAPM leaderboard, player pages | frontend Prompt 6 | T3.10 |
| T3.12 Global SHAP artifacts at train time | explainability Prompt 4 | T2.10 |
| **Gate** | all batch heads live + explained; RAPM leaderboard + props board functional | |

### M3.5 — Stack verification on real data (added 2026-07-01)
> Both the M2 and M3 gates deferred the real end-to-end run: the docker stack has never been
> browser-verified, and no champion model has ever been trained on real data and promoted (several
> endpoints 503 without one). M4 builds Redis/SSE/poller on top of that base — prove it first.
> Also produces the trained champions that M4.5 (report card) and M5 (Monte Carlo) consume.

| Task | Source | Depends |
|------|--------|---------|
| T3.13 Stack up + full-era backfill verification (docker-compose, migrations, Prefect flows on real data) | m2-gate deferral | T3.9 |
| T3.14 Real training runs → MLflow champion promotion for **all** heads (win/margin/total/props) + RAPM snapshot refresh | modeling Prompt 6 | T3.13 |
| T3.15 Browser walkthrough of every page against the live stack; fix wiring bugs found | roadmap M3.5 | T3.14 |
| **Gate** | every page renders real predictions + explanations from the dockerized stack; zero 503s; wiring bugs fixed | |

### M3.75 — Stats browser (added 2026-07-07)
> The stats-hub core pulled forward from M5: player/team pages, box scores, a stat-trajectory
> chart, head-to-head lookup, leaderboards, quick-search. All plain queries over already-ingested
> data — no new sources, no ML risk. Player pages become **stats-first**: props (next-game
> relevance) on top, then a trajectory chart, then season/career tables and game logs. The RAPM
> trajectory lives on the player page, never the leaderboard (snapshot comparison ≠ self-over-time).

| Task | Source | Depends |
|------|--------|---------|
| T3.16 Player headshots + team logos hotlinked from the NBA CDN (shared components, id-keyed, fallbacks) | roadmap M3.75 | T3.11 |
| T3.17 Backend: player stat trajectory + season/career aggregate endpoints (per-game series + season averages; RAPM series already served) | backend-api §4 | T3.14 |
| T3.18 Frontend: player page restructure — props → trajectory chart (tabs PTS/REB/AST/3PM/MIN/RAPM) → season/career tables → game log | frontend Prompt 6 | T3.16, T3.17 |
| T3.19 Backend: game box score endpoint (team + player lines for a finished game) | backend-api §3 | T3.14 |
| T3.20 Frontend: box score section on the game detail page | frontend Prompt 6 | T3.19 |
| T3.21 Backend: team detail (roster + record + recent games) + head-to-head history endpoints | backend-api §3-4 | T3.14 |
| T3.22 Frontend: team pages (roster/record/recent) + head-to-head view | frontend Prompt 6 | T3.21 |
| T3.23 Backend: stat leaderboards endpoint (LeaderboardEntry schema already stubbed) | backend-api §4 | T3.14 |
| T3.24 Frontend: leaderboards page + header quick-search (players/teams) | frontend Prompt 6 | T3.23 |
| **Gate** | player pages read props → trajectory → stats → log; any finished game shows its box score; team pages show roster/record/head-to-head; leaderboards + search work | |

### M4 — Live system (replay-first)
> **Replay is a first-class design constraint, not a bolt-on:** the live pipeline must accept an
> archived play-by-play source interchangeably with the live feed (same interface), so any past
> game can be replayed through the *identical* code path. This makes the live system demoable
> year-round (the NBA off-season runs July–October) and doubles as the T4.10 simulation harness.

| Task | Source | Depends |
|------|--------|---------|
| T4.1 Game-state features | feature-eng Prompt 4 | T2.1 |
| T4.2 Live data client (NBA cdn + ESPN fallback) + **archived-PBP replay source behind the same interface** | live Prompt 1 | T0.2 |
| T4.3 Live win-prob models (LightGBM + NN, compared) | modeling Prompt 5 | T4.1, T2.7 (prior) |
| T4.4 Redis live store + pub/sub | live Prompt 3 | T0.3 |
| T4.5 Live poller | live Prompt 2 | T4.1–T4.4 |
| T4.6 SSE endpoint + transport abstraction | live Prompt 4 | T4.4 |
| T4.7 Lifecycle scheduler + `live_poller` entrypoint | live Prompt 5 | T4.5 |
| T4.8 Timeline persistence | live Prompt 6 | T4.5 |
| T4.9 Live dashboard + SSE hook + timeline scrubber | frontend Prompt 5 | T4.6, T4.8 |
| T4.10 Live simulation tests (drive the replay source) | live Prompt 7 | T4.2, T4.5 |
| T4.11 Curated famous-games replay library: 5–10 iconic games (big comebacks etc.) replayable one-click through the real pipeline, scrubber + per-moment win prob & SHAP drivers | this table (spec inline) | T4.9 |
| **Gate** | live dashboard updates; tip-off ≈ pre-game; a curated famous game replays end-to-end with scrubber + explanations, **with no live NBA games on** | |

### M4.5 — Market benchmark, report card & availability (added 2026-07-01)
> **Framing rule:** the market benchmark measures *how close a transparent model gets to the most
> efficient benchmark that exists* — calibration and honesty, never implied betting edge. Closing
> lines encode injury/lineup news; that's also why availability features live in this milestone.

| Task | Source | Depends |
|------|--------|---------|
| T4.12 Historical closing-odds ingest (free archives: Kaggle / sportsbookreview, ~2007→present; spread/total/moneyline; bronze→silver like any source) | modeling §10 (market field) | T1.4 |
| T4.13 Nightly closing-line capture job (The Odds API free tier, one snapshot per slate) | modeling §10 | T4.12 |
| T4.14 Market backtest job: grade persisted predictions vs. closing lines — rolling Brier/log-loss vs. market, calibration curves, ATS record, props hit rates | modeling Prompt 8 (metrics) | T4.12, T3.14 |
| T4.15 **Public report card** API + page: nightly-updated honest self-grading (losses shown, not hidden) | this table (spec inline) | T4.14 |
| T4.16 Injury/availability ingestion (official NBA injury report via nba_api; ESPN fallback) | data-pipeline pattern (Prompt 1) | T1.4 |
| T4.17 Availability features (e.g. top-N-by-RAPM available flags, minutes-weighted availability) + wiring into team/player features + leakage tests (as-of report time only) | feature-eng Prompts 2–3 pattern | T4.16, T3.9 |
| **Gate** | report card live with real backtest vs. closing lines; nightly capture running; availability features in champions with no-leakage tests green | |

### M5 — Shot charts, Monte Carlo & polish
> Player/team profiles + leaderboards moved forward to M3.75; M5 keeps shot charts, how-it-works,
> Monte Carlo, and polish.

| Task | Source | Depends |
|------|--------|---------|
| T5.1 ShotChart (D3) | frontend Prompt 4 | T3.10 |
| T5.2 How-it-works page (global SHAP) | frontend Prompt 6 | T3.12 |
| T5.3 SEO + a11y | frontend Prompt 7 | T5.2 |
| T5.4 Frontend component tests | frontend Prompt 8 | T2.16 |
| T5.5 Monte Carlo season simulator: simulate remaining season ~10k× off the game head → playoff/seed/title odds per team, nightly refresh + API + fan-chart page | this table (spec inline) | T3.14 |
| T5.6 Props uncertainty bands (quantile intervals rendered **underneath the point estimate**, e.g. "27.5 pts" with an 80% band 18–37 below it) + prediction provenance in UI ("model vX · trained through DATE · features as of tip-off") | this table (spec inline) | T3.11, T2.8 |
| **Gate** | hub navigable; SEO metadata + how-it-works page; Monte Carlo page live; props show bands + provenance | |

### M6 — Hardening & deploy
| Task | Source | Depends |
|------|--------|---------|
| T6.1 Testing completeness: coverage gate + Playwright flow | testing Prompts 1–5 | all |
| T6.2 Observability: structured logging + Sentry | infra Prompt 5 | all |
| T6.3 Scheduled retraining flow | modeling Prompt 7 | T2.8 |
| T6.4 Prod Dockerfiles | infra Prompt 2 | T0.3 |
| T6.5 Deploy config (PaaS) + secrets | infra Prompt 4 | T6.4 |
| T6.6 Domain + launch | roadmap M6 | T6.5 |
| **Gate** | public URL; CI green; monitored; nightly ingestion + retraining on full history | |

## 4. Workflow per task
Branch `feat/<task>` → implement the cited build prompt → tests + ruff + mypy green → **`/code-review`
the diff** (and `/simplify` for a tidy pass if useful) → PR with the
[§7 checklist](engineering-standards.md) → squash-merge to `main`. Update the source plan doc if the
design shifted.

## 5. Skills to invoke (when)

Built-in Claude Code skills to call at the right moments — don't forget these.

| Skill | When to invoke |
|-------|----------------|
| **`/code-review`** | Before opening **every** PR. Catches bugs + cleanup — high value given the ML-correctness risks. |
| **`/code-review ultra`** | On the **big branches only** (e.g., the M2 spine) — deeper multi-agent cloud review. Billed, user-triggered. |
| **`/simplify`** | Optional tidy pass after a feature works, before the PR. |
| **`/verify`** | At **each milestone gate from M2 on** (M2, M4, M5 especially) — proves the change actually works end-to-end, not just that tests pass. |
| **`/run`** | Anytime (M2+) you want eyes on the live app/API. |
| **`/review`** | **M3** — review each parallel-agent PR before squash-merge. |
| **`/security-review`** | **M6, before deploy** (public web app + API), and periodically after. |
| **`/fewer-permission-prompts`** | Occasionally, once prompts pile up — extend the allowlist. |
| **`consolidate-memory`** | Occasional housekeeping as memory grows. |

Per-milestone quick reference: **M2** → `/code-review` (ultra), `/verify`, `/run`. **M3** →
`/review` per agent PR. **M3.5** → `/verify` + `/run` (that milestone *is* verification).
**M3.75** → `/code-review` on the endpoint/query PRs (leakage-free aggregation, N+1 avoidance);
skip pure UI glue. **M4–M5 (incl. M4.5)** → `/verify`, `/run`; `/code-review` on non-trivial-logic
PRs (market backtest math, availability leakage, Monte Carlo). **M6** → `/security-review`.

## 6. Definition of done (project)
Every milestone gate green through M6; v1 scope from [master-plan.md §3](master-plan.md) shipped,
deployed, tested, monitored.
