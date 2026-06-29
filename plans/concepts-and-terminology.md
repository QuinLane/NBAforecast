# Concepts & Terminology

> **Goal:** A plain-language reference for the machine-learning ideas and the technical terms used
> across these plans — written for someone who hasn't done ML before, with a simple explanation
> first and a more technical one after.
> Parent: [master-plan.md](master-plan.md).

---

## 1. How model training works

### The simple version
A "model" is just a function: facts go in, a prediction comes out. **Training** is showing that
function thousands of past examples *where we already know the answer*, and letting it adjust
itself until it's good at reproducing those answers — so it can then handle new situations it
hasn't seen. It's like studying years of past exams: you're not memorizing specific questions,
you're learning the patterns so you can answer new ones.

In our case:
- **Features** = everything known *before* a game (days of rest, team ratings, home/away, recent form).
- **Label** = what actually happened (home team won; final points).
- We feed the model tens of thousands of historical games; it learns "when the features look like
  *this*, the home team tends to win about *that* often."

**Why we hold data back:** if you only test a model on the exact games it studied, it can cheat by
memorizing — looking great but useless on new games. So we always test on games it never saw in
training. For us specifically, we train on the *past* and test on the *future* (walk-forward),
because that's how it will actually be used.

### The more technical version
This is **supervised learning**: a dataset of rows `(X = features, y = label)`. The model has
internal **parameters**, and training searches for the parameter values that **minimize a loss
function** — a number measuring how wrong the predictions are. For win probability we use
**log-loss**, which punishes confident-and-wrong predictions hardest. That search is an
**optimization** process.

After training we check **generalization** on held-out (future) data, watch for **overfitting**
(memorizing noise instead of real patterns), and fix it with **regularization** and the train/test
split. We also **calibrate** so the probabilities are honest, and use **SHAP** to explain each
finished prediction.

**Lifecycle in our system:** data → features → train offline → backtest → register the best model
in MLflow → API loads it and serves → retrain on a schedule. The app never trains while answering a
request; it just loads the already-trained champion.

## 2. The model types we use

| Model | Plain idea | Why we use it |
|-------|-----------|---------------|
| **Logistic regression** | Learns a weight per feature, adds them up, squashes the total into a 0–1 probability via an S-curve. | Simple, interpretable **baseline** every main model must beat. |
| **Gradient-boosted trees (LightGBM)** | Builds many small decision trees in sequence, each correcting the previous ones' mistakes; hundreds combine into a strong predictor. | Our **main** models — excellent on tabular data (games, props, live). |
| **Ridge regression** | Linear regression plus a penalty that stops coefficients from blowing up. | The engine of **RAPM** — tames the multicollinearity of lineup data. |
| **Neural network** | Layers of weighted connections that learn flexible patterns. | One **live win-prob** variant, compared against LightGBM. |

"Gradient boosting" = each new tree is a step downhill on the loss function (gradient descent).

## 3. ML glossary

- **Feature** — a model input (e.g., `days_rest`). **Label/target** — the answer we train toward
  (win/loss, points).
- **Supervised learning** — learning from labeled examples.
- **Loss function** — how wrong the model is; training minimizes it. **Log-loss** rewards honest
  probabilities; **MAE/RMSE** measure regression error (points off).
- **Train/test split** — separating data used to learn from data used to check. **Walk-forward** —
  our time-ordered version: train on the past, test on the future (never random shuffling, which
  would leak the future).
- **Overfitting** — memorizing noise; great on training data, bad on new data.
- **Regularization** — penalties (like ridge's L2) that keep a model simple to fight overfitting.
- **Calibration** — making predicted probabilities match reality (a "65%" wins ~65% of the time).
- **Cross-validation** — systematically testing on held-out slices to tune choices.
- **Baseline** — a dumb reference (e.g., "home team always wins") the real model must beat.
- **Hyperparameter** — a setting you choose before training (e.g., ridge's λ, tree count); tuned
  by cross-validation.
- **Prediction interval** — a range, not a point ("18–26 pts"), expressing uncertainty; we get it
  via **quantile regression**.
- **SHAP / Shapley values** — a fair way to split a prediction into per-feature contributions that
  sum to `prediction − baseline`; powers "show the why."

## 4. Project & architecture glossary

- **Bronze / silver / gold (medallion)** — raw dumped data → cleaned/validated tables → feature
  tables. ([data-pipeline.md](data-pipeline.md))
- **Idempotency** — running a step twice yields the same result, no duplicates (via upserts).
- **Data leakage / point-in-time correctness** — a feature for a game may only use data available
  *before* tip-off; violating this fakes great backtests that fail live. ([feature-engineering.md](feature-engineering.md))
- **Train/serve skew** — computing a feature differently at training vs prediction time; avoided by
  one shared feature library.
- **Feature store** — where computed features are materialized for reuse; ours is lightweight.
- **Champion / challenger** — the live model vs a newly trained candidate; the candidate is
  promoted only if it provably beats the champion. ([modeling.md](modeling.md))
- **MLflow registry** — the catalog telling the API which model is current.
- **RAPM / possession / stint** — player value via ridge on lineup data; a **possession** is one
  team's offensive trip; a **stint** is consecutive possessions with the same 10 players on court.
  ([rapm.md](rapm.md))
- **Parquet** — a columnar file format; fast/cheap for analytics. **ORM** — Python classes mapped
  to DB tables (SQLAlchemy). **Migration** — a versioned DB schema change (Alembic).
- **Orchestration / DAG** — scheduling pipeline steps as a dependency graph (Prefect).
- **SSE (Server-Sent Events)** — one-way server→client live updates over HTTP (our live dashboard).
- **SHAP additivity** — the property (and our test) that contributions sum to `prediction − baseline`.
