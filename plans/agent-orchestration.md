# Agent Orchestration — Parallel Build Strategy

> **Goal:** Use parallel AI subagents to build the project's *breadth* faster — but only after the
> shared foundation and interfaces are proven, so agents never fight over the contracts everything
> depends on.
> Parent: [master-plan.md](master-plan.md). Extends [implementation-plan.md](implementation-plan.md).

---

## 1. The core rule: foundation sequential, breadth parallel

- **M0 → M1 → M2 are built sequentially** (single-threaded, by the main session). These establish
  the *shared contracts*: the `ModelHead` interface, the materialized feature tables, the API
  response schemas, the DB schema. If multiple agents built these at once they'd invent conflicting
  versions of the exact things everything else imports. **Do not parallelize the foundation.**
- **From M3 onward, breadth fans out to parallel agents.** Once the interfaces are frozen and the
  M2 vertical slice proves them, the remaining work is independent modules that *consume* stable
  contracts — ideal for parallel agents.

## 2. Why this project is well-suited to it

- Every task already has a **self-contained build prompt** (files, interfaces, definition of done)
  in its plan doc — that prompt *is* the agent's spec, so cold-start context cost is low.
- The shared **feature pipeline** + **`ModelHead` interface** + **generated API client** mean each
  module plugs into known contracts instead of negotiating them.

## 3. Parallelizable workstreams (M3, after the spine)

| Agent | Scope | Source prompts | Owns (disjoint files) |
|-------|-------|----------------|------------------------|
| `agent-rapm` | RAPM end-to-end | [rapm.md](rapm.md) Prompts 1–7 | `models/rapm/*`, RAPM tests |
| `agent-props` | Props models (PTS/REB/AST/3PM) | [modeling.md](modeling.md) Prompt 4 + [feature-engineering.md](feature-engineering.md) Prompt 3 | `models/props/*`, `features/player_game.py` |
| `agent-game-extras` | Game margin + total regressors | [modeling.md](modeling.md) Prompt 3b/c | `models/game_prediction/{margin,total}.py` |
| `agent-frontend` | Props board, RAPM leaderboard, player/team pages | [frontend.md](frontend.md) Prompt 6 | `frontend/src/app/{props,rapm,players,teams}/*` |

M4's **live system** can overlap as a fifth agent once `features/game_state.py` exists.

## 4. Mechanics

- **Isolation:** each agent runs in its **own git worktree** (`isolation: "worktree"`) on its own
  branch (`feat/<task>`), so their changes never collide on disk.
- **Disjoint ownership:** each agent owns a non-overlapping set of files (table above). Shared
  contracts (`models/base.py`, `api/schemas/`, feature table definitions) are **read-only** to
  agents — changing them is a foundation task, not a breadth task.
- **Spec = the build prompt:** an agent is launched with its plan doc's build prompt(s) +
  [engineering-standards.md](engineering-standards.md) + the relevant interface references + the
  task's definition of done.
- **Output = a tested PR:** each agent implements, runs `ruff`/`mypy`/tests green, and returns a
  branch. The main session reviews and **squash-merges** in dependency order.
- **Background vs foreground:** long, independent agents can run in the background; the main session
  keeps integrating finished ones.

## 5. Integration order & conflict avoidance

- Merge **feature-producing** work before its consumers (e.g., `features/player_game.py` before the
  props API/UI; RAPM snapshots before RAPM-as-feature wiring).
- Because ownership is disjoint and contracts are frozen, merge conflicts are rare and confined to
  shared registries (e.g., a router include list, the feature humanizer) — resolved in the main
  session, not by agents.
- After all M3 agents merge, the main session runs the full test suite + the **extensibility
  review** to confirm the heads integrated cleanly.

## 6. Benefits vs costs

**Benefits:** wall-clock speed (4+ modules at once), isolation (no on-disk collisions), and each
agent stays focused on one crisp spec.

**Costs (honest):** each agent starts cold and re-derives context (mitigated by the build prompts);
integration/review work when branches land; more compute/budget (spawning agents is the expensive
path). Worth it only for genuinely independent, well-specified tasks — which post-M2 ours are.

## 7. ⚠️ Trigger: revisit at M3

**Agents are NOT used during M0–M2.** When the M2 ⭐ gate passes (vertical slice + frozen
interfaces + extensibility review), **the main session must surface this plan and propose the M3
fan-out before starting M3 breadth.** The user asked to be reminded here. See the M3 callout in
[roadmap.md](roadmap.md) and [implementation-plan.md](implementation-plan.md).

## 8. Definition of done (parallel phase)
- M3 breadth (RAPM, props, margin/total, frontend pages) delivered via parallel agents, each a
  reviewed, tested, squash-merged PR.
- Full suite green post-integration; extensibility review confirms heads slot into the shared
  contracts without modification to the foundation.
