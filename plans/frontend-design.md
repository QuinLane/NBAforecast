# Frontend Design — Visual Language & Design System

> **Status:** In progress (started 2026-07-01). The running record of NBAforecast's visual design,
> maintained alongside live mockups. This is the *design* companion to [frontend.md](frontend.md)
> (which owns stack, routes, components, data layer). Decisions here get codified into
> `frontend/src/app/globals.css` design tokens + shadcn components once validated in mockups.
>
> **Process:** iterate on live HTML mockups → capture what's approved here → codify into the real
> app. Nothing is "designed" until it's in this doc.

---

## 1. Vision

A **modern product-dashboard × broadcast** blend, organized around **bold stat lines and
predictions** — the energy of a stats/props app (PrizePicks / Underdog / Sleeper family: big
numbers, punchy accents, stat-line cards) crossed with the clean restraint of a Linear/Vercel
dashboard. NBAforecast's twist on that family is **predictions + explainability** rather than
picks.

Principles:
- **Big numbers, high energy, bold accents** — the predictions and stat lines are the heroes.
- **Generous whitespace, restrained chrome** — energy comes from accents and typography, not clutter.
- **Density where it earns it** — leaderboards, game logs, and stat tables get compact, scannable,
  data-dense treatments; hero/prediction surfaces breathe.
- **Glass-box, quietly** — explainability is *subtle / on-demand* (§3), not the visual identity.

## 2. Palette (locked)

| Role | Hex | Use |
|------|-----|-----|
| Background | `#06030b` | App base — deep purple-black |
| Text | `#e3dcf5` | Primary text (lavender-white) |
| Primary | `#a58dde` | Links, secondary emphasis, primary buttons |
| Secondary | `#832786` | Deeper fills, gradients, muted accent |
| Accent | `#cb4bac` | Hot magenta — the punch: key numbers, CTAs, highlights |
| Positive | `#5fd39a` (mint) | "up / good": positive RAPM, up-drivers, over, wins |
| Negative | `#ff5d73` (rose-red) | "down / bad": negative values, down-drivers, under, losses |

**Locked (2026-07-01):**
- **Accent discipline** — magenta is *punch-only* (hero numbers, RAPM values, CTAs/pills). Primary
  lavender does the quiet work (nav, links). Kept as shown in v1.
- **Semantic pair** — mint `#5fd39a` = positive/up, rose-red `#ff5d73` = negative/down. Used for
  signed values and the explainer waterfall up/down bars.
- **Energy** — soft radial glows + a glow on big numbers are in, **dialed down slightly** from v1.
- **Type** — system-ui, weight 800 for big numbers. No custom display face (kept clean).

Still to derive in mockups: chart palette (win-prob lines, dependence), exact muted/border ramps.

## 3. Explainability stance — subtle / on-demand

Stats + predictions lead. The SHAP "why" is available on every prediction surface but lives behind
an expander / secondary affordance — it is **not** the dominant visual motif. (This overrides the
"explanation-forward" framing floated in [explainability.md](explainability.md) §UI for v1 look;
the honesty caveat still appears wherever an explanation is shown.)

## 4. Typography — TBD (settle in mockups)
Candidates: a strong display weight for big numbers (tabular), a clean sans for body, mono for raw
stat figures. Font family TBD (Geist is currently wired; may keep or swap).

## 5. Components to define (design language)
- **App shell** — header/wordmark, primary nav, (search?), footer.
- **PredictionCard / StatLine** — the money component: player/matchup + big projected number +
  accent, interval, subtle "why" chip. (frontend.md `PropsCard`.)
- **Hero prediction** — featured game: big win-prob number, spread/total, matchup.
- **Dense tables** — RAPM leaderboard, stat leaderboards, game logs (compact, sortable).
- **PredictionExplainer** — waterfall, but entered subtly (expander), per §3.
- **Matchup Context drawer** — collapsible section under a player's projected props; scouting/
  context modules that deepen the projection without cluttering the card row (see §8).
- Buttons, badges/pills, tabs, pagination — the primitives.

