# NBAforecast — Project Explainer

> A plain-language but technically precise breakdown of the whole project: what it is, how the
> pieces fit, why the hard decisions were made, and how to talk about it in an interview.
> Self-contained on purpose — it doesn't depend on the `plans/` docs.
>
> Sections marked **(planned)** describe design that is decided but not yet built; everything
> else is implemented and tested on `main`.

---

## 1. The elevator pitch (30 seconds)

> "NBAforecast is a full-stack NBA prediction platform whose defining feature is that **every
> prediction shows its reasoning**. It ingests the entire NBA play-by-play era (1996 to today)
> through a validated data pipeline, trains several machine-learning models on it — game winners,
> point margins, player stat lines, player value — and serves each prediction with a SHAP
> breakdown of exactly which factors drove it and by how much. It also grades itself in public:
> a report card page compares its predictions to Vegas closing lines and shows its own misses.
> It's a real deployed product — data engineering, ML, MLOps, API, and frontend, built end to end
> by one person."

The one-word theme: **glass box** (vs. black box). Two expressions of it:
1. **Local transparency** — every single prediction ships with its top drivers ("Boston 64% — the
   biggest factors: rest advantage +5.1 points of probability, opponent missing their center…").
2. **Global honesty** — the model's overall track record is published and updated nightly,
   including against the betting market, including the losses. *(planned — M4.5)*

## 2. What the product does

| Feature | What the user sees | Model behind it |
|---|---|---|
| Game predictions | Pre-game win probability, projected margin, projected total, each with an explained top-5 driver breakdown | LightGBM classifier (calibrated) + two LightGBM regressors |
| Player props | Projected PTS / REB / AST / 3PM per player per game, with an uncertainty band under the point estimate | LightGBM **quantile regression** — three boosters per stat (lower / median / upper) |
| RAPM leaderboard | A player-value ranking that isolates each player's on-court impact from who they play with | Ridge regression on a sparse lineup matrix (see §6) |
| Live win probability *(planned — M4)* | An in-game dashboard where win probability updates every ~10s with explained swings; famous past games replayable with a scrubber | LightGBM + neural net compared, on game-state features |
| Report card *(planned — M4.5)* | Nightly self-grading: calibration curves, Brier score vs. Vegas closing lines, props hit rates | Backtest job over persisted predictions vs. ingested odds |
| Monte Carlo season odds *(planned — M5)* | Playoff / seed / title probabilities per team, from simulating the rest of the season ~10,000× | The game head, run in a simulation loop |
| Stats hub | Team/player pages, leaderboards, shot charts | Same data pipeline, no model |

## 3. Architecture — the journey of one data point

Monorepo: one installable Python package (`backend/`) with multiple entrypoints (API, worker,
trainer), plus a Next.js frontend. The whole stack runs locally with `docker-compose` at $0.

```
nba_api / pbpstats  →  Prefect flows  →  BRONZE (raw JSON in MinIO/S3)
        →  parse + Pandera validation  →  SILVER (Postgres + Parquet)
        →  feature pipeline  →  GOLD (feature tables)
        →  model heads (train under MLflow; champion promotion gate)
        →  FastAPI serving (+ SHAP explanation per prediction)
        →  OpenAPI-generated TypeScript client  →  Next.js frontend
```

Stage by stage, in interview terms:

1. **Ingestion (bronze).** Prefect (a workflow orchestrator — think "cron with retries, logging,
   and backfill support") pulls schedules, box scores, and play-by-play from NBA endpoints with
   throttling and retry. Raw responses are stored untouched as JSON in object storage (MinIO
   locally, S3 in prod). *Why keep raw?* If a parser bug is found later, you re-parse history
   instead of re-downloading it; the raw layer is the source of truth.
2. **Validation + load (silver).** Parsers turn raw JSON into typed rows; **Pandera** schemas
   validate every dataframe (types, ranges, nullability) before load. Corrupted payloads are
   quarantined and fail loudly rather than silently polluting training data. Clean data lands in
   **Postgres** (serving queries) and **Parquet** (columnar files for fast bulk ML reads) — same
   data, two access patterns.
3. **Features (gold).** A shared feature pipeline computes model inputs (rolling team form, Elo
   ratings, rest days, pace, player usage, RAPM aggregates…) and materializes them to feature
   tables. Every feature is **leakage-safe by construction** (§8.1).
4. **Training.** Each model is a `ModelHead` (§7) trained by a harness that does walk-forward
   backtesting, logs everything to **MLflow**, and only promotes a new "champion" if it beats the
   incumbent *without regressing calibration*.
5. **Serving.** FastAPI (async SQLAlchemy) loads champions from the MLflow registry, computes
   predictions plus SHAP explanations, and returns typed JSON. The frontend's API client is
   **generated from the OpenAPI spec**, so backend and frontend types can't drift apart silently.

Full play-by-play era ingested from the start (1996-97 → present); training uses a configurable
lookback (default ~15 seasons).

## 4. The models, plainly

**Game win probability** — the flagship. A logistic-regression baseline (any fancy model must
beat it — the "floor test") and a **LightGBM** gradient-boosted tree model, followed by
**isotonic calibration**. Two things to be able to say crisply:

- *Why gradient boosting?* Tabular data with mixed feature types and non-linear interactions is
  where boosted trees still beat neural nets; they're also fast to train and TreeSHAP gives exact
  explanations.
- *What is calibration and why care?* A model can rank games well but output distorted
  probabilities (say, "80%" teams winning only 70% of the time). Isotonic regression is a
  post-processing step that remaps raw scores so predicted probabilities match observed
  frequencies. For a product whose entire pitch is trustworthy probabilities, calibration is a
  first-class metric — the promotion gate refuses a challenger that improves accuracy but
  regresses calibration.

**Margin + total** — LightGBM regressors on the same team features (projected point differential
and combined score).

**Player props** — for each stat (PTS/REB/AST/3PM), *three* LightGBM boosters trained with
`objective="quantile"` at lower/median/upper alphas. The median is the point estimate; the
lower/upper pair forms an honest **prediction interval** ("27 points, 80% range 18–37"). This is
why the UI can show uncertainty bands: the model actually estimates the distribution, not just
its center. (Quantile crossing — independently-fit lower/upper trees occasionally inverting on
noisy inputs — is handled explicitly.)

**Live win probability *(planned)*** — same idea as pre-game but on game-state features (score
differential, time remaining, possession, lineup on floor), retrained per era. LightGBM and a
small neural net are both trained and compared — a deliberate "show your work" comparison.

## 5. Explainability — how "show the why" actually works

- **SHAP** (SHapley Additive exPlanations) assigns each feature a signed contribution to one
  specific prediction, based on Shapley values from game theory: a feature's value is what it
  adds averaged over all possible orderings of features being revealed. For tree models,
  **TreeSHAP** computes this exactly (not approximated) and fast.
- The key property is **additivity**: baseline + sum of all feature contributions = the model's
  actual output. There is a test asserting this within tolerance for every explained prediction —
  the explanation *provably reconciles* with the prediction; it isn't a plausible story bolted on.
- One subtlety worth telling: SHAP explains the *uncalibrated* model score (log-odds), and the
  isotonic step can't be attributed feature-by-feature. So contributions are converted to
  probability points via a telescoping sigmoid sum, and the headline number is synced to the
  calibrated value actually served.
- A **humanizer** registry maps raw feature names to plain-English labels and phrasing
  ("`team_rest_days_diff` → 'rest advantage'"), so the UI shows sentences, not column names.
- At train time, **global SHAP** artifacts (mean |SHAP| importance, dependence data) are logged
  to MLflow — powering a "how the model thinks overall" page, distinct from per-prediction views.

## 6. RAPM in plain terms

Raw plus-minus (team score margin while a player is on court) is polluted by teammates and
opponents. **RAPM (Regularized Adjusted Plus-Minus)** fixes that with a big regression:

1. Split every game into **stints** — stretches where the same ten players are on the floor.
2. Build a huge sparse matrix: one row per stint, one column per player (+1 if on offense on
   that stint, −1 if on defense); the target is points per possession on that stint.
3. Solve with **ridge regression** (L2 regularization). Regularization is essential because the
   matrix is wildly collinear — teammates who always play together are statistically hard to
   separate — and ridge shrinks noisy estimates toward zero instead of letting them explode.
   The shrinkage strength λ is chosen by cross-validation.
4. Output: each player's isolated offensive (ORAPM) and defensive (DRAPM) impact per 100
   possessions, computed on a 3-season rolling window, snapshotted over time.

RAPM is both a product feature (the leaderboard) and a **model input**: player RAPM feeds props
features, and possession-weighted roster aggregates feed team features — joined **as-of** each
game date so no snapshot from the future leaks in.

## 7. The `ModelHead` interface — the extensibility story

Every model implements one contract: `train()`, `predict()`, `explain()`, declared feature
dependencies, MLflow registration. Serving looks models up in a `HEAD_REGISTRY`; if a head's
champion is loaded, its predictions attach to the response.

The payoff, proven in practice: M2 built exactly *one* head end-to-end (win probability) and
validated the interface; M3 then added margin, total, four props heads, and RAPM **without
touching ingestion, serving infrastructure, or the frontend's explanation rendering** — several
of them built by parallel agents in isolated worktrees, precisely because the seams were clean.
This is the strongest architecture answer in the project: *design the interface in the vertical
slice, then broadening is mechanical.*

## 8. The hard problems (best interview stories)

### 8.1 Data leakage — the silent killer
Leakage = training on information unavailable at prediction time. In sports it's everywhere: a
rolling average that includes tonight's game, a season stat computed over the full season, an
as-of join grabbing a future RAPM snapshot. Defenses, in layers:
- Feature primitives are **leakage-safe by construction** — rolling windows that end strictly
  before the game being predicted; as-of joins (`merge_asof` backward) that only look at
  snapshots dated on or before game date.
- **Explicit no-leakage tests**: perturb a future game's data and assert past features don't move.
- **Walk-forward backtesting**: evaluation always trains on the past, predicts the next slice —
  never random shuffles, which leak in time series.

### 8.2 Train/serve parity
A classic production-ML failure: features computed one way in the training pipeline and slightly
differently at serving time, degrading the model invisibly. Solution: **one shared feature
pipeline** feeds both, and parity tests assert that training-time and serving-time computations
produce identical values for identical inputs.

### 8.3 Trustworthy probabilities
Covered in §4/§5: calibration as a promotion-gate metric, plus provable (additive) explanations.

### 8.4 Honest evaluation vs. the market *(planned — M4.5)*
Vegas closing lines are the strongest public benchmark — they encode injuries, lineup news, and
sharp money. **The model will not beat them, and the report card doesn't pretend otherwise.** The
interesting question is *how close a fully transparent model gets*, and whether its probabilities
are as well-calibrated. Framing this correctly signals you understand market efficiency — a claim
of "beating Vegas" would signal the opposite.

### 8.5 The live lane and replay *(planned — M4)*
Live serving is an architecture change, not just a faster model: a poller hits play-by-play every
~10s → game-state features → live model → **Redis** (pub/sub fan-out) → **SSE** stream → dashboard.
(SSE = one-way server push over plain HTTP — simpler than WebSockets, and prediction streaming is
inherently one-way.) The design constraint that makes it portfolio-proof: the archived-play-by-play
**replay source implements the same interface as the live feed**, so iconic past games replay
through the identical pipeline — demoable in the off-season, and it doubles as the simulation test
harness.

## 9. Engineering practice (the "would I want them on my team" layer)

- **Testing:** ~330 backend + frontend tests. The interesting ones are ML-specific: no-leakage,
  SHAP additivity, calibration metrics, baseline-floor, train/serve parity, API contract tests,
  and an E2E smoke path that runs HTTP → real model → real SHAP → typed response.
- **Rigor:** Python under `mypy --strict` + ruff; typed FastAPI schemas; snake_case contract
  across DB, API, and frontend; the TS client generated from OpenAPI (no hand-written fetch code).
- **Git/process:** trunk-based, one task per short-lived branch, squash-merge, Conventional
  Commits, PRs with CI green required. ~40 PRs to date.
- **MLOps:** MLflow experiment tracking + model registry; champion/challenger promotion with a
  calibration guard; scheduled retraining (planned M6); predictions persisted to Postgres, which
  is what makes the report card possible later.
- **Ops (planned M6):** structured logging + Sentry, prod Dockerfiles, PaaS deploy, nightly
  ingestion + retraining.

## 10. Interview Q&A crib sheet

**"Walk me through the architecture."** → §3, in order. Emphasize bronze/silver/gold and *why*
each layer exists, then the ModelHead seam.

**"How do you prevent data leakage?"** → §8.1. Say "by construction, by test, and by evaluation
design" — three layers.

**"Why LightGBM and not deep learning?"** → Tabular, medium-sized, heterogeneous features:
boosted trees are state of the art there; exact TreeSHAP explanations; cheap retraining. The live
model deliberately trains an NN alongside for comparison.

**"How do you know your explanations are right?"** → Additivity test (§5): baseline + contributions
must equal the served output. Explanations reconcile, or the build fails.

**"Can it beat Vegas?"** → No, and it doesn't claim to (§8.4). Recite the framing: closing lines
encode information the model can't see (injuries broke an hour ago, sharp money); the product
measures distance-to-market and calibration honestly. This answer earns more respect than any
accuracy claim.

**"What was the hardest bug/design problem?"** → Pick one: SHAP-vs-isotonic attribution (§5),
leakage-safe RAPM as-of wiring (§6), or quantile crossing in props (§4).

**"How would you scale it?"** → Currently polling + batch, sized to reality (30 games/night max).
Clear upgrade paths: streaming ingestion (Redpanda/Kinesis) if load justified, read replicas,
model servers behind the same registry. The point: knowing *when not to* over-engineer.

**"How would you add a new model?"** → Implement `ModelHead`, register in `HEAD_REGISTRY`, done —
and that this was validated by actually doing it five times in M3 (§7).

**"What would you do differently?"** → Honest answer available: the live docker stack ran too long
unverified while unit/smoke tests stayed green — fixed by inserting a dedicated verification
milestone (M3.5) once the debt was visible. Shows process self-correction.

## 11. Mini-glossary

| Term | Plain meaning |
|---|---|
| Bronze / silver / gold | Raw as-downloaded data / cleaned+validated data / model-ready features |
| Pandera | Library that validates dataframes against a declared schema |
| Prefect | Workflow orchestrator: scheduled, retryable, observable data jobs |
| MLflow | Experiment tracker + model registry (versioned models, metrics, artifacts) |
| Champion / challenger | The model version currently serving / a candidate trying to replace it |
| Calibration | Predicted probabilities matching real-world frequencies |
| Isotonic regression | Non-parametric remapping of scores to calibrated probabilities |
| SHAP / TreeSHAP | Per-prediction feature attributions with the additivity guarantee / exact fast version for trees |
| Quantile regression | Predicting a distribution's quantiles (e.g. 10th/50th/90th), not just the mean |
| RAPM | Player impact isolated via ridge regression over lineup stints |
| Ridge (L2) | Regularization that shrinks coefficients to tame collinear/noisy data |
| Walk-forward backtest | Time-ordered evaluation: train on past, predict next window, repeat |
| As-of join | Join that takes the latest record *at or before* a timestamp — never after |
| SSE | Server-Sent Events: one-way server→browser push over HTTP |
| Elo | Rolling strength rating updated after each game result |
