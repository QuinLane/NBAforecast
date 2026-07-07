"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePlayerRapm, usePlayerStats } from "@/lib/hooks";

type GameStatKey = "pts" | "reb" | "ast" | "fg3m" | "min";
type TabKey = GameStatKey | "rapm";

const TABS: { key: TabKey; label: string }[] = [
  { key: "pts", label: "PTS" },
  { key: "reb", label: "REB" },
  { key: "ast", label: "AST" },
  { key: "fg3m", label: "3PM" },
  { key: "min", label: "MIN" },
  { key: "rapm", label: "RAPM" },
];

const AVG_WINDOW = 10;

// A month/day label for per-game points; a "Mon 'YY" label for monthly RAPM snapshots.
function gameLabel(isoDate: string): string {
  const [, m, d] = isoDate.split("-");
  return `${Number(m)}/${Number(d)}`;
}
function monthLabel(isoDate: string): string {
  const [y, m] = isoDate.split("-");
  const month = new Date(Number(y), Number(m) - 1, 1).toLocaleString("en-US", {
    month: "short",
  });
  return `${month} '${y.slice(2)}`;
}

type ChartRow = { label: string; value: number | null; avg?: number | null };

function ChartTooltip({
  active,
  payload,
  label,
  statLabel,
}: {
  active?: boolean;
  payload?: { dataKey?: string | number; value?: number | null }[];
  label?: string | number;
  statLabel: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const raw = payload.find((p) => p.dataKey === "value")?.value;
  const avg = payload.find((p) => p.dataKey === "avg")?.value;
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs shadow-lg">
      <div className="text-zinc-500">{label}</div>
      {raw != null && (
        <div className="font-mono text-zinc-200">
          {statLabel}: {Number(raw).toFixed(statLabel === "MIN" ? 0 : 0)}
        </div>
      )}
      {avg != null && (
        <div className="font-mono text-emerald-400">
          {AVG_WINDOW}-game avg: {Number(avg).toFixed(1)}
        </div>
      )}
    </div>
  );
}

export function PlayerTrajectory({ playerId }: { playerId: number }) {
  const [tab, setTab] = useState<TabKey>("pts");
  const statsQ = usePlayerStats(playerId);
  const rapmQ = usePlayerRapm(playerId);

  const { rows, showAvg } = useMemo<{ rows: ChartRow[]; showAvg: boolean }>(() => {
    if (tab === "rapm") {
      const history = rapmQ.data ?? [];
      return {
        rows: history.map((h) => ({
          label: monthLabel(h.as_of_date),
          value: h.rapm ?? null,
        })),
        showAvg: false,
      };
    }
    const games = statsQ.data?.games ?? [];
    const values = games.map((g) => {
      const v = g[tab];
      return v == null ? null : Number(v);
    });
    // Trailing simple moving average over the last AVG_WINDOW games (ignoring nulls).
    const avg = values.map((_, i) => {
      const window = values.slice(Math.max(0, i - AVG_WINDOW + 1), i + 1).filter(
        (v): v is number => v != null,
      );
      return window.length === 0
        ? null
        : window.reduce((a, b) => a + b, 0) / window.length;
    });
    return {
      rows: games.map((g, i) => ({
        label: gameLabel(g.game_date),
        value: values[i],
        avg: avg[i],
      })),
      showAvg: true,
    };
  }, [tab, statsQ.data, rapmQ.data]);

  const statLabel = TABS.find((t) => t.key === tab)!.label;
  const isPending = tab === "rapm" ? rapmQ.isPending : statsQ.isPending;
  const tickGap = Math.max(0, Math.floor(rows.length / 8));

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-300">Stat trajectory</h2>
        <div className="flex gap-1" role="tablist" aria-label="Trajectory stat">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                tab === key
                  ? "bg-zinc-200 text-zinc-900"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {isPending ? (
        <div className="h-56 rounded-lg bg-zinc-800/40 animate-pulse" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-zinc-500 h-56 flex items-center justify-center">
          {tab === "rapm"
            ? "No RAPM snapshots for this player yet."
            : "No games in the loaded seasons."}
        </p>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
              <CartesianGrid stroke="#27272a" vertical={false} />
              <XAxis
                dataKey="label"
                interval={tickGap}
                tick={{ fill: "#71717a", fontSize: 11 }}
                stroke="#3f3f46"
              />
              <YAxis
                tick={{ fill: "#71717a", fontSize: 11 }}
                stroke="#3f3f46"
                width={40}
                allowDecimals={false}
              />
              <Tooltip
                content={<ChartTooltip statLabel={statLabel} />}
                cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={showAvg ? "#3f3f46" : "#34d399"}
                strokeWidth={showAvg ? 1 : 2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
              {showAvg && (
                <Line
                  type="monotone"
                  dataKey="avg"
                  stroke="#34d399"
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="text-xs text-zinc-600">
        {tab === "rapm"
          ? "RAPM per monthly snapshot (3-season trailing window). Early-season points are heavily regularized toward zero on small samples."
          : `Faint line: per game. Bright line: ${AVG_WINDOW}-game rolling average.`}
      </p>
    </section>
  );
}
