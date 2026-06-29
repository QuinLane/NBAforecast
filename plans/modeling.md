# Modeling

> **Goal:** Train, evaluate, and serve the three tabular prediction heads — game prediction,
> player props, live win probability — with honest **leakage-free backtesting**, **calibrated
> probabilities**, MLflow tracking, and an automated **champion/challenger** promotion gate.
> Parent: [master-plan.md](master-plan.md). Consumes: [feature-engineering.md](feature-engineering.md).
> RAPM has its own doc: [rapm.md](rapm.md). Explainability: [explainability.md](explainability.md).

---

## 1. Philosophy

1. **Baseline first, always.** Every head ships with a dumb baseline. A model that can't beat its
   baseline isn't allowed to be promoted (enforced by a test). This keeps us honest.
2. **Interpretable by default.** Logistic/linear baseline → gradient boosting (LightGBM). We
   reach for neural nets only where they clearly earn it. SHAP makes the boosted models legible.
3. **Probabilities must be calibrated.** A 65% prediction should win ~65% of the time. We measure
   and, if needed, post-hoc calibrate.
4. **Shared features only.** Every head reads the materialized `features_*` tables — no model
   computes its own features (no train/serve skew).

## 2. The three heads (proposed)

| Head | Target | Type | Model (baseline → main) | Primary metric |
|------|--------|------|-------------------------|----------------|
| **Game prediction** | (a) home win · (b) point margin · (c) total points | 1 classification + 2 regressions | logistic/ridge → **LightGBM** (3 sub-models) | win: log-loss + calibration; margin/total: MAE |
| **Player props** | PTS · REB · AST · 3PM (per player) | regression (4 models per stat) | ridge → **LightGBM regressor** | MAE + interval coverage |
| **Live win prob** | home team wins, per game-state | binary classification | logistic(score_diff,time) → **LightGBM *and* NN (compared)** | log-loss by time-bucket |

**Decided (v1 scope):**
- **Game prediction outputs all three:** win probability, point margin (spread), and total points.
  The win-prob classifier is the hero; margin and total are LightGBM regressors sharing the same
  `features_team_game`.
- **Live win prob builds two models — LightGBM *and* a small neural net — and compares them**
  honestly via the backtest harness (a model-selection narrative for the portfolio). Champion is
  whichever wins on bucketed log-loss + calibration.
- **Props: four stats** — PTS, REB, AST, 3PM — each its own regressor with prediction intervals.
- **Betting-market benchmark deferred to v2.** v1 uses internal baselines only (§3). But model
  output schemas reserve room for a later market comparison, and the [data-pipeline.md](data-pipeline.md)
  /[frontend.md](frontend.md) keep "historical odds source" on the v2 list so the future UI can
  show edge vs. the closing line.

## 3. Baselines (the floor each head must clear)

- **Game prediction:**
  - *win:* "home team always wins" (~57–60% historically) and a plain **Elo** model.
  - *margin:* constant home-court edge (~+2.5) and rating-difference linear fit.
  - *total:* league-average total, and the two teams' average totals.
- **Props:** player's season average, and last-10-game average, for each stat (PTS/REB/AST/3PM).
- **Live win prob:** logistic regression on just `score_diff` + `seconds_remaining`.

A **baseline-floor test** fails CI if a candidate model doesn't beat these on the walk-forward
holdout.

## 4. Backtesting harness (the heart of the system)

The single most important component — get this wrong and every metric is a lie.

- **Walk-forward (expanding/rolling window) validation only.** Train on seasons ≤ T, test on the
  next chunk, roll forward in time. **Never random k-fold** — shuffling future and past together
  is leakage.
- Respects **`lookback_seasons`** (default ~15; see [data-pipeline.md §9](data-pipeline.md)) — the
  training window is a parameter the harness sweeps.
- Produces **out-of-sample** predictions across history → all reported metrics are honest.
- Built-in experiment: **metric vs. `lookback_seasons`** (the portfolio chart that justifies the
  window choice empirically).

## 5. Evaluation metrics

- **Classification (games, live):** log-loss (primary — rewards honest probabilities), Brier
  score, AUC, accuracy, and a **calibration/reliability curve**.
- **Regression (props):** MAE, RMSE, and **prediction-interval coverage** (does the 80% interval
  actually contain the outcome ~80% of the time?).
- **Calibration is first-class**, not an afterthought — it's what makes "show the why" honest and
  what a sharp viewer will check.

## 6. Calibration & uncertainty

- Gradient boosting is often miscalibrated; apply post-hoc **isotonic or Platt** calibration on a
  held-out slice when the reliability curve warrants it.
