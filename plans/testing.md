# Testing Strategy

> **Goal:** A layered test strategy that hammers the things which break *silently* — data drift,
> leakage, miscalibration — not just the things that break loudly. All gated in CI.
> Parent: [master-plan.md](master-plan.md). Consolidates tests defined across the other plans.

---

## 1. Philosophy

Most projects test happy-path code and ignore the failures that actually hurt an ML product:
bad data loaded silently, a leaked feature inflating backtest accuracy, probabilities that aren't
calibrated. We invert that — the **data and ML-correctness layers get the most rigor**, because
those bugs are invisible until they've poisoned everything downstream.

## 2. The test layers

| Layer | Tool | What it guards |
|-------|------|----------------|
| **Unit** | pytest | Pure functions: parsers, feature primitives, math, utilities |
| **Data validation** | Pandera | Ingested data matches schema/ranges; corrupted payloads quarantined ([data-pipeline.md §6](data-pipeline.md)) |
| **ML correctness** | pytest | The differentiators — see §3 |
| **API contract** | FastAPI TestClient | Endpoint status, schema shape, pagination, error envelope ([backend-api.md](backend-api.md)) |
| **Frontend** | Vitest + RTL | Components (esp. PredictionExplainer math/labels), hooks |
| **Codegen drift** | CI check | Regenerated OpenAPI client matches committed ([infrastructure.md §3](infrastructure.md)) |
| **E2E / smoke** | (§7 decision) | A real end-to-end path through the running stack |

## 3. ML-correctness tests (the high-value ones)

These are the tests that signal real ML-engineering maturity:
- **No-leakage** — recompute a game's features from only pre-game data; assert equality with the
  materialized row ([feature-engineering.md §2](feature-engineering.md)).
- **Train/serve parity** — `build_*` with `as_of` = a historical tip-off reproduces that game's
  stored training features exactly.
- **Baseline-floor** — each model beats its defined baseline on a fixed sample, or CI fails
  ([modeling.md §3](modeling.md)).
- **Calibration** — predicted probabilities track observed frequencies within tolerance on holdout.
- **SHAP additivity** — `sum(contributions) ≈ prediction − baseline` for every head
  ([explainability.md §8](explainability.md)).
- **RAPM correctness** — on a tiny synthetic league with known true effects, ridge recovers them
  within tolerance; plus the RAPM-as-feature leakage test ([rapm.md §7](rapm.md)).
- **Backtest integrity** — assert the harness can't be invoked with random k-fold (temporal only).

## 4. Fixtures & determinism

- **Saved sample payloads** (one per entity/source) for parsing + validation tests.
- A **tiny synthetic dataset** (a few teams, a partial season) for fast, deterministic ML tests
  that don't need the full backfill.
- **Fixed seeds** everywhere randomness appears → reproducible runs.

## 5. CI gating & speed

- All layers run on every PR; **fast tests by default**. The full multi-season backtest is **not**
  a per-PR test — it runs on a **small sample** in CI and in full as a separate scheduled/manual job.
- Pragmatic coverage targets (§7 decision), focused on core logic — not a vanity 100%.

## 6. End-to-end smoke (thin but real)

`docker-compose up` → ingest a saved sample game → train a tiny model → request a prediction
through the API → assert the response carries a valid, additive `Explanation`. One thin path that
proves the whole spine is wired together.

---

## 7. Decisions (resolved 2026-06-28)
- **Coverage: pragmatic, core-logic focused** (~70–80% on features/models/API; no vanity 100%).
  High-value correctness tests prioritized over coverage of trivial code.
- **E2E: thin smoke path + one Playwright flow** — the §6 docker-compose smoke plus a single
  browser test over a core flow (load a game → see an explained prediction).

## 8. Build prompts (executable)

> **Prompt 1 — Test scaffold.** Set up `backend/tests/` layout (`unit/`, `data_validation/`,
> `ml/`, `api/`), pytest config, shared fixtures (sample payloads, the tiny synthetic dataset),
> and global seed management.

> **Prompt 2 — Ensure ML-correctness suite.** Implement/verify every §3 test exists and is wired,
> each as a fast, deterministic test against the synthetic dataset where possible.

> **Prompt 3 — Frontend test setup.** Configure Vitest + React Testing Library; test
> PredictionExplainer (driver math, label mapping, units toggle) and key hooks; add the OpenAPI
> codegen drift check to CI.

> **Prompt 4 — E2E smoke (per §7).** Implement the §6 end-to-end smoke path; if Playwright chosen,
> add one browser E2E over a core user flow.

> **Prompt 5 — CI wiring.** Run all layers on PR with the fast/slow split and coverage thresholds;
> schedule the full backtest separately.

## 9. Definition of done
- All §2 layers present and green in CI; ML-correctness suite (§3) fully implemented.
- Tests are deterministic (seeded) and fast (heavy backtest split out).
- End-to-end smoke proves the running stack produces an explained prediction.
