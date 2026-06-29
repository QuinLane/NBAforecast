# NBAforecast

An NBA stats and prediction web app, with a focus on actually explaining the predictions.

## About

I'm building NBAforecast because most NBA prediction sites do the same thing: they hand you a
number and expect you to trust it. I wanted the opposite. When this app says a team has a 64%
chance to win, it also shows you what's behind that number — rest, matchup history, home court,
recent form, and so on. The prediction and the reasoning come together.

It's two things at once. First, a stats hub: clean NBA stats, shot charts, and leaderboards backed
by a real data pipeline. Second, a prediction engine on top of that data that covers game
outcomes, player props, live in-game win probability, and player value. Every prediction is
broken down so you can see why the model landed where it did, and it's always labeled as the
model's reasoning, not gospel.

## v1 features

| Feature | What it does |
|---------|--------------|
| Game prediction | Win probability, point spread, and total points for upcoming games |
| Player props | Projected points / rebounds / assists / threes per player, with ranges |
| Live win probability | In-game win % that updates off live play-by-play, plus a post-game replay |
| RAPM | Each player's independent on-court value (offense and defense), via regression on lineup data |
| Stats hub | Player and team pages, shot charts, leaderboards |
| Explanations | Every prediction shows its top drivers as a breakdown |

The app ingests the full NBA play-by-play era (1996-97 to present) and trains its models on a
configurable recent window (default around 15 seasons).

## What's coming after v1

- **Shot-quality model** — expected shooting percentage based on where and how a shot was taken.
- **Computer-vision shot tracker** — predicting make/miss from the ball's trajectory in uploaded
  video.
- **Betting-market comparison** — historical odds and a view of where the model disagrees with the
  closing line.
- **Live community predictions** — a real-time interactive layer during games.

## How it works

```
nba_api / pbpstats ─► ingestion ─► raw storage ─► validation
   ─► Postgres + Parquet ─► shared feature pipeline ─► model heads (tracked in MLflow)
   ─► API (+ explanations) ─► web frontend
                       live games ─► poller ─► win prob ─► cache ─► live dashboard
```

A few design choices worth calling out:

- Models are trained offline and the API only ever loads the current best one to serve — it never
  trains on a live request.
- Features are computed strictly from data available before each game, so the models aren't
  secretly peeking at the future. There are automated tests that enforce this.
- New models plug into a shared feature pipeline and a common interface, so adding one doesn't mean
  rewiring everything around it.

## Models

The prediction engine is split into four independent heads that share a single upstream feature
pipeline and a common `ModelHead` interface.

### Game prediction

Three sub-models operating on the same `features_team_game` table:

| Sub-model | Task | Algorithm | Baseline |
|-----------|------|-----------|----------|
| Win probability | Binary classification — home team wins? | LightGBM classifier + isotonic/Platt calibration | Home-always-wins (~58%) and Elo |
| Point margin | Regression — final score difference | LightGBM regressor | Home-court edge constant + rating-difference linear fit |
| Total points | Regression — combined final score | LightGBM regressor | League-average total; teams' season averages |

Calibration is first-class: a 65% prediction should correspond to ~65% historical accuracy.
Post-hoc calibration is applied whenever a reliability curve shows systematic over- or
under-confidence. The win-probability output and its calibration curve are always displayed
alongside predictions.

Features include team Elo ratings, recent net-rating rolling windows (last 5/10/20 games),
rest days, back-to-back flags, home/away splits, pace, and RAPM-derived player quality
estimates for each roster.

### Player props

Four independent LightGBM regressors — one per stat — over `features_player_game`:

| Stat | Baseline |
|------|----------|
| Points (PTS) | Player season average; last-10-game average |
| Rebounds (REB) | Same |
| Assists (AST) | Same |
| Three-pointers made (3PM) | Same |

Each model outputs a point estimate **plus a prediction interval** via LightGBM's quantile
objective (or conformal prediction), so "player projected for 22.4 pts (18–27 80% interval)"
carries an honest uncertainty range — not just a number.

### Live in-game win probability

Two models trained and compared via the walk-forward backtest harness:

- **LightGBM classifier** on `features_game_state` (score differential, time remaining,
  possession, shooting efficiency in-game, momentum runs). Fast inference, TreeSHAP-explainable.
- **Small neural network** (PyTorch MLP) on the same features. Used as a direct comparison
  — same backtest, same evaluation metric — to demonstrate whether non-linear capacity
  adds predictive value at this task.

Both are seeded with the pre-game prior (the batch win-probability estimate), which anchors
the live model at tip-off. The champion is whichever wins on bucketed log-loss + calibration
across held-out historical games; it's selected automatically by the MLflow promotion gate.
The live dashboard shows which model is running.

### RAPM — Regularized Adjusted Plus-Minus

