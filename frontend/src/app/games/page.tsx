"use client";

import { useState } from "react";
import Link from "next/link";
import { TeamLogo } from "@/components/nba-images";
import { useGames } from "@/lib/hooks";

const PAGE_SIZE = 20;

export default function GamesPage() {
  const [page, setPage] = useState(1);
  const { data, isPending, isError } = useGames({ page, page_size: PAGE_SIZE });

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Games</h1>

      {isPending && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-14 rounded-lg bg-zinc-800/50 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-zinc-400">Could not load games. Is the backend running?</p>
      )}

      {data && (
        <>
          <ul className="space-y-1" aria-label="Games list">
            {data.items.map((game) => (
              <li key={game.game_id}>
                <Link
                  href={`/games/${game.game_id}`}
                  className="flex items-center justify-between px-4 py-3 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/60 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1.5 font-medium text-sm">
                      <TeamLogo
                        teamId={game.home_team.team_id}
                        name={game.home_team.full_name}
                        className="size-6"
                      />
                      {game.home_team.abbreviation} vs {game.away_team.abbreviation}
                      <TeamLogo
                        teamId={game.away_team.team_id}
                        name={game.away_team.full_name}
                        className="size-6"
                      />
                    </span>
                    <span className="text-xs text-zinc-600">{game.game_date}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {game.home_score != null && game.away_score != null && (
                      <span className="font-mono text-sm">
                        {game.home_score}–{game.away_score}
                      </span>
                    )}
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        game.status === "final"
                          ? "bg-zinc-700 text-zinc-400"
                          : "bg-emerald-900/40 text-emerald-400"
                      }`}
                    >
                      {game.status}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>

          {/* Pagination */}
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
