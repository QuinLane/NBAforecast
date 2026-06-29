# Engineering Standards & Conventions

> **Goal:** One place defining *how the code is written* — structure, naming, git, reviews — so
> every file and commit looks like it came from the same disciplined hand. Read this before
> writing or reviewing code.
> Parent: [master-plan.md](master-plan.md). Complements [architecture.md](architecture.md) (what)
> and [data-model.md](data-model.md) (schema naming).

---

## 1. Tooling

| Area | Tool | Notes |
|------|------|-------|
| Python | **3.12** | one pinned version |
| Python deps/env | **uv** (§decision) | fast, modern; lockfile committed |
| Lint + format (Py) | **ruff** | replaces black/isort/flake8; one config |
| Types (Py) | **mypy --strict** | required on all non-test code |
| Node | **20+** | |
| JS deps | **pnpm** (§decision) | lockfile committed |
| Lint/format (TS) | **ESLint + Prettier** | |
| Types (TS) | **tsc**, `strict: true` | no `any` (eslint-enforced) |
| Pre-commit | **pre-commit** hooks | ruff, mypy, prettier, eslint run before commit |

CI re-runs every gate (a hook can be skipped locally; CI cannot).

## 2. Python conventions

- **Style:** PEP 8 via ruff; **line length 100**.
- **Naming:**
  - modules/files & packages → `snake_case`
  - functions/variables → `snake_case`
  - classes / Pydantic models / type aliases → `PascalCase`
  - constants → `UPPER_SNAKE`
  - "private" → `_leading_underscore`
- **Type hints:** mandatory on every public function signature; `mypy --strict` clean.
- **Docstrings:** **Google style** on public modules/classes/functions; skip the obvious one-liners.
- **Imports:** absolute within the package (`from nbaforecast.features import ...`); ruff-ordered.
- **Data shapes:** **Pydantic** for external/boundary data (API, config, validated rows);
  `@dataclass(slots=True)` for internal value objects.
- **Errors:** a custom hierarchy rooted at `NbaForecastError` (e.g., `IngestionError`,
  `ValidationError`); **never** bare `except`; pipelines **fail loud** (no silent swallow).
- **Logging:** stdlib `logging` with a structured (JSON) formatter; one `logger = getLogger(__name__)`
  per module; **never `print`** in library code.
- **Config:** everything via `pydantic-settings`; **no hardcoded secrets, paths, or magic numbers**
  (promote to named constants/settings).
- **Functions:** small and single-purpose; let ruff flag complexity.

## 3. Code-structure rules (layering)

The package boundaries from [architecture.md §3](architecture.md) are enforced by these
dependency rules:
- **Routers are thin** → delegate to `services/` → which use `storage/` + `ModelProvider`. Routers
  never touch raw SQL or train.
- **Features live in one library** (`features/`); every model head reads materialized features —
  no head computes its own.
- **Models implement the `ModelHead` interface** (`train/predict/explain/feature deps/registry`),
  so heads are drop-in ([roadmap.md §1](roadmap.md)).
- **Dependency direction is one-way:** `api → services → {storage, models(provider)}`;
  `ingestion/features/training` never import `api`. No import cycles.
- One responsibility per module; each subpackage `__init__.py` has a one-line docstring stating it.

## 4. TypeScript / React conventions

- **File naming:** components `PascalCase.tsx` (`PredictionExplainer.tsx`); hooks `useThing.ts`;
  utilities/`lib` `camelCase.ts`.
- **Naming:** components & types/interfaces → `PascalCase`; variables/functions → `camelCase`;
  constants → `UPPER_SNAKE`.
- **Components:** function components + hooks; typed props interface (`PredictionExplainerProps`);
  no class components.
- **Data:** server state only through **TanStack Query hooks** over the **generated** API client;
  components never `fetch` directly; the generated client is **never hand-edited**.
- **Styling:** Tailwind utilities + shadcn/ui components; avoid inline styles and bespoke CSS.
- **Strictness:** `strict: true`; no `any`; exhaustive switch on unions.

## 5. Cross-stack naming

- **Database:** `snake_case`, plural tables, singular columns ([data-model.md](data-model.md)).
- **API routes:** lowercase, plural resources, under `/api/v1` (`/api/v1/games/{game_id}/prediction`).
- **JSON field casing:** **snake_case** (§decision) — matches Pydantic + the generated TS client,
  so no aliasing layer.
- **Env vars:** `UPPER_SNAKE`, prefixed `NBAF_` (`NBAF_POSTGRES_URL`).
- **MLflow:** experiment/model names = the head name (`game_win`, `props_pts`, `live_win`).
- **Features:** `snake_case`; rolling windows `roll{N}_{metric}` (e.g., `roll10_net_rating`).

## 6. Git & version control

- **Branching:** **trunk-based** (§decision) — `main` always deployable; short-lived feature
  branches merged via PR. No long-running `develop`.
- **Branch names:** `<type>/<short-desc>` → `feat/ingestion-clients`, `fix/shot-parser`,
  `chore/ci-cache`.
- **Commits:** **Conventional Commits** (§decision) — `<type>(<scope>): <subject>`.
  - types: `feat, fix, docs, refactor, test, chore, perf, ci, build`
  - imperative mood, ≤72-char subject; body explains **why**, not what; footer for
    `BREAKING CHANGE:` / issue refs.
  - one logical change per commit; keep them small.
  - **No AI/Claude attribution.** Commits carry **no** `Co-Authored-By` trailer; authored solely
    as Quin.
- **Merging:** **squash-merge** (§decision) PRs into `main` for a clean linear history.
- **PRs required** to merge; CI must be green; author self-reviews against the §7 checklist.
- **Releases:** tag `v0.MINOR.PATCH` (v0.x during pre-1.0).
- **Never** commit secrets; `.gitignore` covers `.env`, `data/`, build artifacts.

## 7. PR / review checklist (Definition of Done per task)

- [ ] Scope matches one task / build prompt; small and focused.
- [ ] `ruff`, `mypy`, tests, frontend lint/types all green locally + CI.
- [ ] New/changed behavior covered by tests (incl. ML-correctness where relevant — no-leakage,
      additivity, baseline-floor).
- [ ] No secrets/hardcoded config; new config documented in `.env.example`.
- [ ] Public functions typed + docstringed; names follow §2/§4.
- [ ] Relevant plan doc updated if the design shifted.

## 8. Dependencies & docs

- Pin versions; commit lockfiles; justify each new dependency (tool-liability principle,
  [architecture.md §7](architecture.md)).
- README at repo root + per top-level package; keep `claudeInfo.md` + plans current as the design
  record.

## 9. Decisions (resolved 2026-06-28)
- **Python tooling: uv** (env + deps + lockfile). **JS: pnpm.**
- **Git: trunk-based + squash-merge.** One ticket/task per short-lived branch off `main`; commit
  freely on the branch (it squashes at merge into one clean commit); PR → approve → squash-merge →
  delete branch. Branch naming `<type>/<task-id>-<desc>` (e.g., `feat/T1.2-ingestion-clients`),
  where `task-id` is the [implementation-plan.md](implementation-plan.md) task or a GitHub issue #.
- **Commits: Conventional Commits** on the persisted (squash) commit — `<type>(<scope>): <subject>`,
  body explains *why*, `BREAKING CHANGE:` footer when relevant. **No `Co-Authored-By: Claude`
  trailer and no "Generated with Claude Code" PR footer — commits and PRs are authored solely as
  Quin** (`git config user.name`/`user.email` set to his identity).
- **API JSON casing: snake_case** (matches Pydantic + the generated TS client; no aliasing layer).
