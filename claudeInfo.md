# claudeInfo — Working Instructions for NBAforecast

> **Purpose:** This is the operating manual for how planning and build work gets done on this
> project. Claude should re-read this doc at the start of every prompt/session before acting,
> and update it whenever a new working convention is established.

---

## 1. What this doc is

A persistent context file describing *how* we work on NBAforecast — conventions, structure,
and standards. It is NOT the project plan itself (that lives in `plans/`). Think of this as the
"rules of engagement" that keep every session consistent.

**Refer to this doc after every prompt.** If a new instruction from the user changes how we
work, append it here so it survives across sessions.

---

## 2. Folder structure

```
NBAforecast/
├── claudeInfo.md          # this file — how we work
├── plans/                 # all planning docs (.md)
│   ├── master-plan.md     # index + big picture; points to all sub-plans
│   └── <topic>.md         # one focused plan per concern
└── (code, added later)
```

---

## 3. Plan-writing standards

These rules apply to every `.md` file written into `plans/`.

### 3.1 Naming
- Name each plan after **what it accomplishes**, kebab-case: `data-pipeline.md`,
  `modeling.md`, `frontend-dashboard.md`.
- No vague names (`notes.md`, `stuff.md`).

### 3.2 Master plan is an index
- `master-plan.md` describes the whole project's setup, goals, and architecture at a high
  level, then **points to the smaller sub-plans** rather than duplicating their content.
- Keep cross-references as relative links so the docs stay navigable.

### 3.3 Every plan must contain highly detailed, specific prompts
This is the core requirement. Each sub-plan is not just prose — it contains **ready-to-use,
highly detailed prompts** that Claude can execute to build that part of the project. A good
embedded prompt:
- States the exact goal and the definition of done.
- Names specific files, libraries, data sources, and interfaces.
- Specifies inputs/outputs and edge cases.
- Is self-contained enough to run cold, without re-deriving context.
- Avoids hand-waving ("set up the backend") in favor of specifics ("create
  `api/forecast.py` exposing `GET /forecast/{team_id}` returning JSON `{...}`").

### 3.4 Suggested plan section template
```
# <Plan Title>

## Goal
What this part of the project achieves and why.

## Scope / Out of scope
What's in, what's deliberately deferred.

## Design decisions
Key choices + rationale.

## Build prompts
Numbered, detailed, executable prompts (see 3.3).

## Definition of done
Concrete, checkable criteria.

## Open questions
Things to resolve with the user.
```

---

## 4. Process conventions

- **Confirm the idea before writing detailed plans.** Sub-plans depend on knowing the project
  scope. Don't fabricate specifics; ask when unsure.
- **Start lean.** Begin with ~5–6 sub-plans. Split a doc out only when it grows too big.
  Don't over-fragment early.
- **Keep the master plan in sync.** When a sub-plan is added or removed, update the index.
- **Record decisions, not just intentions.** When a design choice is made, write the rationale
  so future sessions don't re-litigate it.
- **Update this doc** whenever the user gives new guidance on *how* to work.

---

## 5. Change log
- 2026-06-28 — Initial version. Folder structure + plan standards established. Project idea
  (NBA forecasting) to be detailed with the user before sub-plans are written.
- 2026-06-28 — Planning phase complete. All 12 plans drafted in `plans/` (master + architecture,
  data-pipeline, feature-engineering, modeling, rapm, explainability, backend-api, live-system,
  frontend, infrastructure, testing, roadmap), each with embedded build prompts and resolved
  decisions logged per doc and in master-plan.md §8. Working pattern this session: draft a plan
  with recommended defaults → explain new concepts at a learning-appropriate level → surface
  genuine forks via decision prompts → record the decision in the doc's "Decisions (resolved)"
  section → update the master index. Continue this loop for any revisions or v2 plans. Next phase:
  implementation, starting at roadmap M0 (scaffolding).
