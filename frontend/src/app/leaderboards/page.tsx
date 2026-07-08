"use client";

import { useState } from "react";
import Link from "next/link";
import { PlayerHeadshot } from "@/components/nba-images";
import { useStatsLeaderboard, type LeaderboardStat } from "@/lib/hooks";

const PAGE_SIZE = 25;

const STATS: { key: LeaderboardStat; label: string }[] = [
  { key: "pts", label: "Points" },
  { key: "reb", label: "Rebounds" },
  { key: "ast", label: "Assists" },
  { key: "stl", label: "Steals" },
  { key: "blk", label: "Blocks" },
  { key: "fg3m", label: "3-Pointers" },
];

export default function LeaderboardsPage() {
  const [stat, setStat] = useState<LeaderboardStat>("pts");
  const [page, setPage] = useState(1);
  const { data, isPending, isError } = useStatsLeaderboard({
    stat,
    page,
    page_size: PAGE_SIZE,
  });

  const label = STATS.find((s) => s.key === stat)!.label;

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Leaderboards</h1>
        <p className="text-sm text-zinc-500">
          Per-game average of a counting stat across the loaded seasons.
        </p>
      </div>

      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Leaderboard stat">
        {STATS.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            aria-selected={stat === key}
            onClick={() => {
              setStat(key);
              setPage(1);
            }}
            className={`text-sm px-3 py-1 rounded-full transition-colors ${
              stat === key
                ? "bg-zinc-200 text-zinc-900"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {isPending && (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-11 rounded-lg bg-zinc-800/50 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-zinc-400">Could not load the leaderboard. Is the backend running?</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
                <th className="py-2 pr-2 font-medium">#</th>
                <th className="py-2 pr-2 font-medium">Player</th>
                <th className="py-2 px-2 font-medium text-right">{label} / game</th>
                <th className="py-2 pl-2 font-medium text-right">GP</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((entry, i) => (
                <tr
                  key={entry.player_id}
                  className="border-b border-zinc-900 hover:bg-zinc-900/50"
                >
                  <td className="py-2 pr-2 text-zinc-600 tabular-nums">
                    {(page - 1) * PAGE_SIZE + i + 1}
                  </td>
                  <td className="py-2 pr-2">
                    <Link
                      href={`/players/${entry.player_id}`}
                      className="inline-flex items-center gap-2 hover:underline"
                    >
                      <PlayerHeadshot
                        playerId={entry.player_id}
                        name={entry.full_name ?? ""}
                        className="size-7"
                      />
                      {entry.full_name ?? `Player ${entry.player_id}`}
                    </Link>
                  </td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums font-semibold text-emerald-400">
                    {entry.value.toFixed(1)}
                  </td>
                  <td className="py-2 pl-2 text-right font-mono tabular-nums text-zinc-600">
                    {entry.games_played}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.total > PAGE_SIZE && (
            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                ← Previous
              </button>
              <span className="text-xs text-zinc-600">
                Page {page} of {Math.ceil(data.total / PAGE_SIZE)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page * PAGE_SIZE >= data.total}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </main>
  );
}
