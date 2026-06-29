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
