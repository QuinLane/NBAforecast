"use client";

import { useState } from "react";
import type { components } from "@/lib/api-client";

type Explanation = components["schemas"]["Explanation"];
type Contribution = components["schemas"]["Contribution"];

interface Props {
  explanation: Explanation;
  onRequestFull?: () => void;
  fullLoading?: boolean;
}

function formatUnits(value: number, units: Explanation["units"]): string {
  if (units === "probability_points") return `${(value * 100).toFixed(1)}%`;
  if (units === "log_odds") return `${value.toFixed(3)} log-odds`;
  return value.toFixed(2);
}

function formatContribution(value: number, units: Explanation["units"]): string {
  const sign = value >= 0 ? "+" : "";
  if (units === "probability_points") return `${sign}${(value * 100).toFixed(1)}%`;
  if (units === "log_odds") return `${sign}${value.toFixed(3)}`;
  return `${sign}${value.toFixed(2)}`;
}

function ContributionRow({
  contribution,
  maxAbs,
  units,
}: {
  contribution: Contribution;
  maxAbs: number;
  units: Explanation["units"];
}) {
  const widthPct = maxAbs > 0 ? (Math.abs(contribution.contribution) / maxAbs) * 100 : 0;
  const isUp = contribution.direction === "up";

  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="w-36 shrink-0 text-right text-sm text-zinc-400 truncate">
        {contribution.display_label}
      </div>
      <div className="flex-1 flex items-center gap-1 min-w-0">
        {/* negative side */}
        <div className="flex-1 flex justify-end">
          {!isUp && (
            <div
              className="h-5 rounded-sm bg-red-500/80"
              style={{ width: `${widthPct}%` }}
              aria-hidden="true"
            />
          )}
        </div>
        {/* center line */}
        <div className="w-px h-5 bg-zinc-600 shrink-0" />
        {/* positive side */}
        <div className="flex-1">
          {isUp && (
            <div
              className="h-5 rounded-sm bg-emerald-500/80"
              style={{ width: `${widthPct}%` }}
              aria-hidden="true"
            />
          )}
        </div>
      </div>
      <div
        className={`w-16 shrink-0 text-sm font-mono ${isUp ? "text-emerald-400" : "text-red-400"}`}
      >
        {formatContribution(contribution.contribution, units)}
      </div>
      <div className="w-20 shrink-0 text-xs text-zinc-500 truncate">
        {contribution.formatted_value}
      </div>
    </div>
  );
}

export function PredictionExplainer({
  explanation,
  onRequestFull,
  fullLoading,
}: Props) {
  const [showLogOdds, setShowLogOdds] = useState(false);

  const contributions = explanation.contributions;
  const displayUnits: Explanation["units"] = showLogOdds
    ? "log_odds"
    : "probability_points";
  const maxAbs = Math.max(...contributions.map((c) => Math.abs(c.contribution)));

  function handleSeeAll() {
    onRequestFull?.();
  }

  const isTopFive = contributions.length <= 5;

  return (
    <section
      aria-label="Prediction explanation"
      className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-4"
    >
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-200">
          Win probability drivers
        </h3>
        <button
          onClick={() => setShowLogOdds((v) => !v)}
          className="text-xs text-zinc-500 hover:text-zinc-300 underline underline-offset-2 transition-colors"
          aria-pressed={showLogOdds}
        >
          {showLogOdds ? "Show probability %" : "Show log-odds"}
        </button>
      </div>

      {/* Baseline */}
      <div className="flex justify-between text-sm border-b border-zinc-800 pb-3">
        <span className="text-zinc-500">Model average (baseline)</span>
        <span className="font-mono text-zinc-400">
          {formatUnits(explanation.baseline, displayUnits)}
        </span>
      </div>

      {/* Contributions */}
      <div
        role="list"
        aria-label="Feature contributions"
        className="space-y-0.5"
      >
        {contributions.map((c) => (
          <div key={c.feature} role="listitem">
            <ContributionRow
              contribution={c}
              maxAbs={maxAbs}
              units={displayUnits}
            />
          </div>
        ))}
      </div>

      {/* See all / see less */}
      {isTopFive && onRequestFull && (
        <button
          onClick={handleSeeAll}
          disabled={fullLoading}
          className="text-xs text-zinc-500 hover:text-zinc-300 underline underline-offset-2 transition-colors disabled:opacity-50"
        >
          {fullLoading ? "Loading…" : "See all drivers"}
        </button>
      )}
      {!isTopFive && (
        <p className="text-xs text-zinc-600">
          Showing all {contributions.length} drivers.
        </p>
      )}

      {/* Final prediction */}
      <div className="flex justify-between text-sm border-t border-zinc-800 pt-3">
        <span className="text-zinc-400 font-medium">Home win probability</span>
        <span className="font-mono font-semibold text-zinc-100">
          {formatUnits(explanation.prediction, displayUnits)}
        </span>
      </div>

      {/* Honesty caveat */}
      <p className="text-xs text-zinc-600 leading-relaxed">
        {explanation.notes}{" "}
        <span className="italic">
          SHAP explains the model&apos;s reasoning, not causation.
        </span>
      </p>
    </section>
  );
}