- **Props intervals:** quantile regression (LightGBM quantile objective) or conformal prediction
  to produce honest prediction intervals, not just point estimates.

## 7. MLflow: tracking + champion/challenger promotion

- **Track** every run: params, `lookback_seasons`, `feature_version`, all §5 metrics, and the
  model artifact.
- **Registry** holds the current **champion** per head. A newly trained **challenger** is promoted
  **only if** it beats the champion on the walk-forward holdout primary metric by a configurable
  margin **and** does not regress calibration. Otherwise the champion stays. This gate is
  automated — no silent "latest = live."
- The API only ever loads the champion (see [backend-api.md](backend-api.md)).

## 8. Retraining

A Prefect flow runs after nightly ingestion + feature refresh succeed: assemble training set →
backtest/evaluate → log to MLflow → apply promotion gate → (auto-promote or keep champion).
Cadence configurable (e.g., weekly full retrain; daily refresh of live model). Reproducible via
fixed seeds.

## 9. Build prompts (executable)

> **Prompt 1 — Backtesting harness.** In `backend/src/nbaforecast/training/backtest.py`,
> implement walk-forward validation: given a head, a `lookback_seasons` value, and a feature
> table, train on seasons ≤ T and predict the next chunk, rolling forward; return out-of-sample
> predictions + per-fold metrics. Assert (test) that no test-fold row's data predates training
> incorrectly and that random k-fold is impossible to invoke by accident.

> **Prompt 2 — Baselines + floor test.** In `models/*/baseline.py`, implement the §3 baselines
> (home-always-wins, Elo, season/last-10 averages, score-diff logistic). In
> `backend/tests/ml/test_baseline_floor.py`, assert each main model beats its baseline on a fixed
> historical sample.

> **Prompt 3 — Game-prediction models.** In `models/game_prediction/`, over `features_team_game`
> implement three sub-models sharing the feature set: (a) a logistic baseline + LightGBM
> **classifier** for home-win probability with optional isotonic calibration; (b) a LightGBM
> **regressor** for point margin; (c) a LightGBM **regressor** for total points. All trained/
> evaluated through the backtest harness. Expose `predict_game(game_id)` returning
> `{win_prob, margin, total}` from the champions, with the schema leaving an optional `market`
> field for the v2 odds comparison.

> **Prompt 4 — Props models.** In `models/props/`, implement per-stat LightGBM regressors for
> **PTS, REB, AST, 3PM** over `features_player_game`, each with quantile-based prediction
> intervals; evaluate MAE + interval coverage via the harness.

> **Prompt 5 — Live win-prob models (two, compared).** In `models/win_probability/`, implement
> **both** a LightGBM classifier and a small neural net (PyTorch) over `features_game_state`,
> each seeded with the pre-game prior (§5 of [feature-engineering.md](feature-engineering.md)).
> Evaluate both via the harness on log-loss bucketed by game time + calibration; the promotion
> gate selects the better as champion. Keep a shared interface so either can serve.

> **Prompt 6 — MLflow + promotion gate.** In `training/registry.py`, wrap MLflow logging and a
> `promote_if_better(head, challenger_run)` implementing the §7 champion/challenger gate.

> **Prompt 7 — Retraining flow.** In `training/flows.py`, a Prefect flow chaining assemble →
> backtest → log → gate, scheduled after ingestion. Reproducible (seeded).

> **Prompt 8 — Metrics module + tests.** In `training/metrics.py`, implement log-loss, Brier,
> AUC, calibration curve, MAE/RMSE, interval coverage; unit-test against known values.

## 10. Decisions (resolved 2026-06-28)
- **Game output:** win probability **+ point margin + total points** (all three). Win-prob is the
  hero; margin/total are regressors on the same team-game features.
- **Live model:** build **both** LightGBM **and** a small NN and compare; champion = better on
  bucketed log-loss + calibration.
- **Props stats:** **PTS, REB, AST, 3PM** (four regressors).
- **Market benchmark:** **v1 = internal baselines only**; historical-odds source + "edge vs.
  closing line" UI deferred to **v2**, but output schemas reserve a `market` field for it.

## 11. Definition of done
- Walk-forward backtest produces honest out-of-sample metrics for all three heads.
- Each head beats its baseline (floor test green in CI).
- Probabilities are calibrated (reliability curve checked); props ship with interval coverage.
- MLflow logs every run; champion/challenger gate governs what the API serves.
- Retraining flow runs post-ingestion and auto-manages promotion.
