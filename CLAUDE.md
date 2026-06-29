# CLAUDE.md — NBAforecast working guide

Context bootstrap for any session working on this repo. Read this first.

## What this is
NBAforecast: a web app for NBA stats + **explainable** predictions (game outcomes, props, live
win probability, RAPM), every prediction broken down with SHAP. Located at
`D:\PROJECTS 2026\NBAforecast`.

## Status
Planning is **complete**. Implementation proceeds from **roadmap M0** (scaffolding).

## Start here (planning docs)
- `plans/master-plan.md` — index + every decision made.
- `plans/implementation-plan.md` — the dependency-ordered task checklist (T0.1 → T6.6). **Build in
  this order.**
- `plans/engineering-standards.md` — code structure, naming, git, commits, PR rules.
- `plans/concepts-and-terminology.md` — plain-language ML + project glossary (Quin is new to ML).
- `plans/agent-orchestration.md` — parallel-agent strategy (kicks in at M3).
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

### When to run `/code-review`
Run only on PRs with real logic — not scaffolding or config. Cost is high (~13 sub-agents at full
effort); reserve it for catches that are hard to fix retroactively.

| Milestone | Rule |
|-----------|------|
| M0 T0.4–T0.5 | **Skip** — stubs ≤60 LOC; inline manual scan only |
| M1 tasks | Run on the one logic-heavy PR per task; skip pure boilerplate |
| M2 spine | Run on **every** PR (`/code-review ultra`) — leakage + calibration bugs are expensive late |
| M3 agent PRs | Run on each agent PR — parallel worktrees have cross-cutting blind spots |
| M4–M5 | Run on PRs with non-trivial logic; skip glue/config |
| M6 | `/security-review` before deploy |

### Parallel agent count
When `/code-review` runs, use **4 angles only** (drop the cleanup angles to save usage):
- **A** — line-by-line diff scan
- **B** — removed-behavior auditor
- **C** — cross-file tracer
- **Conventions** — CLAUDE.md rule violations

Skip: Reuse, Simplification, Efficiency, Altitude. Add them back only for M2 (`/code-review ultra`)
where correctness and design quality both matter.

Other skills: `/verify` + `/run` at milestone gates (M2/M4/M5); `/security-review` before deploy (M6).
