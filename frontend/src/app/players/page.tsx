"use client";

import { useState } from "react";
import Link from "next/link";
import { usePlayers } from "@/lib/hooks";

const PAGE_SIZE = 25;

export default function PlayersPage() {
  const [page, setPage] = useState(1);
  const { data, isPending, isError } = usePlayers({
    // Hide historical-index players with no data in the loaded seasons.
    with_stats: true,
    page,
    page_size: PAGE_SIZE,
  });

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Players</h1>

      {isPending && (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-zinc-800/50 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-zinc-400">Could not load players. Is the backend running?</p>
      )}

      {data && (
        <>
          <ul className="space-y-1" aria-label="Players list">
            {data.items.map((player) => (
              <li key={player.player_id}>
                <Link
                  href={`/players/${player.player_id}`}
                  className="flex items-center justify-between px-4 py-3 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/60 transition-colors"
                >
                  <span className="font-medium text-sm">{player.full_name}</span>
                  <span className="text-xs text-zinc-500">{player.position ?? ""}</span>
                </Link>
              </li>
            ))}
          </ul>

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