## 6. Open design decisions
- Exact type family + display weight for big numbers.
- Accent-usage rules (how much magenta before it's too much).
- Semantic up/down colors (does magenta double as "up"? need a down/negative color).
- Chart palette (win-prob lines, dependence plots) on the dark base.
- Motion / energy level (hover glows, transitions) — how lively.
- Light mode? (default dark; light is deferred unless wanted.)
- Team-color theming — deferred (was an option; not chosen for the base system).

## 7. Iteration log
- **2026-07-01** — Vision + palette + process captured. **v1 mockup** (home/landing): nav, hero
  prediction, stat-line cards, dense leaderboard. **Approved** with tweaks → accent discipline
  kept, add mint/rose semantic pair, energy dialed down a touch, subtle "why" kept, system font
  kept. Locked in §2.
- **2026-07-01** — **v2 mockup** (game detail): the expanded PredictionExplainer waterfall (mint/
  rose up-down drivers), pre-game win prob hero + margin/total, units toggle, honesty caveat.
  **Approved.** Waterfall style = driver list + centered signed bars (not classic cumulative).
- **2026-07-01** — **v3 mockup** (props board): stat-filter tabs, grid of projection cards (big
  number + interval range bar + vs-season delta in mint/rose + subtle why). Tests density vs breathing.
  **Approved** with tweak: on the card why-line, the **arrow + reason** take the directional
  mint/rose color; only "· why ▾" stays grey.
- **2026-07-01** — **v4 mockup** (player page): profile header + RAPM value & history sparkline,
  compact projected-props row (with the v3 why-line tweak), dense recent-games log table (+/- in
  mint/rose). Completes the core screen set. **Approved.**
- **2026-07-01** — Matchup Context drawer specced (§8) with all data-feasible-now modules. Core
  design phase closed; moving to codifying the language into the real app (§9).

---

## 8. Matchup Context drawer (planned)

A collapsed-by-default disclosure under a player's **Projected props** (player page), opening a
"scouting report" that contextualizes tonight's projection. On-demand (honors §3). **v1 modules =
everything computable from existing data today** (`player_game_stats`, `games`, `shots`,
`possessions`, RAPM snapshots):

- **H2H — last 5 vs tonight's opponent** — the actual stat lines (date, result, MIN/PTS/REB/AST/3PM/
  ±) + a "usual script" average row. `player_game_stats` filtered by `opponent_team_id`.
- **Vs-opponent split** — per-stat average vs this opponent vs overall ("vs BOS 27.4 PTS · avg 25.1").
- **Home / away split** — PTS/REB/AST home vs road, tonight's venue highlighted.
- **Rest impact** — line on 0 days rest (B2B) vs rested (`days_rest`/`is_back_to_back`).
- **Role trend** — minutes/usage rising or falling (`minutes_trend`, `roll_minutes`, `usage_rate`).
- **Shot diet + zone FG%** — mini donut: share of attempts at rim / mid / 3 and FG% by zone
  (`shots` loc/zone/made). A teaser for the M5 D3 shot chart.

**Later additions (need more work / data):** clutch line (last 5 min, ≤5 pt games — PBP filtering);
on/off net rating (`possessions`); **projection track record** — "our PTS projection landed inside
its interval 82% of the time for this player" (needs logged `predictions`; the signature glass-box
trust stat, headline it once available).

**New backend endpoints required** (not built yet — this drawer is a follow-up feature, not part of
the base retheme): a player-context/scouting endpoint (H2H lines + splits + rest/role) and a
player shot-zone summary endpoint. Add under `backend-api.md` players routes.

## 9. Implementation plan (design → code)

Turning the approved mockups into the shipping UI, in dependency order:

1. **Foundation** — lock palette + semantic tokens (mint/rose), surfaces, hairlines, glow, type
   scale into `frontend/src/app/globals.css`; add a global **app shell** (header/nav) in the root
   layout; retheme the home page to the section-nav language. *(No backend dependency.)*
2. **Primitives** — install/settle the shadcn components we hand-rolled (card, table, tabs, badge,
   button) themed to the tokens; extract shared `StatLineCard`, `DenseTable`, `BigStat`.
3. **Retheme pages** — games, game detail (+ restyle `PredictionExplainer` to the v2 waterfall),
   rapm, players, player detail, teams → the neon-dark language. Build the real **props board** page.
4. **Matchup Context drawer** — its two new backend endpoints (§8) + the drawer UI.
5. **Charts** — win-prob line + dependence + the M5 shot chart, themed to the palette.

Each step is its own branch → PR → gates green (lint/type-check/build), same cadence as M3.
