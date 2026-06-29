# RAPM — Regularized Adjusted Plus-Minus

> **Goal:** Estimate each player's independent contribution to point differential per 100
> possessions, controlling for teammates and opponents, via **ridge regression on a sparse
> lineup-stint matrix**. Outputs feed back as features for the other models.
> Parent: [master-plan.md](master-plan.md). Consumes: `possessions` from
> [data-pipeline.md](data-pipeline.md). Feeds: [feature-engineering.md §5](feature-engineering.md).

---

## 1. What RAPM is, and why ridge

**The progression:**
- **Plus-Minus (PM):** point differential while a player is on court. Problem: a bench player on a
  great team looks great; it's polluted by *who he plays with and against*.
- **Adjusted PM (APM):** a regression that puts all 10 on-court players on each possession into one
  model and solves for each player's *independent* effect, controlling for the other nine. Problem:
  **multicollinearity** — players who almost always share the court can't be told apart, so plain
  least-squares produces wild, high-variance coefficients (a deep bench guy might show +40 or −40).
- **RAPM:** APM **+ ridge regression (L2 regularization)**. Ridge adds a penalty on large
  coefficients, shrinking noisy estimates toward zero. This is the whole trick — it tames the
  multicollinearity and turns unstable APM into stable, trustworthy ratings. The strength of that
  shrinkage is the hyperparameter **λ (alpha)**, chosen by cross-validation.

This is genuinely deep, respected basketball analytics *and* a clean demonstration of ridge,
sparse linear algebra, and regularization — strong portfolio substance.

## 2. The model setup

**Unit of analysis: a stint** — a span of consecutive possessions with the same 10 players on
court. A substitution ends one stint and starts the next. (We aggregate possessions into stints
to shrink the matrix; each stint carries its possession count as a weight.)

**Design matrix `X` (sparse):**
- One row per stint.
- Columns: **two per player** — an *offense* column and a *defense* column (the ORAPM/DRAPM split,
  §10 decision). For a stint: each of the 5 offensive players gets `+1` in their offense column;
  each of the 5 defensive players gets `+1` in their defense column; everything else `0`.
- With ~thousands of players across the window and millions of stints, `X` is enormous but
  ~99.9% zeros → **`scipy.sparse` (CSR)** is mandatory.

**Target `y`:** offensive points scored per 100 possessions for that stint.

**Weights:** each stint weighted by its possession count (longer stints = more signal).

**Solve:** ridge regression — minimize `‖y − Xβ‖²_w + λ‖β‖²`. Use `sklearn.linear_model.Ridge`
with sparse input (solver `sparse_cg` or `lsqr`), or the closed-form normal equations for small
windows. The coefficients `β` *are* the ratings: each player's offense coefficient = **ORAPM**,
defense coefficient = **DRAPM**, and **RAPM = ORAPM + DRAPM** (per 100 possessions).

## 3. Choosing λ

λ controls shrinkage and must be cross-validated, **temporally** (no leakage): fit on one period,
measure how well the ratings **retrodict** held-out games' margins, pick the λ minimizing
held-out error. Too small → noisy APM-like estimates; too large → everyone squished toward zero.

## 4. Window & stabilization

- **Multi-year window:** single-season RAPM is noisy (small possession samples). A rolling
  multi-year window (e.g., last 2–3 seasons) is far more stable. Window length is a §10 decision
  and relates to `lookback_seasons`.
- **Stabilization via priors (v2 candidate):** "prior-informed"/Bayesian RAPM seeds the ridge
  with a box-score-based estimate instead of shrinking toward zero (the xRAPM/RPM family). Richer
  but more complex — proposed as a v2 enhancement (§10).

## 5. Outputs & point-in-time use

- Table `player_rapm`: `player_id, as_of_date, window, orapm, drapm, rapm, possessions`.
- **Snapshots, not per-game refits.** Refitting ridge for every historical game is too expensive,
  so we compute RAPM at a fixed cadence (§10) — e.g., per-season-to-date and/or monthly snapshots —
  and downstream features always use the **latest snapshot strictly before game G**. This keeps
  RAPM-as-a-feature **leakage-safe** (per [feature-engineering.md §2](feature-engineering.md)) at
  bounded cost.
