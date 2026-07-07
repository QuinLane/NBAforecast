"use client";

import { useState } from "react";
import Link from "next/link";
import { PlayerHeadshot } from "@/components/nba-images";
import { useRapmLeaderboard, type RapmSort } from "@/lib/hooks";

const PAGE_SIZE = 25;

const SORTS: { key: RapmSort; label: string }[] = [
  { key: "rapm", label: "RAPM" },
  { key: "orapm", label: "ORAPM" },
  { key: "drapm", label: "DRAPM" },
  { key: "possessions", label: "Poss." },
];

// Possessions = sample size, not quality: ridge shrinkage tames small samples but can't
// eliminate their noise, so the board filters to a minimum sample by default.
const MIN_POSS_CHOICES = [
  { value: 0, label: "All players" },
  { value: 500, label: "500+ poss." },
  { value: 1000, label: "1,000+ poss." },
  { value: 2500, label: "2,500+ poss." },
];

function fmt(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

export default function RapmPage() {
  const [sort, setSort] = useState<RapmSort>("rapm");
  const [minPoss, setMinPoss] = useState(1000);
  const [page, setPage] = useState(1);
  const { data, isPending, isError } = useRapmLeaderboard({
    sort,
    min_poss: minPoss,
    page,
    page_size: PAGE_SIZE,
  });

  return (
    <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">RAPM leaderboard</h1>
        <p className="text-sm text-zinc-500">
          Regularized Adjusted Plus-Minus — a player&apos;s point-differential
          impact per 100 possessions, split into offense (ORAPM) and defense
          (DRAPM), from the latest snapshot.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1" role="tablist" aria-label="Sort by metric">
          {SORTS.map(({ key, label }) => (
            <button
              key={key}
              role="tab"
              aria-selected={sort === key}
              onClick={() => {
                setSort(key);
                setPage(1);
              }}
              className={`text-sm px-3 py-1 rounded-full transition-colors ${
                sort === key
                  ? "bg-zinc-200 text-zinc-900"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-zinc-500">
          Min. sample
          <select
            value={minPoss}
            onChange={(e) => {
              setMinPoss(Number(e.target.value));
              setPage(1);
            }}
            className="bg-zinc-900 border border-zinc-800 rounded-md px-2 py-1 text-sm text-zinc-300"
          >
            {MIN_POSS_CHOICES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-xs text-zinc-600">
        Poss. is the sample behind a rating, not part of it — small samples stay noisy even
        after regularization, so low-possession players are hidden by default.
      </p>

      {isPending && (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-11 rounded-lg bg-zinc-800/50 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-zinc-400">
          Could not load the RAPM leaderboard. Is the backend running with RAPM
          snapshots computed?
        </p>
      )}

      {data && data.items.length === 0 && (
        <p className="text-zinc-500 text-sm">
          No RAPM snapshots yet. Run the RAPM refresh once possessions are
          ingested.
        </p>
      )}

      {data && data.items.length > 0 && (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
                <th className="py-2 pr-2 font-medium">#</th>
                <th className="py-2 pr-2 font-medium">Player</th>
                <th className="py-2 px-2 font-medium text-right">ORAPM</th>
                <th className="py-2 px-2 font-medium text-right">DRAPM</th>
                <th className="py-2 pl-2 font-medium text-right">RAPM</th>
                <th className="py-2 pl-2 font-medium text-right">Poss.</th>
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
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-zinc-300">
                    {fmt(entry.orapm)}
                  </td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-zinc-300">
                    {fmt(entry.drapm)}
                  </td>
                  <td className="py-2 pl-2 text-right font-mono tabular-nums font-semibold text-emerald-400">
                    {fmt(entry.rapm)}
                  </td>
                  <td className="py-2 pl-2 text-right font-mono tabular-nums text-zinc-600">
                    {entry.possessions ?? "—"}
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
