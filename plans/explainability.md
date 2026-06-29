# Explainability — "Show the Why"

> **Goal:** Make every prediction legible. For each prediction, surface *which features drove it
> and by how much*, in plain language, with a visual breakdown — the project's core
> differentiator. Cross-cutting across all model heads.
> Parent: [master-plan.md](master-plan.md). Consumes models from [modeling.md](modeling.md) +
> [rapm.md](rapm.md). Serves [backend-api.md](backend-api.md) → [frontend.md](frontend.md).

---

## 1. What SHAP is (intuition)

SHAP answers: *"for this one prediction, how much did each input push the result up or down?"*

It borrows **Shapley values** from cooperative game theory. Imagine the features are players on a
team and the "payout" is how far this prediction sits from the model's average prediction. Shapley
values are the *fair* way to split that payout among the features — accounting for every order in
which features could combine. The result: each feature gets a **signed contribution**, and they
**sum exactly to `prediction − baseline`** (baseline = the model's average output). That additive
property is what makes it honest and what powers a clean waterfall visual:

```
baseline 50% ─► +8% rest advantage ─► +6% matchup edge ─► −4% road ─► ... = 64% home win
```

**Per model head:**
- **Game prediction & props (LightGBM):** **TreeSHAP** — exact and *fast* for tree models. Default.
- **Live win prob:** the LightGBM variant uses TreeSHAP; the **NN** variant uses a gradient-based
  explainer (GradientSHAP/DeepSHAP) since TreeSHAP doesn't apply. Whichever model is champion
  determines the explainer.
- **RAPM (ridge, linear):** *self-explaining* — the player coefficients *are* the contributions.
  Where RAPM-derived features feed game/props models, SHAP attributes to those features normally.

## 2. The honesty caveats (state these in the UI)

- SHAP explains **the model's reasoning, not ground truth or causation.** A contribution means
  "this feature moved *the model's* output," not "this caused the win." We label it as such.
- We only show explanations for **calibrated** probabilities (see [modeling.md §6](modeling.md)),
  so the numbers being explained are trustworthy.
- This restraint *is* the differentiator: a glass box that's honest about being a model beats a
  black box that says "trust me."

## 3. A subtlety: units for classification explanations

TreeSHAP contributions for a classifier come out in **log-odds (margin) space**, not probability —
they don't naively add as "percentage points." We handle this explicitly (§9 decision): either
present a **probability-point approximation** (friendly: "+6%") computed by mapping the
baseline→feature cumulative log-odds through the logistic function, and/or expose the precise
log-odds for the technically inclined. Regression heads (margin, total, props) are already in
natural units (points, rebounds) — no conversion needed.

## 4. Local vs global explanations

- **Local (per prediction):** the main UX — this game / this player projection. Computed and
  **cached alongside the prediction** so the explanation always matches the exact feature values
  that produced it (point-in-time consistent).
- **Global (whole model):** aggregate feature importance + dependence plots, generated at training
  time and logged to **MLflow** as artifacts. Powers a "How this model works" page in the stats
  hub.

## 5. The explanation contract (API → frontend)

A single typed schema every head returns, so the frontend renders one component for all of them:

```
Explanation {
  baseline: float            # model average output (display units)
  prediction: float          # final output (display units)
  contributions: [ {
      feature: str           # raw feature name
      display_label: str     # human label, e.g. "Rest advantage"
      raw_value: any         # the feature's value for this case
      formatted_value: str   # e.g. "+2 days"
      contribution: float    # signed, display units
      direction: "up"|"down"
  } ]
  units: "probability_points" | "points" | "rebounds" | ...
  notes: str                 # honesty caveat text
}
```

Contributions are returned sorted by magnitude; the frontend shows the top-N headline drivers with
the full list expandable (§9 decision).

## 6. Feature humanizer

A registry maps each raw feature → `{display_label, description, value_formatter, unit}` so
explanations read like English ("**+6%** from a **2-day rest advantage**") instead of
`days_rest_diff=2`. Every feature in [feature-engineering.md](feature-engineering.md) must have an
entry; a test fails if any feature lacks one.

## 7. Performance

TreeSHAP is fast, but explaining *every* prediction still adds cost. Mitigations: compute the
explanation once when the prediction is made and **cache it with the prediction**; for live win
prob (frequent ticks), explain only the **headline drivers each update** and compute the full
breakdown **on demand** (§9 decision).

---

## 8. Build prompts (executable)

> **Prompt 1 — Explanation schema.** In `backend/src/nbaforecast/explain/schema.py`, define the
> §5 `Explanation` and `Contribution` Pydantic models with the `units` enum.

> **Prompt 2 — Per-head explainers.** In `explain/explainers.py`, implement a unified
> `explain(model, features) -> Explanation` dispatching to TreeSHAP for LightGBM heads, a
> gradient-based explainer for the NN live model, and a coefficient-based explanation for RAPM.
> For classifiers, apply the §3 log-odds→probability-point mapping when `units=probability_points`.

> **Prompt 3 — Feature humanizer.** In `explain/humanizer.py`, build the feature registry
> (`display_label`, `value_formatter`, `unit`, `description`) covering every feature, and a
> function that decorates raw contributions into human-readable form. Add a test asserting full
> coverage of the feature set.

> **Prompt 4 — Global explanations at train time.** In `training/`, after each model trains,
> generate global SHAP summary (importance) + key dependence plots and log them to MLflow as
> artifacts tied to the run/`feature_version`.

> **Prompt 5 — Serving integration.** Wire `explain()` into prediction serving so each
> `/predict*` response can include its `Explanation`; cache it with the prediction. For live,
> return headline drivers by default with a full-breakdown endpoint.

> **Prompt 6 — Correctness test.** In `backend/tests/ml/test_explanations.py`, assert the SHAP
> additivity property: `sum(contributions) ≈ prediction − baseline` within tolerance for each
> head. (This is a real, checkable property — a strong correctness signal.)

## 9. Decisions (resolved 2026-06-28)
- **UI depth: top ~5 drivers as a waterfall by default, full breakdown expandable.** §5 returns
  contributions sorted by magnitude to support this.
- **Classification units: probability-points by default, with a toggle to exact log-odds.** The §3
  log-odds→probability mapping is the default display; raw log-odds available behind the toggle.
- **Live cadence: headline drivers each tick, full breakdown on demand** (§7) — keeps the live
  dashboard fast.

## 10. Definition of done
- Every head returns a uniform `Explanation`; additivity test passes for all heads.
- Every feature has a humanizer entry (coverage test green).
- Local explanations cached with predictions; global SHAP artifacts in MLflow.
- Honesty caveat surfaced wherever explanations are shown.
