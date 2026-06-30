# M2 Session Protocol — context hygiene + resume instructions

> **Why this doc exists:** M2 is 17 tasks (T2.1→T2.17) of real, dependency-ordered engineering —
> feature primitives, the `ModelHead` interface, a calibrated LightGBM model, MLflow, SHAP, a
> FastAPI slice, and a frontend page. Running all of it in one unbroken Claude Code session risks
> context bloat and drift by the time we reach the frontend tasks. This doc is the protocol for
> running M2 as a **chain of short, clean sessions** — one (or a few) tasks per session, `/clear`
> between them — without losing continuity. Parent: [master-plan.md](master-plan.md),
> [implementation-plan.md](implementation-plan.md) §M2.

---

## 1. The workflow per task

For each task `T2.x` in [implementation-plan.md](implementation-plan.md) §M2:

1. `git checkout main && git pull` (main is always the latest merged state — see §3).
2. `git checkout -b feat/T2.x-<short-desc>`.
3. Implement the task per its source build prompt (cited in implementation-plan.md).
4. Local gates green: backend → `uv run ruff check src tests`, `uv run ruff format --check src
   tests`, `uv run mypy src`, `uv run pytest tests/`. Frontend (once wired, T2.15+) → `pnpm lint`,
   `pnpm type-check`, `pnpm test --run`, `pnpm build`.
5. Commit with Conventional Commits, no AI attribution (per CLAUDE.md hard rules).
6. `git push -u origin feat/T2.x-...` → `gh pr create`.
7. **Squash-merge immediately** (`gh pr merge --squash`) — don't wait on CI or hold for review.
   `main` is unprotected, so this always succeeds; CI still runs and its result is visible on the
   PR for the historical record even though it isn't a merge gate right now.
8. Update the progress table in §4 of this doc (status + PR link) before ending the session.
9. `/clear`, then start the next session with the **resume prompt** in §2.

## 2. Resume prompt (paste after `/clear`, or whenever picking this back up cold)

```
Continue NBAforecast M2 implementation.
Repo: D:\PROJECTS 2026\NBAforecast (git repo, main branch, GitHub QuinLane/NBAforecast).
Read CLAUDE.md first, then plans/master-plan.md and plans/implementation-plan.md §M2, then
plans/m2-session-protocol.md (this file) — check the progress table for the next unchecked task.
Follow the per-task workflow in §1 of m2-session-protocol.md exactly: branch off main, implement
the next task's build prompt (cited in implementation-plan.md), get local gates green, commit,
push, open a PR, and squash-merge it immediately — no per-task /code-review (that's deferred to
one consolidated pass at the M2 gate, see §5). Update the progress table when done.
```

## 3. Why squash-merge per task instead of stacking branches

Tasks are dependency-ordered (T2.2 imports code T2.1 lands, etc.), so each task's code must be on
`main` before the next starts — there's no parallel fan-out here (that's M3's
[agent-orchestration.md](agent-orchestration.md) pattern, not applicable to M2's sequential build).
Squash-merging immediately after each PR keeps `main` always buildable and gives every task its
own PR for history, per the user's explicit call for this M2 push — a deliberate, temporary
deviation from the normal "PR sits for review" flow.

## 4. Progress tracker

Update this table as tasks land. PR column filled in once opened.

| Task | Description | Status | Branch / PR |
|------|-------------|--------|--------------|
| T2.1 | Leakage-safe feature primitives | done | [#16](https://github.com/QuinLane/NBAforecast/pull/16) |
| T2.2 | Team–game features + Elo | done | [#17](https://github.com/QuinLane/NBAforecast/pull/17) |
| T2.3 | Feature materialization + refresh | done | [#18](https://github.com/QuinLane/NBAforecast/pull/18) |
| T2.4 | No-leakage + train/serve parity tests | done | [#19](https://github.com/QuinLane/NBAforecast/pull/19) |
| T2.5 | `ModelHead` interface + backtest harness | done | [#20](https://github.com/QuinLane/NBAforecast/pull/20) |
| T2.6 | Baselines + floor test (game-win) | done | [#21](https://github.com/QuinLane/NBAforecast/pull/21) |
| T2.7 | Game win-prob model (logistic + LightGBM + calibration) | done | [#22](https://github.com/QuinLane/NBAforecast/pull/22) |
| T2.8 | MLflow tracking + promotion gate | done | [#23](https://github.com/QuinLane/NBAforecast/pull/23) |
| T2.9 | Metrics module + tests | done | [#24](https://github.com/QuinLane/NBAforecast/pull/24) |
| T2.10 | Explanation schema + TreeSHAP explainer | done | [#25](https://github.com/QuinLane/NBAforecast/pull/25) |
| T2.11 | Feature humanizer | done | [#26](https://github.com/QuinLane/NBAforecast/pull/26) |
| T2.12 | SHAP additivity test | done | [#27](https://github.com/QuinLane/NBAforecast/pull/27) |
| T2.13 | API: deps/`ModelProvider` + schemas + routers | done | [#28](https://github.com/QuinLane/NBAforecast/pull/28) |
| T2.14 | API contract tests (slice) | done | [#29](https://github.com/QuinLane/NBAforecast/pull/29) |
| T2.15 | Generated API client + Query hooks | done | [#30](https://github.com/QuinLane/NBAforecast/pull/30) |
| T2.16 | PredictionExplainer + game-detail page | not started | — |
| T2.17 | E2E smoke path | not started | — |

M2 start point: `main` @ `ec6b42c` (T1.7, full-era backfill — M1 gate).

## 5. Deferred review (the M2 gate)

No `/code-review` per task this milestone (deviation from implementation-plan.md §5's normal
cadence, by explicit user instruction). Instead, **one consolidated review at the end of M2**,
before declaring the ⭐ gate green:
- `/code-review ultra` over the cumulative diff `ec6b42c..HEAD` (all of M2 in one pass) — this is
  still the milestone CLAUDE.md flags as needing the deep multi-agent pass (leakage, calibration,
  the `ModelHead` interface are hard to fix retroactively).
- `/verify` + `/run` per CLAUDE.md's M2 row, exercising the actual UI: game → calibrated win prob
  + explained top-5.
- Confirm the extensibility check from implementation-plan.md's M2 gate: a 2nd head must drop in
  cleanly.

## 6. Change log
- 2026-06-29 — Doc created at the start of M2. Decided to chain short sessions (`/clear` between
  tasks) with per-task branch+PR+squash-merge and one deferred `/code-review ultra` pass at the
  M2 gate, instead of the normal per-PR review cadence — explicit user call for this milestone.
