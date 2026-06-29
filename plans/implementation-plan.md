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
7. live-system                             → live lane                     (M4)
8. frontend (hub) + explainability (global)→ stats hub & polish            (M5)
9. testing (completeness) + infrastructure → harden + deploy               (M6)
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

### M4 — Live system
| Task | Source | Depends |
|------|--------|---------|
| T4.1 Game-state features | feature-eng Prompt 4 | T2.1 |
| T4.2 Live data client (NBA cdn + ESPN fallback) | live Prompt 1 | T0.2 |
| T4.3 Live win-prob models (LightGBM + NN, compared) | modeling Prompt 5 | T4.1, T2.7 (prior) |
| T4.4 Redis live store + pub/sub | live Prompt 3 | T0.3 |
| T4.5 Live poller | live Prompt 2 | T4.1–T4.4 |
| T4.6 SSE endpoint + transport abstraction | live Prompt 4 | T4.4 |
| T4.7 Lifecycle scheduler + `live_poller` entrypoint | live Prompt 5 | T4.5 |
| T4.8 Timeline persistence | live Prompt 6 | T4.5 |
| T4.9 Live dashboard + SSE hook + replay | frontend Prompt 5 | T4.6, T4.8 |
| T4.10 Live simulation tests | live Prompt 7 | T4.5 |
| **Gate** | live dashboard updates; tip-off ≈ pre-game; replay works | |

### M5 — Stats hub & polish
| Task | Source | Depends |
|------|--------|---------|
| T5.1 ShotChart (D3) | frontend Prompt 4 | T3.10 |
| T5.2 Team/player profiles, leaderboards, how-it-works | frontend Prompt 6 | T3.12 |
| T5.3 SEO + a11y | frontend Prompt 7 | T5.2 |
| T5.4 Frontend component tests | frontend Prompt 8 | T2.16 |
| **Gate** | hub navigable; SEO metadata + how-it-works page | |

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
`/review` per agent PR. **M4–M5** → `/verify`, `/run`. **M6** → `/security-review`.

## 6. Definition of done (project)
Every milestone gate green through M6; v1 scope from [master-plan.md §3](master-plan.md) shipped,
deployed, tested, monitored.
