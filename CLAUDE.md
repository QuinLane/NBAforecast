# CLAUDE.md — NBAforecast working guide

Context bootstrap for any session working on this repo. Read this first.

## What this is
NBAforecast: a web app for NBA stats + **explainable** predictions (game outcomes, props, live
win probability, RAPM), every prediction broken down with SHAP. Located at
`D:\PROJECTS 2026\NBAforecast`.

## Status
M0 and M1 are merged to `main`. Implementation is in **M2** (feature pipeline + vertical slice).
If resuming M2 cold, read `plans/m2-session-protocol.md` next — it has the active build protocol
and a progress tracker of which T2.x tasks are done.

## Start here (planning docs)
- `plans/master-plan.md` — index + every decision made.
- `plans/implementation-plan.md` — the dependency-ordered task checklist (T0.1 → T6.6). **Build in
  this order.**
- `plans/engineering-standards.md` — code structure, naming, git, commits, PR rules.
- `plans/concepts-and-terminology.md` — plain-language ML + project glossary (Quin is new to ML).
- `plans/agent-orchestration.md` — parallel-agent strategy (kicks in at M3).
- `plans/m2-session-protocol.md` — **currently active** M2 build protocol: short chained sessions
  (`/clear` between tasks), per-task branch+PR+squash-merge, one deferred review at the M2 gate.
> Note: `plans/` is committed for now but will be removed after implementation; do not link it from
> the public README.

## Hard rules
- **No Claude/AI attribution** on commits or PRs — authored solely as Quin. (Also enforced via
  `.claude/settings.json`.)
- **Git:** trunk-based; one task per short-lived branch (`feat/T1.2-...`); **squash-merge**;
  **Conventional Commits**. PRs required; CI green before merge.
- **Python:** uv, ruff, `mypy --strict`, line length 100, Google docstrings, `src/` layout.
- **Frontend:** Next.js + TS, shadcn/ui + Tailwind, OpenAPI-generated client, Recharts + D3.
- **Naming/JSON:** snake_case across DB + API; see engineering-standards.md.
- **Build order:** vertical slice first (M2 proves the spine + the `ModelHead` interface).

## Parallel agents
Foundation (M0–M2) is sequential. At **M3**, fan out to parallel subagents in isolated worktrees
(`agent-rapm` / `agent-props` / `agent-game-extras` / `agent-frontend`) — see
`plans/agent-orchestration.md`. **Surface this and confirm with Quin before starting M3.**

## Model guidance
Sonnet 4.6 for mechanical work (M0–M1, boilerplate, parallel agents); Opus 4.8 for
correctness-sensitive work (M2 modeling, leakage, RAPM, calibration, explainability).

## Skills cadence

| Milestone | Code review rule |
|-----------|-----------------|
| M0 T0.4–T0.5 | **None** — stubs ≤ 60 LOC; inline manual scan only |
| M1 tasks | `/code-review` on the one PR per task that has real logic; skip pure boilerplate |
| M2 spine | `/code-review ultra` on every PR — leakage, calibration, and the `ModelHead` interface are hard to fix retroactively. **Temporarily overridden** for the initial M2 build push: see `plans/m2-session-protocol.md` §5 (one deferred review at the gate instead) |
| M3 agent PRs | `/code-review` on each agent PR (parallel work has cross-cutting blind spots) |
| M4–M5 | `/code-review` on PRs with non-trivial logic; skip glue/config |
| M6 | `/security-review` before deploy |

Milestone gates (M2/M4/M5) also get `/verify` + `/run`.

**Why:** the 8-angle skill costs ~13 sub-agent calls per PR. On config/scaffolding that cost
is disproportionate to the risk. Save it for code where bugs are subtle and expensive to
find later (ML correctness, API contracts, live-system timing).
