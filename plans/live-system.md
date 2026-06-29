# Live System — In-Game Win Probability

> **Goal:** During live games, pull live play-by-play, compute an updating win probability with
> headline drivers, and push it to the dashboard in near-real-time — the "live lane" that
> deliberately bypasses the nightly batch pipeline.
> Parent: [master-plan.md](master-plan.md). Consumes: [feature-engineering.md](feature-engineering.md)
> (game-state features), [modeling.md](modeling.md) (live champion), [explainability.md](explainability.md).
> Surfaced via [backend-api.md](backend-api.md) (SSE) → [frontend.md](frontend.md).

---

## 1. Shape of the live lane

A dedicated process — the **live poller** (one of the package entrypoints from
[architecture.md §2](architecture.md)) — runs independently of the API and the batch pipeline:

```
live PBP source ─► live poller (every N s, per active game)
   ─► game-state features ─► live win-prob champion (+ pre-game prior)
   ─► headline-driver explanation ─► write Redis + publish channel
                                         ─► API SSE endpoint ─► frontend
```

Keeping it off the request path (the API only *reads* Redis) is what keeps the live dashboard
fast and resilient.

## 2. Components

- **Live data client** — fetches current play-by-play + score/clock for in-progress games from the
  live source (§7 decision), throttled and retried, normalized into the same **game-state** shape
  used in training.
- **Live poller loop** — discovers today's active games, and every `poll_interval` seconds: pulls
  latest state → builds game-state features (reusing `build_game_state_features` from
  [feature-engineering.md §4](feature-engineering.md) for **train/serve parity**) → runs the live
  win-prob champion seeded with the **pre-game prior** → computes headline drivers → writes Redis +
  publishes to the per-game channel. Updates are pushed **only when state changes** (idempotent).
- **Redis live store + pub/sub** — holds the latest `LiveWinProb` per game (for cold reads) and a
  channel per game for SSE fan-out.
- **SSE endpoint** (in API, [backend-api.md §3](backend-api.md)) — subscribes to the Redis channel
  and streams updates to connected clients, behind the transport abstraction (SSE now, WS-ready).
- **Lifecycle scheduler** — from the schedule, determines which games are live, starts polling at
  tip-off, stops at final; backs off (sleeps) when no games are in progress.

## 3. The pre-game → live continuity

At tip-off, the live win prob is seeded by the **pre-game prediction** ([game prediction](modeling.md)),
so the dashboard opens at the same number the pre-game page showed, then evolves with the game.
This is the composition wired in [feature-engineering.md §5](feature-engineering.md).

## 4. Game-state handling & edge cases

- Transitions: tip-off, end of quarter, end of regulation, **overtime**, final.
- Garbage time: win prob saturates near 0/1 — fine and expected; calibration should reflect it.
- No-games days, postponements, double-headers, delayed feeds — the scheduler and client tolerate
  all (skip/backoff, never crash the loop).
- Deduplication: ignore repeated/identical event payloads; only recompute on genuine state change.

## 5. Latency & cadence

Play-by-play granularity is ~event-level (seconds), not sub-second. A `poll_interval` of ~10s
(§7 decision) gives a responsive dashboard without hammering the source. This is intentionally
**not** a low-latency trading system — the engineering interest is the pipeline, not microseconds.

## 6. Persistence (win-prob timeline)

Optionally persist each game's live win-prob series (§7 decision) to enable a **post-game "win
probability over time" replay chart** and historical analysis — cheap to store and a compelling
visual. The live champion's training data itself comes from stored historical PBP via the batch
pipeline, not from this runtime.

---

## 7. Decisions (resolved 2026-06-28)
- **Live source: NBA live (cdn.nba.com) primary + ESPN fallback** — robust to a single feed
  stalling; the client tries NBA first, falls back to ESPN on failure/staleness.
- **Poll cadence: ~10 seconds** (configurable) — responsive without hammering the source.
- **Persist the win-prob timeline: yes** — `live_win_prob_timeline` table per game enables the
  post-game replay chart (§6, build Prompt 6 is in scope).

## 8. Build prompts (executable)

> **Prompt 1 — Live data client.** In `backend/src/nbaforecast/live/client.py`, implement a
> throttled+retried client that fetches current PBP/score/clock for in-progress games from the
> chosen source (§7) and normalizes them into the game-state shape. Handle missing/late feeds
> gracefully. Unit-test normalization against saved sample live payloads.

> **Prompt 2 — Live poller.** In `live/poller.py`, implement the loop: discover active games via
> the scheduler, and per interval build game-state features (reusing
> `build_game_state_features`), run the live champion seeded with the pre-game prior, compute
> headline drivers via `explain()`, and write Redis + publish on state change only.

> **Prompt 3 — Redis live store + pub/sub.** In `live/store.py`, implement latest-value storage
> per game and a publish/subscribe channel per game for SSE fan-out.

> **Prompt 4 — SSE endpoint.** In the API, implement `GET /live/games/{id}/stream` subscribing to
> the Redis channel and streaming `LiveWinProb` updates, behind a `LivePublisher` transport
> abstraction (SSE impl now; interface ready for WebSocket).

> **Prompt 5 — Lifecycle scheduler.** In `live/scheduler.py`, determine active games from the
> schedule, start/stop polling at tip-off/final, and back off when idle. Add `entrypoints/live_poller`.

> **Prompt 6 — Timeline persistence (if chosen).** Persist the per-game win-prob series to a
> `live_win_prob_timeline` table for the replay chart.

> **Prompt 7 — Tests.** Simulate a full game's PBP feed and assert: win prob at tip-off ≈ pre-game
> prior; updates only on state change; final ≈ 1.0/0.0 for the winner; OT handled. Wire into CI.

## 9. Definition of done
- Live poller computes and publishes updating win prob + headline drivers for in-progress games.
- API streams updates via SSE; the dashboard updates live.
- Tip-off equals the pre-game prediction; finals resolve correctly; OT/edge cases handled.
- (If chosen) win-prob timelines persisted for replay.
