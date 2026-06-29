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
Invoke the right skill at the right time (full table in `plans/implementation-plan.md` §5):
`/code-review` before every PR (`/code-review ultra` on the M2 spine); `/verify` + `/run` at
milestone gates (M2/M4/M5); `/review` on each agent PR at M3; `/security-review` before deploy (M6).