RAPM estimates each player's **independent** contribution to point differential per 100
possessions, controlling for all ten players on the court simultaneously.

**Setup.** The unit of analysis is a *stint* — a contiguous span of possessions with an
unchanged lineup. Each stint becomes one row in a sparse design matrix `X`:
- Two columns per player (offense and defense).
- Each offensive player on court gets `+1` in their offense column; each defensive player
  gets `+1` in their defense column; everything else is `0`.
- With thousands of distinct players across a multi-season window, `X` is enormous (~99.9%
  zeros) and stored as a `scipy.sparse` CSR matrix.
- Target `y`: offensive points scored per 100 possessions for that stint.
- Weights: possession count (longer stints carry more signal).

**Why ridge, not OLS.** Players who share the court frequently are nearly collinear — plain
least squares (APM) produces wild, high-variance coefficients. Ridge regression (L2
regularization) adds a penalty `λ‖β‖²` that shrinks noisy estimates toward zero without
biasing the well-identified ones. The result is stable, trustworthy ratings. λ is chosen by
temporal cross-validation (train on one period, validate on how well ratings retrodict
held-out game margins).

**Output.** Each player's offense column coefficient is **ORAPM**, defense column is
**DRAPM**, and **RAPM = ORAPM + DRAPM** (points per 100 possessions above a replacement-level
player). These ratings feed back into the game-prediction and props feature tables as
player-quality inputs.

### Backtesting and leakage prevention

All models are evaluated with **walk-forward (expanding-window) validation** only. The
training set covers seasons ≤ T; the test set is the next chunk; the window rolls forward
in time. Random k-fold on a time series would shuffle future games into the training set —
this is data leakage and is ruled out architecturally: the harness makes it impossible to
call. Every metric reported is out-of-sample.

A **baseline-floor test** in CI asserts that each head beats its dumb baseline on a fixed
historical holdout before it's allowed to be promoted to production.

### Explainability (SHAP)

Every prediction is decomposed into per-feature contributions using Shapley values from
cooperative game theory. A SHAP value answers: *"how much did this feature push the
prediction above or below the model's average output?"* Contributions are signed and
**sum exactly to `prediction − baseline`** — the additivity property makes the breakdown
honest and enables the waterfall visualization.

Implementation per head:

| Head | Explainer | Why |
|------|-----------|-----|
| Game prediction (LightGBM) | **TreeSHAP** | Exact, polynomial-time for tree ensembles |
| Props (LightGBM) | TreeSHAP | Same |
| Live win prob — LightGBM champion | TreeSHAP | Same |
| Live win prob — NN champion | **GradientSHAP / DeepSHAP** | TreeSHAP doesn't apply to neural nets |
| RAPM (ridge, linear) | Coefficients directly | Linear models are self-explaining |

TreeSHAP contributions for a classifier come out in log-odds space, not probability space.
The app converts these to approximate probability-point contributions
(`Δp ≈ σ(logit + SHAP) − σ(logit)`) for the user-facing waterfall, while preserving the
exact log-odds values for technically inclined viewers.

### MLflow — experiment tracking and model promotion

Every training run logs its hyperparameters, feature version, `lookback_seasons`, and all
evaluation metrics as an MLflow experiment. The **model registry** holds the current
**champion** for each head. A newly trained **challenger** is promoted only if it strictly
beats the champion on the primary held-out metric (log-loss for classifiers, MAE for
regressors) and does not regress calibration. The API never trains at request time — it
always loads the current champion from the registry.

## Tech stack

**Backend / ML:** Python, FastAPI, Postgres, Prefect, MLflow, scikit-learn / LightGBM, SHAP,
S3 (MinIO) + Parquet, Redis
**Frontend:** Next.js + TypeScript, shadcn/ui + Tailwind, Recharts + D3, TanStack Query
**Infra:** Docker, GitHub Actions, uv / pnpm

## Repository layout

```
NBAforecast/
├── README.md
├── backend/     # Python: ingestion, features, models, API
├── frontend/    # Next.js app
└── infra/       # Docker and deploy config
```

## Getting started

Still early in development. Once the stack is wired up, the whole thing runs locally with Docker:

```bash
docker-compose up
```

Prerequisites: Docker Desktop, Python 3.12+, Node 20+, uv, pnpm.

## Data sources

- [nba_api](https://github.com/swar/nba_api) — box scores, shots, play-by-play
- [pbpstats](https://github.com/dblackrun/pbpstats) — possession and lineup data
- [NBA.com Stats](https://www.nba.com/stats) and [ESPN](https://www.espn.com/nba/) — live feeds

## Disclaimer

Predictions are statistical model outputs meant for informational and educational use, not betting
advice. Data comes from publicly available NBA endpoints. Not affiliated with the NBA.

## License

TBD.
