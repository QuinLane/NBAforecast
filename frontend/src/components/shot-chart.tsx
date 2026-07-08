"use client";

import { useMemo } from "react";
import { usePlayerShots } from "@/lib/hooks";
import type { components } from "@/lib/api-client/schema";

type Shot = components["schemas"]["ShotChartEntry"];

// NBA stats shot coordinates: the hoop is the origin, x ∈ [-250, 250] (tenths of a foot, 50 ft
// wide), y grows from the hoop toward half court. The court group is flipped (scale 1,-1) and
// shifted so we can author every element in these natural units with the hoop near the bottom.
const COURT = "#3f3f46"; // zinc-700 lines
const HALF_COURT_Y = 417.5;
const FRONTCOURT_MAX_Y = 430; // drop backcourt heaves from the plot

function pct(made: number, att: number): string {
  return att === 0 ? "—" : `${((made / att) * 100).toFixed(1)}%`;
}

export function ShotChart({ playerId, season }: { playerId: number; season?: string }) {
  const { data, isPending, isError } = usePlayerShots(playerId, season);

  const summary = useMemo(() => {
    const shots = data ?? [];
    const three = shots.filter((s) => s.shot_type === "3PT");
    return {
      made: shots.filter((s) => s.made).length,
      total: shots.length,
      threeMade: three.filter((s) => s.made).length,
      threeAtt: three.length,
      plotted: shots.filter(
        (s): s is Shot & { loc_x: number; loc_y: number } =>
          s.location_reliable &&
          s.loc_x != null &&
          s.loc_y != null &&
          s.loc_y <= FRONTCOURT_MAX_Y,
      ),
    };
  }, [data]);

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-300">Shot chart</h2>
        {data && (
          <div className="text-xs text-zinc-500 font-mono">
            {summary.made}/{summary.total} FG ({pct(summary.made, summary.total)}) · 3P{" "}
            {summary.threeMade}/{summary.threeAtt} ({pct(summary.threeMade, summary.threeAtt)})
          </div>
        )}
      </div>

      {isPending ? (
        <div className="aspect-[50/47] rounded-lg bg-zinc-800/40 animate-pulse" />
      ) : isError || !data || summary.plotted.length === 0 ? (
        <p className="text-sm text-zinc-500 h-40 flex items-center justify-center">
          No shot-location data for this player yet.
        </p>
      ) : (
        <>
          <svg
            viewBox="-250 -15 500 500"
            className="w-full max-w-md mx-auto"
            role="img"
            aria-label="Shot chart"
          >
            <g transform={`translate(0, ${HALF_COURT_Y}) scale(1, -1)`}>
              {/* Court markings */}
              <g fill="none" stroke={COURT} strokeWidth={2}>
                <rect x={-250} y={-52.5} width={500} height={470} />
                <rect x={-80} y={-52.5} width={160} height={190} />
                <circle cx={0} cy={137.5} r={60} />
                <line x1={-30} y1={-7.5} x2={30} y2={-7.5} />
                <circle cx={0} cy={0} r={7.5} />
                {/* Restricted-area arc */}
                <path d="M -40 0 A 40 40 0 0 1 40 0" />
                {/* Three-point line: corners + arc */}
                <line x1={-220} y1={-52.5} x2={-220} y2={89.5} />
                <line x1={220} y1={-52.5} x2={220} y2={89.5} />
                <path d="M -220 89.5 A 237.5 237.5 0 0 1 220 89.5" />
              </g>
              {/* Shots: filled = make, ring = miss */}
              {summary.plotted.map((s, i) =>
                s.made ? (
                  <circle
                    key={i}
                    cx={s.loc_x}
                    cy={s.loc_y}
                    r={4.2}
                    fill="#34d399"
                    fillOpacity={0.75}
                  />
                ) : (
                  <circle
                    key={i}
                    cx={s.loc_x}
                    cy={s.loc_y}
                    r={4.2}
                    fill="none"
                    stroke="#fb7185"
                    strokeWidth={1.4}
                    strokeOpacity={0.6}
                  />
                ),
              )}
            </g>
          </svg>
          <div className="flex items-center justify-center gap-4 text-xs text-zinc-500">
            <span className="flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-full bg-emerald-400/80" /> Make
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-full border border-rose-400" /> Miss
            </span>
          </div>
        </>
      )}
    </section>
  );
}