- Aggregations for features: minutes-weighted team ORAPM/DRAPM (team strength), and individual
  player RAPM (player quality for props) — wired in [feature-engineering.md §5](feature-engineering.md).

## 6. Evaluation

RAPM has no clean label, so evaluation is indirect (standard in the field):
- **Retrodiction test:** do ratings from period A predict period B game margins with lower RMSE
  than baselines (raw plus-minus, box plus-minus)? This is the headline metric.
- **Out-of-sample stability:** correlation of a player's RAPM across adjacent windows.
- **Face validity:** the top of the leaderboard should be recognizable stars (a sanity report,
  not a metric).

## 7. Build prompts (executable)

> **Prompt 1 — Stint aggregation.** In `backend/src/nbaforecast/models/rapm/stints.py`, from the
> `possessions` table build stints: group consecutive possessions sharing the same 10-player
> lineup into `(offense_player_ids[5], defense_player_ids[5], points, possessions)` rows for a
> given window. Unit-test on a small hand-built possession sequence.

> **Prompt 2 — Sparse design matrix.** In `models/rapm/design.py`, build the sparse `X`
> (`scipy.sparse` CSR) with two columns per player (offense/defense), the weighted target `y`
> (points per 100 poss), and possession weights, plus a `player_index` mapping columns↔player_ids.

> **Prompt 3 — Ridge fit + λ CV.** In `models/rapm/fit.py`, implement `fit_rapm(X, y, weights,
> alpha)` via sparse Ridge, and `select_alpha(...)` that temporally cross-validates λ by
> retrodiction RMSE on held-out games. Return ORAPM/DRAPM/RAPM per player.

> **Prompt 4 — Snapshots + storage.** In `models/rapm/snapshots.py`, compute RAPM at the chosen
> cadence (§10) over the rolling window, and a `player_rapm` SQLAlchemy model + Alembic migration
> + Parquet writer. A Prefect task refreshes the latest snapshot after ingestion.

> **Prompt 5 — Evaluation.** In `models/rapm/evaluate.py`, implement the retrodiction RMSE test
> vs. baselines, cross-window stability, and a face-validity leaderboard report; log results to
> MLflow.

> **Prompt 6 — Feature wiring.** Implement the team/player RAPM aggregations consumed by
> [feature-engineering.md §5](feature-engineering.md), using only snapshots dated before each game.

> **Prompt 7 — Tests.** In `backend/tests/ml/`: (a) a **correctness test** on a tiny synthetic
> league where the true player effects are known and ridge (low λ) should recover them within
> tolerance; (b) a **leakage test** asserting feature wiring only ever uses pre-game snapshots.

## 8. Definition of done
- `player_rapm` populated with ORAPM/DRAPM/RAPM snapshots across the ingested history.
- λ selected by temporal CV; retrodiction RMSE beats raw plus-minus and box plus-minus baselines.
- RAPM aggregations available as leakage-safe features for game prediction and props.
- Correctness + leakage tests green in CI.

## 9. Decisions (resolved 2026-06-28)
- **Formulation: Offense/Defense split** — two coefficients per player (ORAPM + DRAPM), RAPM =
  ORAPM + DRAPM. The matrix and §2/§7 are built for this.
- **Default window: 3-season rolling** (configurable). Balances stability vs. recency; relates to
  `lookback_seasons` but is a RAPM-specific default.
- **Stabilization: plain ridge for v1**, shrinking toward zero. **Box-prior / Bayesian RAPM
  (xRAPM/RPM-style) deferred to v2** (§4, §10).

## 10. Open / deferred
- **Box-prior (Bayesian) RAPM** — proposed v2 enhancement (§4).
- Exact snapshot cadence (per-season vs monthly) — cost vs. freshness; default proposed
  per-season-to-date + monthly during season.
- Whether to publish a public RAPM leaderboard page in the stats hub (likely yes — cheap, cool).
