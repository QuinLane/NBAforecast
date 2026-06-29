# Frontend

> **Goal:** A Next.js + TypeScript web app that is both the clean **stats hub** and the home of the
> **explainable predictions** and **live win-prob dashboard** — SSR/SSG where SEO matters,
> client-side where it's interactive.
> Parent: [master-plan.md](master-plan.md). Consumes: [backend-api.md](backend-api.md),
> [live-system.md](live-system.md), [explainability.md](explainability.md).

---

## 1. Stack

- **Next.js (App Router) + TypeScript** — SSR/SSG for discoverability (see SSR rationale in
  [architecture.md §1](architecture.md)).
- **Tailwind CSS** + a component library (§7 decision) for a consistent, fast-to-build UI.
- **TanStack Query** — server-state fetching/caching/revalidation.
- **D3.js** — bespoke spatial viz (shot charts / court heatmaps).
- **Charts library** (§7 decision) — standard charts (win-prob lines, trends).
- **SSE client** — live dashboard updates (transport matches [backend-api.md §7](backend-api.md)).

## 2. Rendering strategy (per page type)

- **SSG / ISR** for stable, SEO-valuable pages: team & player profiles, RAPM leaderboard,
  historical game pages, "how it works."
- **SSR** for pages needing fresh-on-load data with SEO: today's games / home.
- **Client-side** for the interactive/live surfaces: live dashboard, sortable tables, the
  explanation toggles.

## 3. Route map

| Route | Render | Content |
|-------|--------|---------|
| `/` | SSR | Today's games + headline predictions, featured content |
| `/games` | SSR | Schedule + results |
| `/games/[id]` | SSR/ISR | Game detail; pre-game `{win_prob, margin, total}` + explanation; live tab if in progress |
| `/live` | Client | Live dashboard — all in-progress games, SSE-driven |
| `/players` · `/players/[id]` | SSG/ISR | Profile, stats, game logs, **shot chart**, props, RAPM history |
| `/teams` · `/teams/[id]` | SSG/ISR | Team profile + ratings |
| `/rapm` | SSG/ISR | ORAPM/DRAPM/RAPM leaderboard (sortable) |
| `/props` | SSR | Today's props board (PTS/REB/AST/3PM) |
| `/how-it-works` | SSG | Global SHAP importance + model cards (from MLflow artifacts) |
| `/stats` | SSG/ISR | Generic stat leaderboards |

## 4. Key components

- **PredictionExplainer** — the differentiator UI: a **waterfall** of the top-5 drivers
  (baseline → contributions → final), "see all" expand, and the **probability-points ↔ log-odds
  toggle** ([explainability.md §9](explainability.md)). Reused for games and props.
- **ShotChart** — D3 court with shot locations/zones/heatmap; respects `location_reliable`.
- **LiveWinProb** — SSE-driven live number + headline drivers; **WinProbTimeline** replays the
  persisted series post-game.
- **PropsCard** — point estimate + prediction interval band + explanation.
- **RapmTable** / **StatLeaderboard** — sortable, paginated tables.
- **ModelCard** — per-head metrics + global SHAP summary for "how it works."

## 5. Data layer

- A **typed API client** (§7 decision) over [backend-api.md](backend-api.md), wrapped in TanStack
  Query hooks (`useGamePrediction`, `usePlayerProps`, `useRapmLeaderboard`, …).
- A `useLiveWinProb(gameId)` hook managing the SSE connection (subscribe, reconnect, cleanup).
- Types shared from the API schema so the `Explanation`/`Prediction` shapes can't drift.

## 6. Cross-cutting

- **SEO:** per-page metadata, Open Graph cards, `sitemap.xml`, semantic HTML.
- **Accessibility:** keyboard nav, ARIA on charts (text alternative summaries), color-contrast.
- **Responsive + dark mode** (default dark, data-dashboard aesthetic — refine at build time).
- **Honesty UI:** the explanation caveat ([explainability.md §2](explainability.md)) shown wherever
  predictions appear.
- **Performance:** ISR caching, lazy-load heavy charts, skeleton states.

---

## 7. Decisions (resolved 2026-06-28)
- **UI library: shadcn/ui + Tailwind** — own-the-code components on Tailwind + Radix; bespoke
  data-dashboard look, no lock-in.
- **API client: generate from OpenAPI** — a codegen step (orval / openapi-typescript) auto-produces
  the typed client + TanStack Query hooks from FastAPI's spec, so the backend is the single source
  of truth and breaking changes fail at compile time. Re-run on API change in CI.
- **Charts: Recharts** for standard charts (win-prob lines, trends); **D3** retained for the
  bespoke court/shot viz.

## 8. Build prompts (executable)

> **Prompt 1 — App scaffold.** Flesh out the Next.js App-Router + TS + Tailwind project from
> [architecture.md §6](architecture.md): layout, nav, theme (dark default), TanStack Query
> provider, and the §3 route skeletons with loading/skeleton states.

> **Prompt 2 — Typed API client + hooks.** Generate (or hand-write per §7) a typed client from the
> backend OpenAPI spec; wrap endpoints in TanStack Query hooks; share `Explanation`/`Prediction`
> types.

> **Prompt 3 — PredictionExplainer.** Build the waterfall component: top-5 drivers, expandable
> full list, units toggle (probability-points default / log-odds), and the honesty caveat. Reused
> for games + props.

> **Prompt 4 — ShotChart.** Build the D3 court + shot rendering (locations, zones, heatmap),
> respecting `location_reliable`.

> **Prompt 5 — Live dashboard.** Build `/live`, the `useLiveWinProb` SSE hook, the LiveWinProb
> component, and the WinProbTimeline replay (from the persisted series).

> **Prompt 6 — Pages.** Implement game detail, player, team, RAPM leaderboard, props board, and
> how-it-works, wiring the §4 components to the §5 hooks.

> **Prompt 7 — SEO + a11y.** Per-page metadata, OG cards, sitemap; chart text alternatives and
> keyboard nav.

> **Prompt 8 — Tests.** Vitest + React Testing Library for components (esp. PredictionExplainer
> math/labels); optional Playwright E2E for a core flow. Wire into CI.

## 9. Definition of done
- All §3 routes render with correct SSR/SSG/client strategy.
- PredictionExplainer shows correct, label-mapped, unit-toggleable breakdowns for games + props.
- Live dashboard updates over SSE; post-game timeline replays.
- Shot charts, RAPM leaderboard, props board functional; SEO metadata + a11y in place.
- Component tests green in CI.
